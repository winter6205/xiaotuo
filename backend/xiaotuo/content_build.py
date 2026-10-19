"""课程内容生成与校验（原 scripts/build_content.py、scripts/check_content.py 的实现，随包分发，CLI 进程内调用）。

从课程根目录（COURSE_DIR）自动发现课程，生成到内容目录（CONTENT_DIR）：
- courses.json + items-<id>.json：后端计分元数据（见 content.py）；
- catalog.json：前端课程目录 {"version", "courses": [CourseMeta]}，由 GET /api/courses 原样提供。
  CourseMeta 由各课 course.json 与页面生成，并与计分清单做 id 对照；示例课程的输出由 tests/fixtures/catalog-examples.json 固定。

每门课目录下的 course.json 决定 id、标题、存储键与引擎：
- engine=course-manifest-js：读 assets/course-manifest.js，逐项 XP 来自无头浏览器调用 Course.inventory()，
  依赖 node、google-chrome（或 CHROME）与 <课程根>/shared/tools（puppeteer-core）；与清单交叉校验。
  课程目录里有与内容一致的 .xiaotuo-inventory.json 缓存时直接使用（容器、CLI 环境没有浏览器）。
- engine=static：按 course.json 的 chapters 静态解析页面（不需要浏览器）。
任一不一致即失败（退出码 2）。
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from xiaotuo.catalog import CatalogError, CourseSource, course_root, discover
from xiaotuo.content import BASE_BADGES, GRAD_BADGE, LEVELS  # noqa: F401  BASE_BADGES 供外部沿用

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
    # static 课程的徽章表以清单为准：只有清单声明的 base_badges / grad_badge 才计入，缺省为空，
    # 不再隐式补入通用徽章（否则只定义 1 枚 Boss 徽章的课程会显示 x/6）
    extra = {"base_badges": m.get("base_badges", []), "grad_badge": m.get("grad_badge"),
             "levels": m.get("levels", [list(x) for x in LEVELS]), "item_badges": m.get("item_badges", {})}
    return _finish(cs, items, cpages, chapters, badges, extra), items


INVENTORY_CACHE = ".xiaotuo-inventory.json"
INVENTORY_JS = Path(__file__).resolve().parent / "inventory.cjs"


def source_digest(root: Path) -> str:
    """页面与引擎脚本的摘要：缓存只在课程内容未变时有效。"""
    h = hashlib.sha256()
    for f in sorted(root.glob("*.html")) + [root / "assets/course.js", root / "assets/course-manifest.js"]:
        h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def inventory(cs: CourseSource, problems: list[str], write_cache: bool = False) -> list | None:
    """engine=course-manifest-js 的逐页清单。课程目录里有与当前内容一致的缓存时直接用（容器内无浏览器），
    否则调用无头浏览器；--write-cache 时把结果写回课程目录。"""
    root = cs.dir
    digest = source_digest(root)
    cache = root / INVENTORY_CACHE
    if cache.is_file() and not write_cache:
        c = json.loads(cache.read_text(encoding="utf-8"))
        if c.get("source_digest") == digest:
            return c["pages"]
    try:
        raw = subprocess.run(["node", str(INVENTORY_JS), str(root.parent), root.name],
                             check=True, capture_output=True, text=True, encoding="utf-8", timeout=300).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        problems.append(f"{cs.id}：课程目录没有有效的 {INVENTORY_CACHE}，且无法运行无头浏览器生成清单（{e}）。"
                        f"engine=course-manifest-js 的课程须自带与当前内容一致的 {INVENTORY_CACHE}："
                        f"请在装有 node 与 Chrome 的环境运行 build_content.py --write-cache")
        return None
    pages = json.loads(raw)
    if write_cache:
        cache.write_text(json.dumps({"source_digest": digest, "pages": pages}, ensure_ascii=False) + "\n", encoding="utf-8")
    return pages


def build(cs: CourseSource, problems: list[str], write_cache: bool = False) -> tuple[dict, list[dict]]:
    if cs.manifest["engine"] == "static":
        return build_static(cs, problems)
    code, root = cs.id, cs.dir
    man = read_manifest(root)
    home, grads = _grads(cs, root)
    js_badges = js_array(root, "BADGES")
    boss_badge, comp_badge = html_badges(root) if "badges" not in man else ({}, {})
    pages = inventory(cs, problems, write_cache)
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



# ---------------- 双向检查（原 check_content.py） ----------------

COMP = {"done-check", "xt-check", "quiz", "numeric", "sim", "sort", "bucket", "match", "scenario", "fill", "spot",
        "codespot", "experiment", "pointpick", "track", "rec"}


def scan(root: Path):
    """页面上的交互 id 与 Boss 阶段数（check_content 用）。"""
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


def check_course(code: str, course_dir: Path, content: Path, log=print) -> list[str]:
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
    log(f"{code}: items {len(items)}，页面交互 id {n_inter}，Boss {len(bosses)}（阶段 {sum(bosses.values())}）")
    return bad



# ---------------- 前端课程目录 catalog.json ----------------
# 输出格式固定：字段顺序、缺省值、对象键顺序（与 JS 对象相同）与 JSON.stringify(…, null, 1) 的缩进；
# 前端 CourseMeta 依赖这一形状，示例课程的结果由 tests/fixtures/catalog-examples.json 逐字节固定。

_ID_TAG = re.compile(r'<\w+([^>]*?)data-id="([^"]+)"', re.ASCII)   # JS \w 只含 ASCII
_TRACK_IN = re.compile(r'<input[^>]*class="track"[^>]*data-id="([^"]+)"')
_STAGE = re.compile(r'class="stage[\s"]')
_UNDEF = object()   # JS undefined：JSON.stringify 时整个键省略


class CatalogBuildError(Exception):
    pass


def _nn(v, default):
    """JS 的 a ?? b：只有 null / undefined 才取默认值。"""
    return default if v is None or v is _UNDEF else v


def _js_keys(v):
    """按 JS 对象的键顺序重排（整数形式的键升序在前，其余保持插入顺序），递归处理；去掉 undefined。"""
    if isinstance(v, dict):
        def is_index(k):
            return isinstance(k, str) and k.isdigit() and (k == "0" or not k.startswith("0")) and int(k) < 2**32 - 1
        ints = sorted((k for k in v if is_index(k)), key=int)
        rest = [k for k in v if not is_index(k)]
        return {k: _js_keys(v[k]) for k in ints + rest if v[k] is not _UNDEF}
    if isinstance(v, list):
        return [None if x is _UNDEF else _js_keys(x) for x in v]
    return v


def _split_boss(html: str) -> tuple[str, str]:
    """Boss 节：<section id="boss"> 到其 </section>（Boss 节内不嵌套 section）。返回 (boss, rest)。"""
    at = html.find('<section id="boss"')
    close = -1 if at < 0 else html.find("</section>", at)
    end = -1 if close < 0 else close + len("</section>")
    if at < 0:
        return "", html
    return (html[at:end] if end >= 0 else html[at:]), html[:at] + ("" if end < 0 else html[end:])


def _page_ids(file: Path, boss_id, expect=None) -> list[str]:
    html = file.read_text(encoding="utf-8")
    boss, rest = _split_boss(html)
    ids = [m.group(2) for m in _ID_TAG.finditer(rest) if 'class="track"' not in m.group(1)]
    if boss_id and boss:
        n = len(_STAGE.findall(boss))
        ids += [f"{boss_id}-s{i}" for i in range(1, n + 1)] + [f"{boss_id}-clear", f"{boss_id}-perfect"]
    if expect is not None and len(ids) != expect:
        raise CatalogBuildError(f"{file}: 推出 {len(ids)} 个 id，manifest items={expect}")
    return ids


def _title(t: str) -> str:
    return re.split(r"\s*\|\s*", t)[0]


def _from_manifest_js(src: Path) -> dict:
    m = read_manifest(src)
    pages = []
    for pid, p in m["pages"].items():
        ids = p.get("ids")
        if ids is None:
            ids = _page_ids(src / p["file"], p.get("boss"), p.get("items"))
        pages.append({
            "id": pid, "file": p.get("file", _UNDEF), "title": _title(p["title"]), "xp": p.get("xp", _UNDEF),
            "sections": p.get("sections", _UNDEF), "boss": _nn(p.get("boss"), None), "ids": ids,
            "subs": [{"key": sp.get("key", _UNDEF), "file": sp.get("file", _UNDEF),
                      "title": re.sub(r"^\S+ · ", "", _title(sp["title"]), count=1),
                      "ids": _nn(sp.get("ids"), []), "boss": _nn(sp.get("boss"), None)}
                     for sp in _nn(p.get("subpages"), [])],
        })
    return {"generated": m.get("generated", _UNDEF), "total": m.get("total", _UNDEF),
            "anchors": m.get("anchors") or {}, "pages": pages}


def _from_static(src: Path, c: dict) -> dict:
    xp_def = {"done": 10, "quiz": 10, "check": 10, **_nn(c.get("xp"), {})}
    total, pages = 0, []
    for ch in c["chapters"]:
        f = src / ch["file"]
        boss, rest = _split_boss(f.read_text(encoding="utf-8"))
        m = re.search(r'class="boss"[^>]*data-id="([^"]+)"', boss) or re.search(r'data-id="([^"]+)"[^>]*class="boss"', boss)
        boss_id = m.group(1) if m else None
        ids = _page_ids(f, boss_id)
        xp = 0
        for t in _ID_TAG.finditer(rest):
            if 'class="track"' in t.group(1):
                continue
            own = re.search(r'data-xp="(\d+)"', t.group(1))
            parts = t.group(2).split("-")
            typ = "done" if "-done-" in t.group(2) else (parts[1] if len(parts) > 1 else None)
            xp += int(own.group(1)) if own else _nn(xp_def.get(typ) if typ is not None else None, xp_def["check"])
        if boss_id:
            xp += len(_STAGE.findall(boss)) * 20 + 80
        total += xp
        pages.append({"id": ch["id"], "file": ch["file"], "title": ch["title"], "xp": xp,
                      "sections": [i for i in ids if "-done-" in i], "boss": boss_id or None, "ids": ids, "subs": []})
    return {"generated": None, "total": total, "anchors": {}, "pages": pages}


def _check_ids(cid: str, engine: str, course: dict, back: list[dict], src: Path) -> None:
    """页面推出的 id 与计分清单对照：差异必须恰好是 0 XP 跟踪项；
    通过后各章 / 小节的 ids 改为清单里的计分项，static 课程的 xp / total 以清单为准。"""
    tracks = {m for f in src.iterdir() if f.name.endswith(".html")
              for m in _TRACK_IN.findall(f.read_text(encoding="utf-8"))}
    front = list(dict.fromkeys(i for p in course["pages"] for i in p["ids"]))
    back_ids = {x["id"] for x in back}
    extra = [i for i in front if i not in back_ids]
    front_set = set(front)
    missing = [x["id"] for x in back if x["id"] not in front_set]
    wrong = [i for i in missing if i not in tracks] + [i for i in tracks if i not in missing]
    if extra or wrong:
        raise CatalogBuildError(f"{cid}: 页面 id 与 items-{cid}.json 不一致，多出 [{','.join(extra)}]，"
                                f"非跟踪项差异 [{','.join(wrong)}]")

    def of(key):
        return [x["id"] for x in back if x["page"] == key and x["max_xp"] > 0]
    for p in course["pages"]:
        for sp in p["subs"]:
            sp["ids"] = of(sp["key"])
        p["ids"] = of(p["id"]) + [i for sp in p["subs"] for i in sp["ids"]]
    if engine == "static":
        def xp_of(key):
            return sum(x["max_xp"] for x in back if x["page"] == key)
        for p in course["pages"]:
            p["xp"] = xp_of(p["id"]) + sum(xp_of(sp["key"]) for sp in p["subs"])
        course["total"] = sum(p["xp"] for p in course["pages"])
    keys = {k for p in course["pages"] for k in [p["id"], *(sp["key"] for sp in p["subs"])]}
    n = sum(1 for x in back if x["page"] in keys)
    if n != len(back):
        raise CatalogBuildError(f"{cid}: 有 {len(back) - n} 个清单项的 page 不在章或小节里")


def _locale_key(s: str) -> str:
    """近似 JS localeCompare（ICU 根排序）在课程 id 字符集 [a-z0-9_] 上的顺序：_ < 数字 < 字母。"""
    return s.replace("_", "\x00")


def course_meta(cs: CourseSource, items: list[dict]) -> dict:
    """单门课的 CourseMeta（已与计分清单做 id 对照）。"""
    c, src = cs.manifest, cs.dir
    body = _from_static(src, c) if c["engine"] == "static" else _from_manifest_js(src)
    course = {
        "id": c["id"], "dir": src.name, "key": cs.storage_key, "title": c["title"],
        "name": _nn(c.get("name"), c["title"]), "short": _nn(c.get("short"), _nn(c.get("name"), c["title"])),
        "icon": _nn(c.get("icon"), "📘"), "order": c["order"], "accent": c["accent"],
        "accentLight": _nn(c.get("accent_light"), None), "accentDark": _nn(c.get("accent_dark"), None),
        "stateVersion": c["state_version"], "courseId": _nn(c.get("course_id"), None), "engine": c["engine"],
        "homeChapter": _nn(c.get("home_chapter"), None), "graduation": _nn(c.get("graduation_chapters"), None),
        **body,
    }
    _check_ids(c["id"], c["engine"], course, items, src)
    return _js_keys(course)


def dumps_courses(courses: list[dict]) -> str:
    """与 JSON.stringify(data, null, 1) 相同的文本（无结尾换行）。"""
    return json.dumps(courses, ensure_ascii=False, indent=1)


def catalog_doc(courses: list[dict]) -> dict:
    """catalog.json 内容。version 取整个 courses 文本的 sha256 前 12 位：任何字段变化（含标题、主题色）都会换版本，
    GET /api/courses 的 ETag 即由它生成。"""
    courses = sorted(courses, key=lambda x: (x["order"], _locale_key(x["id"])))
    return {"version": hashlib.sha256(dumps_courses(courses).encode()).hexdigest()[:12], "courses": courses}


# ---------------- 入口：生成与检查（scripts/*.py 与 CLI 共用） ----------------

def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr)


def build_content(src, out, *, write_cache: bool = False, allow_empty: bool = False, log=print, err=None) -> int:
    """生成 courses.json、items-<id>.json、catalog.json。返回退出码：0 成功；2 清单或内容有问题。
    allow_empty：课程根目录里没有课程时照样写出空目录（CLI 与容器入口用；脚本默认仍视为错误，需显式 --allow-empty）。"""
    err = err or _stderr
    out = Path(out)
    try:
        sources = discover(src, allow_empty=allow_empty)
    except CatalogError as e:
        err(str(e))
        return 2
    log(f"课程根目录：{course_root(src)}，发现 {len(sources)} 门课")
    problems, meta, built = [], {}, []
    for cs in sources:
        code = cs.id
        m, items = build(cs, problems, write_cache)
        if not m:
            continue
        meta[code] = m
        if not problems:
            out.mkdir(parents=True, exist_ok=True)
            (out / f"items-{code}.json").write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            built.append((cs, items))
        log(f"{code}: {len(items)} 项 / {m['total']} XP / version {m['content_version']}")
        for ch in m["chapters"]:
            ci = [i for i in items if i["page"].split("-")[0] == ch]
            log(f"  {ch} {m['chapters'][ch]}: {len(ci)} 项 / {sum(i['max_xp'] for i in ci)} XP"
                f" / Boss {m['pages'].get(ch, {}).get('boss') or '—'}")
    cat = []
    if not problems:
        for cs, items in built:
            try:
                cat.append(course_meta(cs, items))
            except (CatalogBuildError, OSError, KeyError, ValueError) as e:
                problems.append(f"{cs.id}：生成课程目录失败（{e}）")
    if problems:
        err("问题：\n- " + "\n- ".join(problems))
        return 2
    out.mkdir(parents=True, exist_ok=True)
    (out / "courses.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "catalog.json").write_text(json.dumps(catalog_doc(cat), ensure_ascii=False, indent=1) + "\n",
                                      encoding="utf-8")
    log(f"已写入 {out}")
    return 0


def check_content(src, content, *, allow_empty: bool = False, log=print, err=None) -> int:
    """items ↔ 页面双向检查。返回退出码：0 一致；2 有问题。"""
    err = err or _stderr
    try:
        sources = discover(src, allow_empty=allow_empty)
    except CatalogError as e:
        err(str(e))
        return 2
    bad = [b for c in sources for b in check_course(c.id, c.dir, Path(content), log)]
    log("问题：\n- " + "\n- ".join(bad) if bad else "✅ 双向一致")
    return 2 if bad else 0
