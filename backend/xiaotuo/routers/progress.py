import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import delete, select

from xiaotuo import ratelimit
from xiaotuo.auth import Ctx, now, user_csrf, user_only
from xiaotuo.content import Course, courses, get_course
from xiaotuo.errors import ApiError, course_not_found
from xiaotuo.models import ActivityDay, BadgeAward, Import, ProgressEvent, ProgressItem, ProgressReset
from xiaotuo.dbtypes import utc_iso
from xiaotuo.progress import (add_days, award_badges, build_state, current_state, etag, insert, load_badges,
                              load_days, load_rows, lock_user, xp_total)

router = APIRouter(prefix="/api/progress")
FUTURE_SKEW = timedelta(minutes=5)
EVENTS_MAX_BYTES = 1 * 1024 * 1024
IMPORT_MAX_BYTES = 2 * 1024 * 1024

ItemId = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[^\s/]+$")]
LocalDate = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
CourseCode = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,15}$")]


def _uuid(v: str) -> str:
    return str(uuid.UUID(v))


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Solved(Strict):
    rev: bool
    wrong: int = Field(ge=0)


class Event(Strict):
    course: CourseCode
    item_id: ItemId
    kind: Literal["xp", "done", "solved", "rec"]
    amt: int | None = Field(default=None, ge=0, le=1000)
    client_event_id: Annotated[str, AfterValidator(_uuid)]
    ts: datetime
    day: LocalDate | None = None
    solved: Solved | None = None
    fix: bool | None = None
    value: bool | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.kind in ("xp", "done") and self.amt is None:
            raise ValueError("kind=xp/done 时 amt 必填")
        if self.ts.tzinfo is None:
            raise ValueError("ts 须带时区（RFC 3339）")
        return self


class EventsBody(Strict):
    events: list[Event] = Field(min_length=1, max_length=500)


class Streak(BaseModel):
    cur: int = Field(ge=0)
    best: int = Field(ge=0)
    last: LocalDate | None = None


class CourseState(BaseModel):
    # version/course 不在模型里做 const/enum 限制，以便按 openapi 返回 422 import_course_mismatch
    version: int
    course: str | None = None  # state_version 2 的状态没有 course
    xp: dict[str, Annotated[int, Field(ge=0)]]
    done: dict[str, Literal[1]] = {}
    rec: dict[str, Literal[1]] = {}
    solved: dict[str, Solved] = {}
    fix: dict[str, Literal[1]] = {}
    streak: Streak | None = None
    days: dict[LocalDate, Literal[1]] = {}
    badges: dict[str, LocalDate] = {}
    quiet: bool | None = None
    data: dict | None = None
    sections: dict[str, list[str]] | None = None


class ImportBody(Strict):
    source: Literal["export_file", "local_first_login"]
    state: CourseState


class ResetBody(Strict):
    confirm: str


def course_or_404(course: str) -> Course:
    c = get_course(course)
    if not c:
        raise course_not_found()
    return c


async def body_limit(request: Request, limit: int) -> None:
    if len(await request.body()) > limit:
        raise ApiError(413, "payload_too_large", "文件太大")


async def events_limit(request: Request):
    await body_limit(request, EVENTS_MAX_BYTES)


async def import_limit(request: Request):
    await body_limit(request, IMPORT_MAX_BYTES)


def iso(t: datetime) -> str:
    return utc_iso(t)


