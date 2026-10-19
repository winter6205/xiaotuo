"""两种库（XT_TEST_DB=sqlite|postgres）都要成立的行为：约束、级联、时区、徽章取较早日期、并发写同一用户，
以及 API 响应里的时间一律带时区（UTC，Z 结尾）。"""
import asyncio
import re
from datetime import UTC, date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from tests.conftest import SQLITE, Api, ev
from xiaotuo import db
from xiaotuo.dbtypes import UTCDateTime, utc_iso
from xiaotuo.main import app
from xiaotuo.models import ActivityDay, BadgeAward, ProgressEvent, ProgressItem, Session, User

TZ_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$")


def run(coro):
    return asyncio.run(coro)


async def _with_session(fn):
    async with db.SessionLocal() as s:
        return await fn(s)


def test_dialect_matches_switch():
    assert db.engine.dialect.name == ("sqlite" if SQLITE else "postgresql")


def test_invalid_course_rejected_by_check(user):
    uid = user.get("/api/me").json()["user"]["id"]

    async def go(s):
        s.add(ActivityDay(user_id=uid, course="Bad-Id", day=date(2026, 10, 1)))
        await s.commit()
    with pytest.raises(IntegrityError):
        run(_with_session(go))

    async def ok(s):
        s.add(ActivityDay(user_id=uid, course="ok_1", day=date(2026, 10, 1)))
        await s.commit()
    run(_with_session(ok))


def test_delete_user_cascades(user):
    user.post("/api/progress/alpha/events", {"events": [ev("01-done-a", kind="done", amt=10)]})
    uid = user.get("/api/me").json()["user"]["id"]

    async def go(s):
        await s.delete(await s.get(User, uid))
        await s.commit()
        counts = []
        for m in (Session, ProgressItem, ActivityDay):
            counts.append((await s.execute(select(func.count()).select_from(m).where(m.user_id == uid))).scalar())
        return counts
    assert run(_with_session(go)) == [0, 0, 0]  # SQLite 须开 foreign_keys 才会级联


def test_timezone_roundtrip(user):
    uid = user.get("/api/me").json()["user"]["id"]
    t = datetime(2026, 10, 18, 8, 21, 4, 123456, tzinfo=timezone(timedelta(hours=8)))

    async def go(s):
        s.add(ProgressItem(user_id=uid, course="alpha", item_id="01-1-quiz-x", kind="xp", amt=1, first_at=t,
                           source="event"))
        await s.commit()
        s.expunge_all()
        row = (await s.execute(select(ProgressItem).where(ProgressItem.user_id == uid))).scalar_one()
        u = await s.get(User, uid)
        return row.first_at, row.updated_at, u.created_at
    first_at, updated_at, created_at = run(_with_session(go))
    assert first_at == t and first_at.tzinfo is not None and first_at.utcoffset() == timedelta(0)
    for v in (updated_at, created_at):  # 服务端默认值同样读回 aware UTC
        assert v.tzinfo is not None and v.utcoffset() == timedelta(0)
        assert abs(datetime.now(UTC) - v) < timedelta(minutes=5)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        UTCDateTime().process_bind_param(datetime(2026, 1, 1), db.engine.dialect)
    with pytest.raises(ValueError):
        utc_iso(datetime(2026, 1, 1))
    assert utc_iso(datetime(2026, 1, 1, 8, tzinfo=timezone(timedelta(hours=8)))) == "2026-01-01T00:00:00Z"


def test_badge_upsert_keeps_earlier_date(user):
    r = user.post("/api/progress/alpha/events", {"events": [ev("01-done-a", kind="done", amt=10, day="2026-10-18")]})
    assert "first" in r.json()["new_badges"]
    user.post("/api/progress/alpha/import", {"source": "export_file", "state": {
        "version": 1, "course": "alpha", "xp": {"01-done-a": 10}, "done": {"01-done-a": 1},
        "badges": {"first": "2026-10-01"}}})
    user.post("/api/progress/alpha/import", {"source": "export_file", "state": {
        "version": 1, "course": "alpha", "xp": {"01-done-a": 10}, "done": {"01-done-a": 1},
        "badges": {"first": "2026-10-10"}}})  # 更晚的日期不覆盖

    async def go(s):
        return (await s.execute(select(BadgeAward.awarded_on).where(BadgeAward.badge_id == "first"))).scalar_one()
    assert run(_with_session(go)) == date(2026, 10, 1)
    assert user.get("/api/progress/alpha").json()["state"]["badges"]["first"] == "2026-10-01"


