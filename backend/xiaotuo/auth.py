"""密码、会话 Cookie、CSRF。会话存数据库（PostgreSQL 或 SQLite），Cookie 只放不透明随机值，库里存其 SHA-256。"""
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from xiaotuo import db
from xiaotuo.config import settings
from xiaotuo.errors import ApiError, unauthorized
from xiaotuo.models import Session, User
from xiaotuo.progress import release_user_locks

COOKIE = "xt_session"
USER_TTL = timedelta(days=30)
ANON_TTL = timedelta(hours=2)
_ph = PasswordHasher()  # argon2id
_DUMMY_HASH = _ph.hash("dummy-password-for-timing")


def now() -> datetime:
    return datetime.now(UTC)


def sha256(s: str) -> bytes:
    return hashlib.sha256(s.encode()).digest()


@lru_cache
def common_passwords() -> frozenset[str]:
    path = Path(__file__).parent / "data" / "common-passwords.txt"
    return frozenset(line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def check_password_strength(pw: str) -> None:
    if pw.lower() in common_passwords():
        raise ApiError(400, "weak_password", "这个密码太常见了，换一个吧")


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw_hash: str | None, pw: str) -> bool:
    try:
        return _ph.verify(pw_hash or _DUMMY_HASH, pw) and pw_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


async def get_db():
    s = db.SessionLocal()
    try:
        yield s
    finally:
        await s.close()  # 先结束事务，再放开 SQLite 下的进程内用户锁
        release_user_locks(s)


@dataclass
class Ctx:
    db: AsyncSession
    session: Session | None
    user: User | None


async def load_ctx(request: Request, s: AsyncSession = Depends(get_db)) -> Ctx:
    raw = request.cookies.get(COOKIE)
    sess = user = None
    if raw:
        sess = await s.get(Session, sha256(raw))
        if sess and sess.expires_at <= now():
            await s.delete(sess)
            await s.commit()
            sess = None
        if sess and sess.user_id:
            user = await s.get(User, sess.user_id)
    return Ctx(s, sess, user)


def check_csrf(request: Request, ctx: Ctx) -> None:
    token = request.headers.get("x-csrf-token", "")
    if not ctx.session or not token or not hmac.compare_digest(token, ctx.session.csrf_token):
        raise ApiError(403, "csrf_failed", "页面已过期，请刷新后重试")


async def csrf(request: Request, ctx: Ctx = Depends(load_ctx)) -> Ctx:
    """匿名可用的写接口（注册、登录、找回密码）：只校验 CSRF。"""
    check_csrf(request, ctx)
    return ctx


async def user_csrf(request: Request, ctx: Ctx = Depends(load_ctx)) -> Ctx:
    """需要登录的写接口：先 401（未登录），再 403（CSRF）。"""
    if not ctx.user:
        raise unauthorized()
    check_csrf(request, ctx)
    return ctx


async def user_only(ctx: Ctx = Depends(load_ctx)) -> Ctx:
    if not ctx.user:
        raise unauthorized()
    return ctx


def set_cookie(resp: Response, raw: str, ttl: timedelta) -> None:
    resp.set_cookie(COOKIE, raw, max_age=int(ttl.total_seconds()), httponly=True, secure=settings.cookie_secure,
                    samesite="lax", path="/")


def clear_cookie(resp: Response) -> None:
    resp.set_cookie(COOKIE, "", max_age=0, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")


async def new_session(s: AsyncSession, resp: Response, user_id: int | None, ua: str | None) -> Session:
    raw = secrets.token_urlsafe(32)
    ttl = USER_TTL if user_id else ANON_TTL
    t = now()
    sess = Session(id_hash=sha256(raw), user_id=user_id, csrf_token=secrets.token_hex(16), user_agent=ua,
                   created_at=t, last_seen_at=t, expires_at=t + ttl)
    s.add(sess)
    set_cookie(resp, raw, ttl)
    return sess


async def rotate_session(ctx: Ctx, resp: Response, user_id: int, request: Request) -> Session:
    """登录/注册成功：删除旧（预）会话，生成新会话 ID 与 CSRF token，防会话固定。"""
    if ctx.session:
        await ctx.db.execute(delete(Session).where(Session.id_hash == ctx.session.id_hash))
    return await new_session(ctx.db, resp, user_id, request.headers.get("user-agent"))


async def user_by_email(s: AsyncSession, email: str) -> User | None:
    return (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