def _parse_day(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


# ---------------- 快照 ----------------

@router.get("/{course}")
async def snapshot(course: str, response: Response, ctx: Ctx = Depends(user_only),
                   if_none_match: str | None = Header(default=None)):
    c = course_or_404(course)
    state = await current_state(ctx.db, ctx.user.id, c)
    tag = etag(c.code, state)
    if if_none_match and tag in [t.strip() for t in if_none_match.split(",")]:
        return Response(status_code=304, headers={"ETag": tag})
    response.headers["ETag"] = tag
    return {"course": c.code, "storage_key": c.storage_key, "server_time": iso(now()),
            "content_version": c.content_version, "state": state}


# ---------------- 事件 ----------------

def _merge(row: ProgressItem, *, amt=None, solved=None, fix=None, active=None, at=None, kind=None) -> tuple[bool, bool]:
    """按并集规则合并进已有行：amt 取 max、时间取较早、rev 以 false 优先、wrong 取小、fix 取或。
    返回 (raised, changed)。"""
    raised = changed = False
    if amt is not None and (row.amt is None or amt > row.amt):
        raised, row.amt = True, amt
    if kind and row.kind == "solved" and kind != "solved":
        changed, row.kind = True, kind
    if solved is not None:
        rev = solved.rev if row.rev is None else (row.rev and solved.rev)
        wrong = solved.wrong if row.wrong is None else min(row.wrong, solved.wrong)
        changed |= (rev, wrong) != (row.rev, row.wrong)
        row.rev, row.wrong = rev, wrong
    if fix and not row.fix:
        changed, row.fix = True, True
    if active is not None and active != row.active:
        changed, row.active = True, active
    if at is not None and at < row.first_at:
        row.first_at = at
    return raised, changed


@router.post("/{course}/events", dependencies=[Depends(events_limit)])
async def post_events(course: str, body: EventsBody, ctx: Ctx = Depends(user_csrf)):
    c = course_or_404(course)
    uid = ctx.user.id
    ratelimit.hit("events_user", str(uid))
    s = ctx.db
    await lock_user(s, uid)
    t_now = now()
    cids = [e.client_event_id for e in body.events]
    seen = set((await s.execute(select(ProgressEvent.client_event_id).where(
        ProgressEvent.user_id == uid, ProgressEvent.client_event_id.in_(cids)))).scalars())
    rows = await load_rows(s, uid, c.code)
    new_days: set[date] = set()
    last_day = None
    results, logs = [], []
    for e in body.events:
        cid = e.client_event_id
        if cid in seen:
            r = rows.get(e.item_id)
            res = {"client_event_id": cid, "status": "duplicate"}
            if r is not None and r.amt is not None and e.kind in ("xp", "done"):
                res["amt"] = r.amt
            results.append(res)
            continue
        seen.add(cid)
        ts = e.ts if e.ts <= t_now + FUTURE_SKEW else t_now  # 晚于服务器 5 分钟以上按服务器时间
        day = _parse_day(e.day) or ts.date()
        item = c.items.get(e.item_id)
        res = {"client_event_id": cid}
        if e.course != c.code:
            res.update(status="rejected", reason="course_mismatch")
        elif not item:
            res.update(status="rejected", reason="unknown_item")
        else:
            amt = min(e.amt, item.max_xp) if e.kind in ("xp", "done") else None
            active = (True if e.value is None else e.value) if e.kind in ("done", "rec") else None
            row = rows.get(e.item_id)
            if row is None:
                row = ProgressItem(user_id=uid, course=c.code, item_id=e.item_id, kind=e.kind, amt=amt,
                                   rev=e.solved.rev if e.solved else None, wrong=e.solved.wrong if e.solved else None,
                                   fix=bool(e.fix), active=True if active is None else active, first_at=ts,
                                   updated_at=t_now, source="event")
                s.add(row)
                rows[e.item_id] = row
                status = "applied"
                if amt:  # course.js award()：仅首次写入且 amt>0 才 touchDay
                    new_days.add(day)
            else:
                raised, changed = _merge(row, amt=amt, solved=e.solved, fix=e.fix, active=active, at=ts, kind=e.kind)
                status = "raised" if raised else "applied" if changed else "unchanged"
                if raised or changed:
                    row.updated_at = t_now
            res["status"] = status
            if amt is not None:
                res["amt"] = row.amt
                if e.amt > item.max_xp:
                    res["reason"] = "amt_capped"
            last_day = max(filter(None, [last_day, day]))
        results.append(res)
        logs.append({"user_id": uid, "client_event_id": cid, "course": e.course, "item_id": e.item_id,
                     "kind": e.kind, "amt": e.amt, "client_ts": ts, "local_day": day, "status": res["status"],
                     "payload": e.model_dump(include={"solved", "fix", "value"}, exclude_none=True) or None})
    if logs:
        await s.execute(insert(s, ProgressEvent).values(logs).on_conflict_do_nothing())
    await s.flush()
    await add_days(s, uid, c.code, new_days)
    state = build_state(c, rows, await load_days(s, uid, c.code), await load_badges(s, uid, c.code))
    new_badges = await award_badges(s, uid, c, state, last_day or t_now.date())
    await s.commit()
    return {"results": results, "xp_total": xp_total(state), "new_badges": new_badges,
            "snapshot_etag": etag(c.code, state)}


# ---------------- 导入（并集） ----------------

@router.post("/{course}/import", dependencies=[Depends(import_limit)])
async def import_progress(course: str, body: ImportBody, ctx: Ctx = Depends(user_csrf),
                          idempotency_key: str | None = Header(default=None, max_length=64)):
    c = course_or_404(course)
    uid = ctx.user.id
    ratelimit.hit("import_user", str(uid))
    s = ctx.db
    st = body.state
    # state_version 2 的状态没有 course 字段，只认 version
    if st.version != c.state_version or (c.state_version == 1 and st.course != c.course_id):
        raise ApiError(422, "import_course_mismatch",
                       "这是另一门课的进度文件" if st.version == c.state_version else "文件不是本课导出的进度",
                       {"expected": c.course_id, "got": st.course})
    await lock_user(s, uid)
    if idempotency_key:
        prev = (await s.execute(select(Import.result).where(Import.user_id == uid,
                                                            Import.idempotency_key == idempotency_key))).scalar()
        if prev is not None:
            return prev
    t_now = now()
    rows = await load_rows(s, uid, c.code)
    xp_before = sum(r.amt or 0 for r in rows.values())
    ids = set(st.xp) | set(st.done) | set(st.rec) | set(st.solved) | set(st.fix)
    unknown = sorted(i for i in ids if i not in c.items)
    added = raised_n = 0
    for iid in sorted(ids - set(unknown)):
        item = c.items[iid]
        if iid in st.xp or iid in st.done:
            kind = "done" if iid in st.done or item.type == "done" else "xp"
            amt = min(st.xp.get(iid, 0), item.max_xp)  # done 缺 xp 时按 0 记（见 README）
        else:
            kind, amt = ("rec" if iid in st.rec else "solved"), None
        solved = st.solved.get(iid)
        row = rows.get(iid)
        if row is None:
            active = iid in st.done if kind == "done" else iid in st.rec if kind == "rec" else True
            row = ProgressItem(user_id=uid, course=c.code, item_id=iid, kind=kind, amt=amt,
                               rev=solved.rev if solved else None, wrong=solved.wrong if solved else None,
                               fix=iid in st.fix, active=active, first_at=t_now, updated_at=t_now, source="import")
            s.add(row)
            rows[iid] = row
            added += 1
        else:  # 并集：只会勾上，不会取消已有勾选
            r, ch = _merge(row, amt=amt, solved=solved, fix=iid in st.fix, kind=kind,
                           active=True if (iid in st.done or iid in st.rec) else None)
            raised_n += r
            if r or ch:
                row.updated_at = t_now
    days = {d for d in map(_parse_day, st.days) if d}
    await s.flush()
    await add_days(s, uid, c.code, days)
    state = build_state(c, rows, await load_days(s, uid, c.code), await load_badges(s, uid, c.code))
    cand = {b: d for b, d in ((b, _parse_day(v)) for b, v in st.badges.items()) if d}
    badges_added = await award_badges(s, uid, c, state, max(days) if days else t_now.date(), cand)
    result = {"imported_at": iso(t_now), "items_added": added, "items_raised": raised_n, "unknown_ids": unknown,
              "badges_added": badges_added, "xp_before": xp_before, "xp_after": xp_total(state)}
    s.add(Import(user_id=uid, course=c.code, source=body.source, idempotency_key=idempotency_key, result=result,
                 created_at=t_now))
    await s.commit()
    return result


# ---------------- 账号级清空 ----------------

@router.post("/{scope}/reset")
async def reset_progress(scope: str, body: ResetBody, ctx: Ctx = Depends(user_csrf)):
    known = list(courses())
    if scope not in (*known, "all"):
        raise ApiError(400, "validation_error", "请求字段不合法",
                       {"fields": [{"loc": ["path", "scope"], "msg": "须为已有课程 id 或 all"}]})
    if body.confirm != f"RESET {scope}":
        raise ApiError(400, "confirm_required", f"请输入 RESET {scope} 确认")
    uid = ctx.user.id
    ratelimit.hit("progress_reset_user", str(uid))
    s = ctx.db
    await lock_user(s, uid)
    targets = known if scope == "all" else [scope]
    t = now()
    n = (await s.execute(delete(ProgressItem).where(ProgressItem.user_id == uid,
                                                    ProgressItem.course.in_(targets)))).rowcount
    for model in (BadgeAward, ActivityDay):
        await s.execute(delete(model).where(model.user_id == uid, model.course.in_(targets)))
    s.add_all([ProgressReset(user_id=uid, course=co, reset_at=t) for co in targets])
    await s.commit()
    return {"reset_at": iso(t), "courses": targets, "items_deleted": n}