def test_concurrent_writes_same_user(user):
    """同一用户并发写：PG 靠 advisory lock，SQLite 靠进程内用户锁 + BEGIN IMMEDIATE；不报错、不丢更新。"""
    cookies = dict(user.c.cookies)
    csrf = user.csrf
    items = ["01-1-quiz-x", "01-1-sim-x", "01-done-a", "01-done-b"]

    async def go():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver", cookies=cookies) as c:
            reqs = [c.post("/api/progress/alpha/events", headers={"X-CSRF-Token": csrf},
                           json={"events": [ev(items[i % 4], kind="done" if "done" in items[i % 4] else "xp",
                                               amt=1 + i)]}) for i in range(12)]
            return await asyncio.gather(*reqs)
    res = asyncio.run(go())
    assert [r.status_code for r in res] == [200] * 12, [r.text for r in res if r.status_code != 200]
    assert all(r.json()["results"][0]["status"] in ("applied", "raised", "unchanged") for r in res)
    xp = user.get("/api/progress/alpha").json()["state"]["xp"]
    assert set(items) <= set(xp)

    async def count(s):
        return (await s.execute(select(func.count()).select_from(ProgressEvent))).scalar()
    assert run(_with_session(count)) == 12  # 每个事件都记了日志，没有因锁冲突丢失


def test_api_times_are_utc_aware(user):
    """所有带时间的响应字段：/api/me、注册、快照 server_time、导入 imported_at、清空 reset_at、
    学习中心 user.created_at / recent[].at / last_import.imported_at。"""
    seen = []

    def check(v, where):
        assert isinstance(v, str) and TZ_RE.match(v), f"{where}: {v!r}"
        seen.append(where)

    a = Api()
    r = a.post("/api/auth/register", {"email": "tz@example.com", "password": "correct-horse-battery"})
    check(r.json()["user"]["created_at"], "register.user.created_at")
    check(a.get("/api/me").json()["user"]["created_at"], "me.user.created_at")
    a.post("/api/progress/alpha/events", {"events": [
        ev("01-done-a", kind="done", amt=10, ts="2026-10-18T23:30:00-07:00", day="2026-10-18"),
        ev("01-1-quiz-x", amt=10, ts="2026-10-19T08:00:00+08:00", day="2026-10-19")]})
    check(a.get("/api/progress/alpha").json()["server_time"], "snapshot.server_time")
    r = a.post("/api/progress/alpha/import", {"source": "export_file", "state": {
        "version": 1, "course": "alpha", "xp": {"01-1-sim-x": 15}}})
    check(r.json()["imported_at"], "import.imported_at")
    d = a.get("/api/dashboard", params={"tz": "Asia/Hong_Kong"}).json()
    check(d["user"]["created_at"], "dashboard.user.created_at")
    assert d["recent"]
    for e in d["recent"]:
        check(e["at"], "dashboard.recent[].at")
    check(d["last_import"]["imported_at"], "dashboard.last_import.imported_at")
    assert d["summary"]["days_total"] == 2 and d["summary"]["streak_best"] == 2
    r = a.post("/api/progress/alpha/reset", {"confirm": "RESET alpha"})
    check(r.json()["reset_at"], "reset.reset_at")
    # 清空之后 recent 不再显示之前的事件（SQLite 上按 UTC 文本比较，PG 上按 timestamptz）
    assert a.get("/api/dashboard").json()["recent"] == []
    assert len(set(seen)) == 8
