"""内容导入：从课程根目录（COURSE_DIR）自动发现课程，生成 courses.json + items-<id>.json。

用法（在 backend/ 下）：
    uv run python scripts/build_content.py [--src <课程根目录>] [--out content]
--src 默认取环境变量 COURSE_DIR，再默认仓库同级的 ../course-content。
每门课目录下的 course.json 决定 id、标题、存储键与引擎：
- engine=course-manifest-js：读 assets/course-manifest.js，逐项 XP 来自无头浏览器调用 Course.inventory()，
  依赖 node、google-chrome（或 CHROME）与 <课程根>/shared/tools（puppeteer-core）；与清单交叉校验。
- engine=static：按 course.json 的 chapters 静态解析页面（不需要浏览器）。
任一不一致即失败（退出码 2）。
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from app.catalog import CatalogError, CourseSource, course_root, discover  # noqa: E402
from app.content import BASE_BADGES, GRAD_BADGE, LEVELS  # noqa: E402

# inventory 类型 → 后端类型（content.NON_PRACTICE_TYPES 用 "boss" 表示 Boss 阶段/通关/完美）
TYPE_MAP = {"boss-stage": "boss", "boss-clear": "boss", "boss-perfect": "boss"}
KNOWN_TYPES = {"done", "rec", "track", "boss", "quiz", "numeric", "sort", "bucket", "match", "scenario",
               "fill", "spot", "codespot", "experiment", "pointpick", "sim"}  # course.js TAGS + quiz/sim
DONE_CLASSES = {"done-check", "xt-check"}  # 小节完成 / 读完打卡
STATIC_XP = {"done": 10, "default": 10, "boss_stage": 20, "boss_clear": 50, "boss_perfect": 30}
TAG = re.compile(r'<(\w+)\b([^>]*?\bdata-id="([^"]+)"[^>]*)>')


def read_manifest(root: Path) -> dict:
    txt = (root / "assets/course-manifest.js").read_text(encoding="utf-8")
    txt = txt[txt.index("window.COURSE_MANIFEST=") + len("window.COURSE_MANIFEST="):].strip().rstrip(";")
    return json.loads(txt)


def home_page(root: Path) -> str | None:
    m = re.search(r"HOME_PAGE='([^']+)'", (root / "assets/course.js").read_text(encoding="utf-8"))
    return m.group(1) if m else None


def grad_list(root: Path) -> list[str] | None:
    """部分引擎版本的 course.js 在 gradOK 写死参与毕业判定的章（['01','02','03','04']），没有 HOME_PAGE。"""
    m = re.search(r"function gradOK\(\)\{.*?\[((?:'[^']+',?)+)\]\.forEach", (root / "assets/course.js").read_text(encoding="utf-8"), re.S)
    return re.findall(r"'([^']+)'", m.group(1)) if m else None


def js_array(root: Path, name: str) -> list:
    """读取 course.js 里的字面量数组（var BADGES=[...]; / var LEVELS=[...];），单引号转 JSON。"""
    txt = (root / "assets/course.js").read_text(encoding="utf-8")
    m = re.search(rf"var {name}=(\[.*?\]\]);", txt, re.S)
    return json.loads(m.group(1).replace("'", '"'))


def html_badges(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    """清单不带 badges 的引擎版本：徽章写在元素的 data-badge 上。返回 ({boss id: 徽章}, {组件 id: 徽章})。
    course.js：Boss 通关 grant(data-badge)；普通组件不看答案做对时 grant(data-badge)。"""
    boss, comp = {}, {}
    for f in sorted(root.glob("*.html")):
        for m in re.finditer(r'<\w+\b([^>]*\bdata-badge="([^"]+)"[^>]*)>', f.read_text(encoding="utf-8")):
            cls = (re.search(r'class="([^"]*)"', m.group(1)) or [None, ""])[1].split()
            did = re.search(r'data-id="([^"]+)"', m.group(1))
            if did:
                (boss if "boss" in cls else comp)[did.group(1)] = m.group(2)
    return boss, comp


def storage_key(root: Path, course_id: str) -> tuple[str, int]:
    """localStorage 键与 blank() 的 version：course.js 有 var KEY 时取它，否则 COURSE_ID+'-v1'。"""
    txt = (root / "assets/course.js").read_text(encoding="utf-8")
    m = re.search(r"var KEY='([^']+)'", txt)
    v = int(re.search(r"function blank\(\)\{return \{version:(\d+)", txt).group(1))
    return (m.group(1) if m else f"{course_id}-v1"), v


def _grads(cs: CourseSource, root: Path | None) -> tuple[str | None, list[str] | None]:
    """毕业判定范围：course.json 的 home_chapter / graduation_chapters 优先，缺省时读 course.js。"""
    m = cs.manifest
    home = m.get("home_chapter", home_page(root) if root else None)
    grads = m.get("graduation_chapters", grad_list(root) if root else None)
    return home, grads


def _attr(attrs: str, name: str) -> str | None:
    m = re.search(rf'\b{name}="([^"]*)"', attrs)
    return m.group(1) if m else None


def _finish(cs: CourseSource, items: list[dict], cpages: dict, chapters: dict, badges: list, extra: dict) -> dict:
    m = cs.manifest
    digest = hashlib.sha256(json.dumps(
        {"items": items, "pages": cpages, "badges": badges}, ensure_ascii=False, sort_keys=True
    ).encode()).hexdigest()[:12]
    meta = {"course_id": m.get("course_id", cs.id), "storage_key": cs.storage_key, "title": m["title"],
            "content_version": f"{cs.id}-{digest}", "total": sum(i["max_xp"] for i in items), "chapters": chapters,
            "pages": cpages, "badges": badges, "dir": cs.dir.name, "order": m["order"],
            "state_version": m["state_version"]}
    meta.update(extra)
    return meta


def build_static(cs: CourseSource, problems: list[str]) -> tuple[dict, list[dict]]:
    """engine=static：每章一页，页面上的 data-id 即计分项（口径同 course.js inventory）。"""
    m, code = cs.manifest, cs.id
    xpdef = {**STATIC_XP, **m.get("xp", {})}
    defs = {b[0]: b for b in m.get("badges", []) or []}
    home, grads = _grads(cs, None)
    items, seen, chapters, cpages, badges = [], {}, {}, {}, []

    def add(iid, ch, typ, xp, f):
        if iid in seen:
            problems.append(f"{code}：id {iid} 在 {seen[iid]} 与 {f} 重复"); return
        seen[iid] = f
        items.append({"id": iid, "page": ch, "type": typ, "max_xp": int(xp)})

    for ch in m["chapters"]:
        cid, f = ch["id"], ch["file"]
        html = (cs.dir / f).read_text(encoding="utf-8")
        tags = [(t.start(), set((_attr(t.group(2), "class") or "").split()), t.group(3), t.group(2))
                for t in TAG.finditer(html)]
        bosses = [(pos, iid, a) for pos, cls, iid, a in tags if "boss" in cls]
        if len(bosses) > 1:
            problems.append(f"{code} {f}：一页最多一个 Boss")
        boss = bosses[0][1] if bosses else None
        sections = []
        for pos, cls, iid, a in tags:
            if "boss" in cls or (boss and iid.startswith(boss + "-")):
                continue  # Boss 本身另行登记；Boss 关内题不入清单
            if not iid.startswith(cid + "-"):
                problems.append(f"{code} {f}：id {iid} 须以章号 {cid}- 开头"); continue
            xp = _attr(a, "data-xp")
            if "track" in cls:
                add(iid, cid, "track", 0, f)
            elif cls & DONE_CLASSES:
                add(iid, cid, "done", xp or xpdef["done"], f); sections.append(iid)
            elif cls & KNOWN_TYPES:
                typ = sorted(cls & KNOWN_TYPES)[0]
                add(iid, cid, typ, xp or xpdef.get(typ, xpdef["default"]), f)
        entry = {"sections": sections, "boss": boss}
        if boss:
            pos, _, a = bosses[0]
            n = len(re.findall(r'class="stage[" ]', html[pos:]))
            if not n:
                problems.append(f"{code} {f}：Boss {boss} 没有 .stage")
            for k in range(1, n + 1):
                add(f"{boss}-s{k}", cid, "boss", xpdef["boss_stage"], f)
            add(f"{boss}-clear", cid, "boss", xpdef["boss_clear"], f)
            add(f"{boss}-perfect", cid, "boss", xpdef["boss_perfect"], f)
            bid = _attr(a, "data-badge")
            if bid and bid in defs:
                entry["badge"] = bid; badges.append(list(defs[bid]))
            else:
                problems.append(f"{code} {f}：Boss {boss} 的徽章 {bid} 未在 course.json badges 中定义")
        if cid == home:
            entry["graduation"] = False  # 目录首页：Boss/徽章照常，不参与毕业判定
        elif grads is not None and cid not in grads:
            entry["graduation"] = False
        chapters[cid] = ch["title"]
        cpages[cid] = entry
    for i in items:
        if i["max_xp"] <= 0 and i["type"] != "track":
            problems.append(f"{code}：{i['id']} max_xp 缺失或为 0")
    extra = {"base_badges": m.get("base_badges", BASE_BADGES), "grad_badge": m.get("grad_badge", GRAD_BADGE),
             "levels": m.get("levels", [list(x) for x in LEVELS]), "item_badges": m.get("item_badges", {})}
    return _finish(cs, items, cpages, chapters, badges, extra), items


INVENTORY_CACHE = ".xiaotuo-inventory.json"
WRITE_CACHE = False


def source_digest(root: Path) -> str:
    """页面与引擎脚本的摘要：缓存只在课程内容未变时有效。"""
    h = hashlib.sha256()
    for f in sorted(root.glob("*.html")) + [root / "assets/course.js", root / "assets/course-manifest.js"]:
        h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def inventory(cs: CourseSource, problems: list[str]) -> list | None:
    """engine=course-manifest-js 的逐页清单。课程目录里有与当前内容一致的缓存时直接用（容器内无浏览器），
    否则调用无头浏览器；--write-cache 时把结果写回课程目录。"""
    root = cs.dir
    digest = source_digest(root)
    cache = root / INVENTORY_CACHE
    if cache.is_file() and not WRITE_CACHE:
        c = json.loads(cache.read_text(encoding="utf-8"))
        if c.get("source_digest") == digest:
            return c["pages"]
    try:
        raw = subprocess.run(["node", str(HERE / "inventory.cjs"), str(root.parent), root.name],
                             check=True, capture_output=True, text=True, timeout=300).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        problems.append(f"{cs.id}：课程目录没有有效的 {INVENTORY_CACHE}，且无法运行无头浏览器生成清单（{e}）。"
                        f"请在装有 node 与 Chrome 的环境运行 build_content.py --write-cache")
        return None
    pages = json.loads(raw)
    if WRITE_CACHE:
        cache.write_text(json.dumps({"source_digest": digest, "pages": pages}, ensure_ascii=False) + "\n", encoding="utf-8")
    return pages


def build(cs: CourseSource, problems: list[str]) -> tuple[dict, list[dict]]:
    if cs.manifest["engine"] == "static":
        return build_static(cs, problems)
    code, root = cs.id, cs.dir
    man = read_manifest(root)
    home, grads = _grads(cs, root)
    js_badges = js_array(root, "BADGES")
    boss_badge, comp_badge = html_badges(root) if "badges" not in man else ({}, {})
    pages = inventory(cs, problems)
    if pages is None:
        return {}, []
    items, seen, badge_of = [], {}, {}
    for p in pages:
        inv = p["inv"]
        if not inv:
            problems.append(f"{code} {p['file']}：没有 Course.inventory()"); continue
        for e in p["errors"]:
            problems.append(f"{code} {p['file']}：JS 报错 {e}")
        page_id = inv.get("subpage") or inv["page"]
        if "badges" in inv:
            for b in inv["badges"]:
                badge_of.setdefault(inv["page"], b)
        elif inv.get("boss") in boss_badge:  # inventory 不带徽章的引擎版本：取 Boss 元素的 data-badge
            b = next((b for b in js_badges if b[0] == boss_badge[inv["boss"]]), None)
            if b:
                badge_of.setdefault(inv["page"], b)
            else:
                problems.append(f"{code} {p['file']}：Boss 徽章 {boss_badge[inv['boss']]} 不在 BADGES 里")
        for it in inv["items"]:
            if it["id"] in seen:
                problems.append(f"{code}：id {it['id']} 在 {seen[it['id']]} 与 {p['file']} 重复"); continue
            seen[it["id"]] = p["file"]
            items.append({"id": it["id"], "page": page_id, "type": TYPE_MAP.get(it["type"], it["type"]),
                          "max_xp": int(it["xp"])})
        # input.track（state.rec，0 XP）不在 inventory 里，但外壳会上报 kind=rec，须登记为 track/0
        for tid in p.get("tracks", []):
            if tid in seen:
                problems.append(f"{code}：id {tid} 在 {seen[tid]} 与 {p['file']} 重复"); continue
            seen[tid] = p["file"]
            items.append({"id": tid, "page": page_id, "type": "track", "max_xp": 0})
    # 交叉校验清单
    total = sum(i["max_xp"] for i in items)
    if total != man["total"]:
        problems.append(f"{code}：items 合计 {total} ≠ 清单 total {man['total']}")
    chapters, cpages = {}, {}
    for ch, pg in man["pages"].items():
        ids = [i for i in items if i["page"].split("-")[0] == ch and i["type"] != "track"]
        if "ids" in pg:
            if [i["id"] for i in ids] != pg["ids"] and sorted(i["id"] for i in ids) != sorted(pg["ids"]):
                problems.append(f"{code} {ch}：items id 集合与清单 ids 不一致")
        elif len(ids) != pg["items"]:  # 部分引擎版本的清单只给条目数
            problems.append(f"{code} {ch}：items {len(ids)} 项 ≠ 清单 {pg['items']} 项")
        if sorted(i["id"] for i in ids if i["type"] == "done") != sorted(pg["sections"]):
            problems.append(f"{code} {ch}：done 项与清单 sections 不一致")
        if sum(i["max_xp"] for i in ids) != pg["xp"]:
            problems.append(f"{code} {ch}：XP {sum(i['max_xp'] for i in ids)} ≠ 清单 {pg['xp']}")
        chapters[ch] = re.sub(r"^\S+\s*·\s*", "", pg["title"].split("|")[0]).strip()
        entry = {"sections": pg["sections"], "boss": pg["boss"]}
        if ch == home:
            if not pg["boss"]:
                continue  # 无 Boss 的目录首页不进 pages
            entry["graduation"] = False  # course.js gradOK 排除 HOME_PAGE；Boss/徽章照常
        elif home is None and grads is not None and ch not in grads:
            entry["graduation"] = False  # 不在毕业章列表里的章不参与
        if pg["boss"]:
            b = badge_of.get(ch)
            if b:
                entry["badge"] = b[0]
            else:
                problems.append(f"{code} {ch}：有 Boss 但没有徽章")
        cpages[ch] = entry
    man_badges = man.get("badges") or [list(b) for b in badge_of.values()]
    if [b[0] for b in man_badges] != [b[0] for b in badge_of.values()] and \
            sorted(map(tuple, man_badges)) != sorted(map(tuple, badge_of.values())):
        problems.append(f"{code}：徽章与清单不一致")
    for i in items:
        if i["type"] not in KNOWN_TYPES:
            problems.append(f"{code}：未知类型 {i['type']}（{i['id']}）")
        if i["max_xp"] <= 0 and i["type"] != "track":
            problems.append(f"{code}：{i['id']} max_xp 缺失或为 0")
    key, state_version = storage_key(root, cs.manifest.get("course_id", code))
    if state_version != cs.manifest["state_version"]:
        problems.append(f"{code}：course.json state_version {cs.manifest['state_version']} 与 course.js blank() 的 {state_version} 不一致")
    if "storage_key" in cs.manifest and key != cs.storage_key and re.search(r"var KEY='", (root / "assets/course.js").read_text(encoding="utf-8")):
        problems.append(f"{code}：course.json storage_key 与 course.js KEY 不一致")
    # 快照格式、等级名、非 Boss 徽章随课程引擎走，统一写入生成物，后端不再内置课程专属文案
    boss_ids = {b[0] for b in man_badges}
    extra = {"base_badges": [b for b in js_badges if b[0] not in boss_ids and b[0] != "grad"],
             "grad_badge": next((b for b in js_badges if b[0] == "grad"), GRAD_BADGE),
             "levels": js_array(root, "LEVELS"), "item_badges": comp_badge}
    for iid, b in comp_badge.items():
        if iid not in seen or not any(x[0] == b for x in js_badges):
            problems.append(f"{code}：组件徽章 {b}（{iid}）的组件或徽章定义不存在")
    return _finish(cs, items, cpages, chapters, man_badges, extra), items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None, help="课程根目录，默认 $COURSE_DIR 或 ../course-content")
    ap.add_argument("--out", default=str(HERE.parent / "content"))
    ap.add_argument("--write-cache", action="store_true",
                    help=f"engine=course-manifest-js：用浏览器重新生成清单并写入课程目录的 {INVENTORY_CACHE}")
    a = ap.parse_args()
    global WRITE_CACHE
    WRITE_CACHE = a.write_cache
    out = Path(a.out)
    try:
        sources = discover(a.src)
    except CatalogError as e:
        print(e, file=sys.stderr)
        return 2
    print(f"课程根目录：{course_root(a.src)}，发现 {len(sources)} 门课")
    problems, meta = [], {}
    for cs in sources:
        code = cs.id
        m, items = build(cs, problems)
        if not m:
            continue
        meta[code] = m
        if not problems:
            out.mkdir(parents=True, exist_ok=True)
            (out / f"items-{code}.json").write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{code}: {len(items)} 项 / {m['total']} XP / version {m['content_version']}")
        for ch in m["chapters"]:
            ci = [i for i in items if i["page"].split("-")[0] == ch]
            print(f"  {ch} {m['chapters'][ch]}: {len(ci)} 项 / {sum(i['max_xp'] for i in ci)} XP"
                  f" / Boss {m['pages'].get(ch, {}).get('boss') or '—'}")
    if problems:
        print("问题：\n- " + "\n- ".join(problems), file=sys.stderr)
        return 2
    (out / "courses.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
