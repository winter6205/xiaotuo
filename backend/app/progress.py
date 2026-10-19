"""进度状态复算：快照（与 course.js blank() 同构）、连学、徽章、ETag。"""
import hashlib
import json
import re
from datetime import date, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.content import NON_PRACTICE_TYPES, Course
from app.models import ActivityDay, BadgeAward, ProgressItem

_CODER_RE = re.compile(r"-(fill|codespot|spot)-")


async def lock_user(s: AsyncSession, user_id: int) -> None:
    """同一用户的写操作串行化（事务级 advisory lock），保证幂等去重与取 max 不竞争。"""
    await s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": user_id})


async def load_rows(s: AsyncSession, user_id: int, course: str) -> dict[str, ProgressItem]:
    rows = await s.execute(select(ProgressItem).where(ProgressItem.user_id == user_id, ProgressItem.course == course))
    return {r.item_id: r for r in rows.scalars()}


async def load_days(s: AsyncSession, user_id: int, course: str | None = None) -> set[date]:
    q = select(ActivityDay.day).where(ActivityDay.user_id == user_id)
    if course:
        q = q.where(ActivityDay.course == course)
    return set((await s.execute(q)).scalars())


async def load_badges(s: AsyncSession, user_id: int, course: str) -> dict[str, date]:
    q = select(BadgeAward.badge_id, BadgeAward.awarded_on).where(BadgeAward.user_id == user_id,
                                                                 BadgeAward.course == course)
    return dict((await s.execute(q)).all())


async def add_days(s: AsyncSession, user_id: int, course: str, days: set[date]) -> None:
    if days:
        await s.execute(insert(ActivityDay).values([{"user_id": user_id, "course": course, "day": d} for d in days])
                        .on_conflict_do_nothing())


def streak(days: set[date]) -> dict:
    """touchDay() 口径：cur=以 last 结尾的连续天数，best=最长连续，last=最近活动日。"""
    if not days:
        return {"cur": 0, "best": 0, "last": None}
    best = run = 0
    prev = None
    for d in sorted(days):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    return {"cur": run, "best": best, "last": prev.isoformat()}


def streak_now(st: dict, today: date) -> int:
    """streakNow()：last 距今天 ≤1 天才算连续中。"""
    if not st["last"]:
        return 0
    return st["cur"] if (today - date.fromisoformat(st["last"])).days <= 1 else 0


def build_state(course: Course, rows: dict[str, ProgressItem], days: set[date], badges: dict[str, date]) -> dict:
    xp, done, rec, solved, fix = {}, {}, {}, {}, {}
    for iid, r in sorted(rows.items()):
        if r.amt is not None:
            xp[iid] = r.amt
        if r.kind == "done" and r.active:
            done[iid] = 1
        if r.kind == "rec" and r.active:
            rec[iid] = 1
        if r.rev is not None:
            solved[iid] = {"rev": r.rev, "wrong": r.wrong or 0}
        elif r.kind == "xp" and r.amt is not None:
            item = course.items.get(iid)
            if item and item.type not in NON_PRACTICE_TYPES:  # blank-writeback：练习组件缺 solved 时补
                solved[iid] = {"rev": r.amt in (0, 5), "wrong": 0}
        if r.fix:
            fix[iid] = 1
    data = {f"cleared.{p}": 1 for p, pg in course.pages.items() if pg.get("boss") and f"{pg['boss']}-clear" in xp}
    head = {"version": 1, "course": course.course_id} if course.state_version == 1 else \
        {"version": course.state_version, "migratedV1": True}  # state_version 2 的 blank()：无 course 字段
    return {**head, "xp": xp, "done": done, "rec": rec, "solved": solved,
            "fix": fix, "streak": streak(days), "days": {d.isoformat(): 1 for d in sorted(days)},
            "badges": {b: d.isoformat() for b, d in sorted(badges.items())}, "quiet": False, "data": data,
            "sections": {}}


def satisfied_badges(course: Course, state: dict) -> set[str]:
    """course.js checkBadges()（L67–74）+ Boss 通关徽章（L588）。"""
    got = set()
    if state["done"]:
        got.add("first")
    if state["streak"]["best"] >= 3:
        got.add("streak3")
    if state["streak"]["best"] >= 7:
        got.add("streak7")
    if len(state["fix"]) >= 5:
        got.add("comeback")
    if sum(1 for k, v in state["solved"].items() if _CODER_RE.search(k) and not v["rev"]) >= 10:
        got.add("coder")
    for iid, b in course.item_badges.items():  # 组件 data-badge：不看答案做对即得
        if iid in state["solved"] and not state["solved"][iid]["rev"]:
            got.add(b)
    xp, done = state["xp"], state["done"]
    grad = course.grad_pages
    if grad and all(all(i in done for i in pg.get("sections", [])) and
                    (not pg.get("boss") or f"{pg['boss']}-clear" in xp) for pg in grad.values()):
        got.add("grad")
    for pg in course.pages.values():
        if pg.get("boss") and pg.get("badge") and f"{pg['boss']}-clear" in xp and course.badge(pg["badge"]):
            got.add(pg["badge"])
    return {b for b in got if course.badge(b)}  # 只发本课徽章表里有的（如有的课没有 coder）


async def award_badges(s: AsyncSession, user_id: int, course: Course, state: dict, on_day: date,
                       candidates: dict[str, date] | None = None) -> list[str]:
    """把已满足条件的徽章写入 badge_awards（已有的取较早日期）；返回新增的徽章 id。

    candidates：导入文件里的徽章与日期，仅在条件满足时采信其日期。
    """
    have = await load_badges(s, user_id, course.code)
    ok = satisfied_badges(course, state)
    new = []
    for b in sorted(ok):
        d = min(filter(None, [(candidates or {}).get(b), on_day]))
        if b not in have:
            new.append(b)
        elif have[b] <= d:
            continue
        await s.execute(insert(BadgeAward).values(user_id=user_id, course=course.code, badge_id=b, awarded_on=d)
                        .on_conflict_do_update(index_elements=["user_id", "course", "badge_id"],
                                               set_={"awarded_on": func.least(BadgeAward.awarded_on, d)}))
        have[b] = d
        state["badges"][b] = min(d.isoformat(), state["badges"].get(b, "9999"))
    state["badges"] = dict(sorted(state["badges"].items()))
    return new


def etag(course: str, state: dict) -> str:
    digest = hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    return f'W/"{course}-{digest}"'


async def current_state(s: AsyncSession, user_id: int, course: Course) -> dict:
    return build_state(course, await load_rows(s, user_id, course.code), await load_days(s, user_id, course.code),
                       await load_badges(s, user_id, course.code))


def xp_total(state: dict) -> int:
    return sum(state["xp"].values())
