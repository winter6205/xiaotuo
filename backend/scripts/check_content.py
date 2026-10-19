"""id 双向检查：content/items-*.json ↔ 课程页面（静态解析 HTML，不依赖浏览器）。

1) 内容 → 页面：每个 item id 在页面上有对应 data-id；Boss 派生 id（<boss>-sN / -clear / -perfect）
   要求 <boss> 存在且 N ≤ 该 Boss 的 .stage 数。
2) 页面 → 内容：每个交互元素（class 含组件类型或 done-check）的 data-id 都在 items 里；
   Boss 内部的题目（id 以 <boss>- 开头）按 course.js 不单独计分，跳过。
课程由课程根目录（--src，默认 $COURSE_DIR 或 ../course-content）自动发现。
用法：uv run python scripts/check_content.py [--src <课程根目录>] [--content content]；有问题退出码 2。
"""
import argparse, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.catalog import CatalogError, discover  # noqa: E402

COMP = {"done-check", "xt-check", "quiz", "numeric", "sim", "sort", "bucket", "match", "scenario", "fill", "spot",
        "codespot", "experiment", "pointpick", "track", "rec"}
TAG = re.compile(r'<(\w+)\b([^>]*?\bdata-id="([^"]+)"[^>]*)>')


def scan(root: Path):
    ids, bosses = {}, {}
    for f in sorted(root.glob("*.html")):
        html = f.read_text(encoding="utf-8")
        for m in TAG.finditer(html):
            cls = set((re.search(r'class="([^"]*)"', m.group(2)) or [None, ""])[1].split())
            ids.setdefault(m.group(3), (f.name, cls))
            if "boss" in cls:
                rest = html[m.end():]
                end = re.search(r'<(?:div|section)[^>]*class="[^"]*\bboss\b', rest)
                bosses[m.group(3)] = len(re.findall(r'class="stage[" ]', rest[:end.start()] if end else rest))
    return ids, bosses


def check(code, course_dir, content):
    f = content / f"items-{code}.json"
    if not f.is_file():
        return [f"{code}：缺少 {f.name}（先运行 build_content.py）"]
    items = {i["id"] for i in json.loads(f.read_text(encoding="utf-8"))}
    ids, bosses = scan(course_dir)
    bad = []
    for i in sorted(items):
        if i in ids:
            continue
        m = re.match(r"(.+)-(?:s(\d+)|clear|perfect)$", i)
        if m and m.group(1) in bosses and (not m.group(2) or int(m.group(2)) <= bosses[m.group(1)]):
            continue
        bad.append(f"{code} 内容→页面：{i} 在页面上找不到")
    for i, (f, cls) in sorted(ids.items()):
        if not (cls & COMP) or i in items or any(i.startswith(b + "-") for b in bosses):
            continue
        bad.append(f"{code} 页面→内容：{f} 的 {i}（{' '.join(sorted(cls))}）不在 items 里")
    n_inter = sum(1 for i, (_, c) in ids.items() if c & COMP)
    print(f"{code}: items {len(items)}，页面交互 id {n_inter}，Boss {len(bosses)}（阶段 {sum(bosses.values())}）")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None)
    ap.add_argument("--content", default=str(Path(__file__).resolve().parent.parent / "content"))
    a = ap.parse_args()
    try:
        sources = discover(a.src)
    except CatalogError as e:
        print(e, file=sys.stderr)
        return 2
    bad = [b for c in sources for b in check(c.id, c.dir, Path(a.content))]
    print("问题：\n- " + "\n- ".join(bad) if bad else "✅ 双向一致")
    return 2 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
