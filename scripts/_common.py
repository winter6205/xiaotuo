"""共享：解析课程页面 HTML（只读课程根目录 COURSE_DIR，默认仓库同级的 ../course-content）。"""
from __future__ import annotations
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from xiaotuo.catalog import CatalogError, course_root, discover  # noqa: E402,F401

ROOT = course_root()


def courses() -> dict[str, Path]:
    """自动发现的课程：{课程 id: 课程目录}。"""
    return {c.id: c.dir for c in discover(ROOT)}
EXCLUDE_CLASSES = {"actor"}  # 时序图角色，非进度 id


def pages(course_dir: Path) -> list[Path]:
    return sorted(course_dir.glob("*.html"))


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.svg_depth = 0
        self.data_ids: list[str] = []
        self.section_ids: list[str] = []
        self.anchors: set[str] = set()
        self.links: list[tuple[str, str]] = []  # (attr, url)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "svg":
            self.svg_depth += 1
        if a.get("id"):
            self.anchors.add(a["id"])
        if tag == "a" and a.get("name"):
            self.anchors.add(a["name"])
        if tag == "section" and a.get("id"):
            self.section_ids.append(a["id"])
        did = a.get("data-id")
        cls = set((a.get("class") or "").split())
        if did and self.svg_depth == 0 and not cls & EXCLUDE_CLASSES:
            self.data_ids.append(did)
        for k in ("href", "src"):
            if a.get(k):
                self.links.append((k, a[k]))

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        if tag == "svg" and self.svg_depth:
            self.svg_depth -= 1


def parse(p: Path) -> PageParser:
    pp = PageParser()
    pp.feed(p.read_text(encoding="utf-8"))
    return pp
