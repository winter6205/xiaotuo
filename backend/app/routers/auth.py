import ipaddress
import logging
import re
import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from app import ratelimit
from app.auth import (Ctx, check_password_strength, clear_cookie, client_ip, csrf, hash_password, load_ctx,
                      new_session, now, rotate_session, sha256, user_by_email, user_csrf, verify_password)
from app.config import settings
from app.content import default_course
from app.errors import ApiError
from app.models import PasswordReset, Session, User

router = APIRouter(prefix="/api")
log = logging.getLogger(__name__)
NO_STORE = {"Cache-Control": "no-store"}
RESET_TTL = timedelta(minutes=30)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _email(v: str) -> str:
    v = v.strip().lower()
    if not _EMAIL_RE.match(v):
        raise ValueError("邮箱格式不正确")
    return v


Email = Annotated[str, Field(max_length=254), AfterValidator(_email)]
Password = Annotated[str, Field(min_length=10, max_length=128)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(Strict):
    email: Email
    password: Password


class ResetRequest(Strict):
    email: Email


class ResetConfirm(Strict):
    token: str = Field(min_length=32, max_length=128)
    new_password: Password


def user_json(u: User) -> dict:
    return {"id": u.id, "email": u.email, "created_at": u.created_at.isoformat().replace("+00:00", "Z")}


def me_json(user: User | None, csrf_token: str) -> dict:
    return {"user": user_json(user) if user else None, "csrf_token": csrf_token, "default_course": default_course(),
            "features": {"password_reset": settings.email_enabled}}


@router.get("/me")
async def get_me(request: Request, response: Response, ctx: Ctx = Depends(load_ctx)):
    response.headers.update(NO_STORE)
    sess = ctx.session
    if not sess:  # 匿名预会话，只承载 CSRF
        sess = await new_session(ctx.db, response, None, request.headers.get("user-agent"))
        await ctx.db.commit()
    return me_json(ctx.user, sess.csrf_token)


@router.post("/auth/register", status_code=201)
async def register(body: Credentials, request: Request, response: Response, ctx: Ctx = Depends(csrf)):
    ratelimit.hit("register_ip", client_ip(request))
    check_password_strength(body.password)
    user = User(email=body.email, pw_hash=hash_password(body.password))
    ctx.db.add(user)
    try:
        await ctx.db.flush()
    except IntegrityError:
        raise ApiError(409, "email_taken", "该邮箱已注册，可直接登录或找回密码")
    sess = await rotate_session(ctx, response, user.id, request)
    await ctx.db.commit()
    await ctx.db.refresh(user)
    response.headers.update(NO_STORE)
    return me_json(user, sess.csrf_token)


@router.post("/auth/login")
async def login(body: Credentials, request: Request, response: Response, ctx: Ctx = Depends(csrf)):
    ratelimit.hit("login_ip", client_ip(request))
    ratelimit.hit("login_email", body.email)
    user = await user_by_email(ctx.db, body.email)
    if not verify_password(user.pw_hash if user else None, body.password):
        raise ApiError(401, "invalid_credentials", "邮箱或密码不正确")
    sess = await rotate_session(ctx, response, user.id, request)
    await ctx.db.commit()
    response.headers.update(NO_STORE)
    return me_json(user, sess.csrf_token)


@router.post("/auth/logout", status_code=204)
async def logout(ctx: Ctx = Depends(user_csrf)):
    await ctx.db.execute(delete(Session).where(Session.id_hash == ctx.session.id_hash))
    await ctx.db.commit()
    resp = Response(status_code=204)
    clear_cookie(resp)
    return resp


async def csrf_email(ctx: Ctx = Depends(csrf)) -> Ctx:
    """找回密码：CSRF 之后、请求体校验之前判断 EMAIL_ENABLED。"""
    if not settings.email_enabled:
        raise ApiError(503, "email_disabled", "找回密码暂未开放，请联系管理员")
    return ctx


def _inet(ip: str) -> str | None:
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return None


async def send_reset_email(email: str, token: str) -> None:
    """Resend 接入留到 M5（需维护者开通账号与发信域名）；当前只记日志，不打印 token。"""
    log.info("password reset requested for %s", email)


@router.post("/auth/password-reset/request", status_code=202)
async def reset_request(body: ResetRequest, request: Request, ctx: Ctx = Depends(csrf_email)):
    ip = client_ip(request)
    ratelimit.hit("reset_ip", ip)
    ratelimit.hit("reset_email", body.email)
    user = await user_by_email(ctx.db, body.email)
    if user:
        t = now()
        await ctx.db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id,
                                                         PasswordReset.used_at.is_(None)).values(used_at=t))
        token = secrets.token_urlsafe(32)
        ctx.db.add(PasswordReset(user_id=user.id, token_hash=sha256(token), created_at=t, expires_at=t + RESET_TTL,
                                 request_ip=_inet(ip)))
        await ctx.db.commit()
        await send_reset_email(user.email, token)
    return {"message": "如果该邮箱已注册，你会在几分钟内收到重置链接"}


@router.post("/auth/password-reset/confirm", status_code=204)
async def reset_confirm(body: ResetConfirm, request: Request, ctx: Ctx = Depends(csrf_email)):
    ratelimit.hit("reset_confirm_ip", client_ip(request))
    t = now()
    pr = (await ctx.db.execute(select(PasswordReset).where(
        PasswordReset.token_hash == sha256(body.token), PasswordReset.used_at.is_(None),
        PasswordReset.expires_at > t).with_for_update())).scalar_one_or_none()
    if not pr:
        raise ApiError(400, "reset_token_invalid", "链接已失效，请重新申请")
    check_password_strength(body.new_password)
    pr.used_at = t
    await ctx.db.execute(update(User).where(User.id == pr.user_id).values(
        pw_hash=hash_password(body.new_password), password_changed_at=t, updated_at=t))
    await ctx.db.execute(delete(Session).where(Session.user_id == pr.user_id))
    await ctx.db.commit()
    return Response(status_code=204)
