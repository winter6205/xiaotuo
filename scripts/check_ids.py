#!/usr/bin/env python3
"""id 只增不删检查：对比课程页面中的 data-id 与 section id 与本地基线。
课程由 COURSE_DIR（默认仓库同级的 ../course-content）自动发现。
基线 baseline/course-ids.json 只在本地（已加入 .gitignore）：首次运行自动生成，之后每次对比。
用法：check_ids.py [--update]   (--update 重写基线)"""
from __future__ import annotations
import json, sys
from collections import Counter
from pathlib import Path
from _common import CatalogError, ROOT, courses, pages, parse

BASELINE = Path(__file__).resolve().parents[1] / "baseline" / "course-ids.json"


def collect(found: dict[str, Path]) -> tuple[dict, list[str]]:
    out, errors = {}, []
    for c, d in found.items():
        data_ids: Counter = Counter()
        sections: Counter = Counter()
        for p in pages(d):
            pp = parse(p)
            data_ids.update(pp.data_ids)  # 进度 id 在一门课内须全局唯一
            sections.update(f"{p.name}#{s}" for s in pp.section_ids)  # 锚点按页唯一
        errors += [f"{c}: data-id 重复 {i} x{n}" for i, n in data_ids.items() if n > 1]
        errors += [f"{c}: section id 重复 {i} x{n}" for i, n in sections.items() if n > 1]
        out[c] = {"data_ids": sorted(data_ids), "section_ids": sorted(sections)}
    return out, errors


def main() -> int:
    try:
        found = courses()
    except CatalogError as e:
        print(f"{e}\n（课程根目录 {ROOT}，可用 COURSE_DIR 指定）"); return 2
    cur, errors = collect(found)
    if "--update" in sys.argv or not BASELINE.is_file():
        if errors:
            print("\n".join(errors)); return 1
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(cur, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"基线已写入 {BASELINE}")
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    for c in cur:
        for k in ("data_ids", "section_ids"):
            removed = sorted(set(base.get(c, {}).get(k, [])) - set(cur[c][k]))
            added = set(cur[c][k]) - set(base.get(c, {}).get(k, []))
            errors += [f"{c}: {k} 被删除 {i}" for i in removed]
            print(f"{c}: {k} 当前 {len(cur[c][k])}，基线 {len(base.get(c,{}).get(k,[]))}，新增 {len(added)}，删除 {len(removed)}")
    if errors:
        print("FAIL\n" + "\n".join(errors)); return 1
    print("OK"); return 0


if __name__ == "__main__":
    sys.exit(main())
