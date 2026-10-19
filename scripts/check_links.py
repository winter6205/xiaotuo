#!/usr/bin/env python3
"""死链检查：渲染页中的相对链接与资源（href/src）须指向存在的文件；带 #锚点 的 HTML 链接须锚点存在。"""
from __future__ import annotations
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
from _common import courses, pages, parse, ROOT

SKIP_SCHEMES = {"http", "https", "mailto", "tel", "javascript", "data"}


def main() -> int:
    cache: dict[Path, object] = {}
    def P(p):
        if p not in cache: cache[p] = parse(p)
        return cache[p]
    bad, n = [], 0
    for c, d in courses().items():
        for page in pages(d):
            for attr, url in P(page).links:
                u = urlsplit(url)
                if u.scheme in SKIP_SCHEMES or url.startswith("//") or not url.strip():
                    continue
                n += 1
                target = page if not u.path else (page.parent / unquote(u.path)).resolve()
                if not target.exists():
                    bad.append(f"{page.relative_to(ROOT)}: {attr}={url} 文件不存在"); continue
                if u.fragment and target.suffix == ".html" and unquote(u.fragment) not in P(target).anchors:
                    bad.append(f"{page.relative_to(ROOT)}: {attr}={url} 锚点不存在")
    print(f"检查页面 {len(cache)}，相对链接/资源 {n}，死链 {len(bad)}")
    if bad:
        print("FAIL\n" + "\n".join(bad)); return 1
    print("OK"); return 0


if __name__ == "__main__":
    sys.exit(main())
