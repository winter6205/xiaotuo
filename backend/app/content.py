"""课程内容元数据（scripts/build_content.py 从 COURSE_DIR 生成，启动时载入内存，不入库）。

目录 settings.content_dir 下：
- courses.json：{"<课程 id>": {"course_id", "storage_key", "title", "content_version", "total", "dir", "order",
                              "state_version", "chapters": {"01": "章名"},
                              "pages": {"01": {"sections": [...], "boss": "01-boss", "badge": "boss01"}},
                              "badges": [[id, icon, name, desc], ...],
                              "base_badges", "grad_badge", "levels", "item_badges"}}
  pages 列各章；"graduation": false 的章（目录首页等）不参与 grad 判定，但其 Boss 通关、徽章、has_boss 照常计算。
  badges 为 Boss 徽章；base_badges / grad_badge / levels 缺省时用下方通用默认值。
- items-<课程 id>.json：[{"id", "page", "type", "max_xp"}, ...]
"""
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.config import settings

# 通用默认值：课程未在清单中提供时使用。Boss 徽章插在 grad 之前
BASE_BADGES = [
    ["first", "🐣", "第一步", "完成任意一节"],
    ["streak3", "🔥", "三天连学", "连学天数达到 3"],
    ["streak7", "🏅", "七天连学", "连学天数达到 7"],
    ["comeback", "💪", "越挫越勇", "累计 5 道题先答错再改对"],
]
GRAD_BADGE = ["grad", "🎓", "全课毕业", "参与毕业判定的各章小节和 Boss 都完成"]
LEVELS = [(1, "入门", 0), (2, "起步", 100), (3, "进阶", 300),
          (4, "熟练", 600), (5, "精通", 1000), (6, "毕业", None)]
# 这些类型不是练习组件，快照不为其补 solved
NON_PRACTICE_TYPES = {"done", "rec", "track", "boss"}


@dataclass
class Item:
    id: str
    page: str
    type: str
    max_xp: int

    @property
    def chapter(self) -> str:
        return self.page.split("-")[0]


@dataclass
class Course:
    code: str
    course_id: str
    storage_key: str
    title: str
    content_version: str
    total: int
    chapters: dict[str, str]
    pages: dict[str, dict]
    items: dict[str, Item]
    badges: list[list[str]] = field(default_factory=list)
    dir: str = ""     # 课程根目录下的子目录名（static.py 据此提供 /course/<id>/）
    order: float = 0
    state_version: int = 1
    base_badges: list[list[str]] = field(default_factory=lambda: BASE_BADGES)
    grad_badge: list[str] = field(default_factory=lambda: GRAD_BADGE)
    levels: list[tuple] = field(default_factory=lambda: LEVELS)
    item_badges: dict[str, str] = field(default_factory=dict)  # 组件 id → 不看答案做对即得的徽章

    @property
    def grad_pages(self) -> dict[str, dict]:
        """参与 grad 判定的章（course.js gradOK 排除 HOME_PAGE）。"""
        return {k: pg for k, pg in self.pages.items() if pg.get("graduation", True)}

    @property
    def all_badges(self) -> list[list[str]]:
        return self.base_badges + self.badges + [self.grad_badge]

    def badge(self, badge_id: str) -> list[str] | None:
        return next((b for b in self.all_badges if b[0] == badge_id), None)

    def level(self, xp: int) -> dict:
        lv6 = max(1001, int(self.total * 0.9 + 0.5)) if self.total else None  # JS Math.round
        cur, nxt = tuple(self.levels[0]), None
        for lv, name, mn in self.levels:
            mn = lv6 if lv == 6 else mn
            if mn is None:
                break
            if xp >= mn:
                cur = (lv, name, mn)
            else:
                nxt = (lv, name, mn)
                break
        return {"level": cur[0], "level_name": cur[1], "level_min_xp": cur[2],
                "next_level_xp": nxt[2] if nxt else None, "next_level_name": nxt[1] if nxt else None}


@lru_cache
def courses() -> dict[str, Course]:
    root = Path(settings.content_dir)
    meta = json.loads((root / "courses.json").read_text(encoding="utf-8"))
    out = {}
    for code, m in meta.items():
        raw = json.loads((root / f"items-{code}.json").read_text(encoding="utf-8"))
        items = {i["id"]: Item(i["id"], i["page"], i.get("type", ""), int(i["max_xp"])) for i in raw}
        out[code] = Course(code, m["course_id"], m["storage_key"], m["title"], m.get("content_version", ""),
                           int(m.get("total") or sum(i.max_xp for i in items.values())),
                           m.get("chapters", {}), m.get("pages", {}), items, m.get("badges", []),
                           **{k: m[k] for k in ("dir", "order", "state_version", "base_badges", "grad_badge", "item_badges") if k in m},
                           **({"levels": [tuple(lv) for lv in m["levels"]]} if "levels" in m else {}))
    return dict(sorted(out.items(), key=lambda kv: (kv[1].order, kv[0])))


def default_course() -> str | None:
    """order 最小的课（GET /api/me 的 default_course）。"""
    return next(iter(courses()), None)


def get_course(code: str) -> Course | None:
    return courses().get(code)
