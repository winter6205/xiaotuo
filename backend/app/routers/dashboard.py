from collections import defaultdict
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.auth import Ctx, user_only
from app.content import courses
from app.errors import ApiError
from app.models import Import, ProgressEvent, ProgressReset
from app.progress import current_state, load_days, streak, streak_now
from app.routers.auth import user_json
from app.routers.progress import iso

router = APIRouter(prefix="/api")
RECENT = 20


def _id_done(state: dict, iid: str) -> bool:
    """course.js idDone()（L720）。"""
    if "-done-" in iid:
        return iid in state["done"]
    return iid in state["done"] or iid in state["rec"] or iid in state["xp"]


def local_today(tz: str | None) -> date:
    """学员本地「今天」：tz 为 IANA 时区名（如 Asia/Hong_Kong），缺省按 UTC。"""
    if not tz:
        return datetime.now(UTC).date()
    try:
        return datetime.now(ZoneInfo(tz)).date()
    except (ZoneInfoNotFoundError, ValueError):
        raise ApiError(400, "validation_error", "请求字段不合法",
                       {"fields": [{"loc": ["query", "tz"], "msg": "不是有效的 IANA 时区名"}]})


@router.get("/dashboard")
async def dashboard(ctx: Ctx = Depends(user_only), tz: str | None = Query(default=None, max_length=64)):
    today = local_today(tz)
    s, uid = ctx.db, ctx.user.id
    out_courses, out_badges = [], []
    for c in courses().values():
        st = await current_state(s, uid, c)
        days = {date.fromisoformat(d) for d in st["days"]}
        chapters: dict[str, dict] = defaultdict(lambda: {"items_done": 0, "items_total": 0, "xp": 0, "xp_max": 0,
                                                           "scored_total": 0, "scored_done": 0, "tracks_done": 0})
        for item in c.items.values():
            ch = chapters[item.chapter]
            ch["items_total"] += 1
            ch["xp_max"] += item.max_xp
            done = _id_done(st, item.id)
            ch["items_done"] += done
            if item.max_xp > 0:
                ch["scored_total"] += 1
                ch["scored_done"] += done
            else:
                ch["tracks_done"] += done
            ch["xp"] += st["xp"].get(item.id, 0)
        xp = sum(st["xp"].values())
        out_courses.append({
            "course": c.code, "title": c.title, "xp": xp, "xp_max": c.total, "level": c.level(xp),
            "items_done": sum(ch["items_done"] for ch in chapters.values()), "items_total": len(c.items),
            **{k: sum(ch[k] for ch in chapters.values()) for k in ("scored_total", "scored_done", "tracks_done")},
            "chapters": [{"chapter_id": k, "title": c.chapters.get(k, k), **v,
                          "has_boss": bool(c.pages.get(k, {}).get("boss")),
                          "boss_cleared": bool((b := c.pages.get(k, {}).get("boss")) and f"{b}-clear" in st["xp"])}
                         for k, v in sorted(chapters.items())],
            "streak_cur": streak_now(st["streak"], today), "streak_best": st["streak"]["best"],
            "days_total": len(days), "badges_count": sum(1 for b in st["badges"] if c.badge(b)), "badges_total": len(c.all_badges)})
        for b, d in st["badges"].items():
            if (meta := c.badge(b)):
                out_badges.append({"course": c.code, "badge_id": b, "icon": meta[1], "name": meta[2],
                                   "desc": meta[3], "awarded_at": d})
    all_days = await load_days(s, uid)
    union = streak(all_days)
    summary = {"xp_total": sum(x["xp"] for x in out_courses), "streak_cur": streak_now(union, today),
               "streak_best": union["best"], "days_total": len(all_days),
               "badges_count": sum(x["badges_count"] for x in out_courses),
               "badges_total": sum(x["badges_total"] for x in out_courses)}
    return {"user": user_json(ctx.user), "summary": summary, "courses": out_courses,
            "badges": sorted(out_badges, key=lambda b: (b["awarded_at"], b["course"], b["badge_id"])),
            "recent": await _recent(ctx), "last_import": await _last_import(ctx)}


async def _recent(ctx: Ctx) -> list[dict]:
    """最近 20 条生效事件；账号级清空之前的事件不显示。"""
    s, uid = ctx.db, ctx.user.id
    last_reset = (select(ProgressReset.course, func.max(ProgressReset.reset_at).label("at"))
                  .where(ProgressReset.user_id == uid).group_by(ProgressReset.course).subquery())
    q = (select(ProgressEvent).outerjoin(last_reset, last_reset.c.course == ProgressEvent.course)
         .where(ProgressEvent.user_id == uid, ProgressEvent.status.in_(("applied", "raised")),
                or_(last_reset.c.at.is_(None), ProgressEvent.received_at > last_reset.c.at))
         .order_by(ProgressEvent.received_at.desc(), ProgressEvent.id.desc()).limit(RECENT))
    cs = courses()
    out = []
    for e in (await s.execute(q)).scalars():
        item = cs[e.course].items.get(e.item_id) if e.course in cs else None
        if item:
            out.append({"at": iso(e.client_ts), "course": e.course, "chapter_id": item.chapter, "page_id": item.page,
                        "item_id": e.item_id, "kind": e.kind,
                        "amt": None if e.amt is None else min(e.amt, item.max_xp)})
    return out


async def _last_import(ctx: Ctx) -> dict | None:
    imp = (await ctx.db.execute(select(Import).where(Import.user_id == ctx.user.id)
                                .order_by(Import.created_at.desc(), Import.id.desc()).limit(1))).scalar()
    if not imp:
        return None
    r = imp.result
    return {"imported_at": r["imported_at"], "course": imp.course, "items_added": r["items_added"],
            "xp_delta": r["xp_after"] - r["xp_before"]}
