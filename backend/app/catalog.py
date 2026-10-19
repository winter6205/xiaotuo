"""课程自动发现：COURSE_DIR 的每个直接子目录，含 course.json 即注册为一门课。

清单格式见 course.json 规范（schema 1）。后端构建脚本、check_content、check_ids 共用本模块；
前端 import-course.mjs 实现同一规则。校验失败抛 CatalogError，列出全部问题。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

MANIFEST = "course.json"
ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,15}$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
ENGINES = {"course-manifest-js", "static"}
REQUIRED = ("schema", "id", "title", "order", "accent", "state_version", "engine")
# 默认课程根目录：仓库根的同级目录 course-content（与 docker compose 的 CONTENT_HOST_DIR 默认一致）
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO_ROOT.parent / "course-content"


class CatalogError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("课程清单有问题：\n- " + "\n- ".join(problems))
        self.problems = problems


@dataclass
class CourseSource:
    dir: Path            # 课程目录（已解析）
    manifest: dict

    @property
    def id(self) -> str:
        return self.manifest["id"]

    @property
    def storage_key(self) -> str:
        return storage_key(self.manifest)


def course_root(explicit: str | os.PathLike | None = None) -> Path:
    return Path(explicit or os.environ.get("COURSE_DIR") or DEFAULT_ROOT).resolve()


def storage_key(m: dict) -> str:
    """省略 storage_key 时默认 "<id>-v<state_version>"。"""
    return m.get("storage_key") or f"{m['id']}-v{m['state_version']}"


def validate(m: object, where: str) -> list[str]:
    if not isinstance(m, dict):
        return [f"{where}：不是 JSON 对象"]
    bad = [f"{where}：缺少必填字段 {k}" for k in REQUIRED if k not in m]
    if bad:
        return bad
    if m["schema"] != 1:
        bad.append(f"{where}：schema 须为 1")
    if not isinstance(m["id"], str) or not ID_RE.match(m["id"]):
        bad.append(f"{where}：id {m['id']!r} 不符合 ^[a-z][a-z0-9_]{{0,15}}$")
    if not isinstance(m["title"], str) or not m["title"].strip():
        bad.append(f"{where}：title 不能为空")
    if not isinstance(m["order"], (int, float)) or isinstance(m["order"], bool):
        bad.append(f"{where}：order 须为数字")
    for k in ("accent", "accent_light", "accent_dark"):
        if k in m and not (isinstance(m[k], str) and HEX_RE.match(m[k])):
            bad.append(f"{where}：{k} 须为 #rrggbb")
    if m["state_version"] not in (1, 2):
        bad.append(f"{where}：state_version 须为 1 或 2")
    if m["engine"] not in ENGINES:
        bad.append(f"{where}：engine 须为 {' 或 '.join(sorted(ENGINES))}")
    if "storage_key" in m and not (isinstance(m["storage_key"], str) and m["storage_key"]):
        bad.append(f"{where}：storage_key 须为非空字符串")
    if m["engine"] == "static":
        chs = m.get("chapters")
        if not isinstance(chs, list) or not chs:
            bad.append(f"{where}：engine=static 时 chapters 必填")
        else:
            seen = set()
            for i, ch in enumerate(chs):
                if not (isinstance(ch, dict) and isinstance(ch.get("id"), str) and isinstance(ch.get("file"), str)
                        and isinstance(ch.get("title"), str)):
                    bad.append(f"{where}：chapters[{i}] 须含 id、title、file")
                    continue
                if ch["id"] in seen:
                    bad.append(f"{where}：章 {ch['id']} 重复")
                seen.add(ch["id"])
    return bad


def discover(root: str | os.PathLike | None = None) -> list[CourseSource]:
    """按 order、id 排序返回全部课程；任何问题都汇总后抛 CatalogError。"""
    base = course_root(root)
    if not base.is_dir():
        raise CatalogError([f"课程根目录不存在：{base}（用 COURSE_DIR 指定）"])
    problems, out = [], []
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        f = d / MANIFEST
        if not f.is_file():
            continue
        real = d.resolve()
        if not real.is_relative_to(base):
            problems.append(f"{d.name}：目录指向课程根之外，已拒绝")
            continue
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            problems.append(f"{d.name}/{MANIFEST}：无法解析（{e}）")
            continue
        bad = validate(m, f"{d.name}/{MANIFEST}")
        if not bad and m["engine"] == "static":
            for ch in m["chapters"]:
                p = (real / ch["file"]).resolve()
                if not (p.is_relative_to(real) and p.is_file() and p.parent == real and p.suffix == ".html"):
                    bad.append(f"{d.name}/{MANIFEST}：章 {ch['id']} 的页面 {ch['file']} 不存在或不在课程目录顶层")
        problems += bad
        if not bad:
            out.append(CourseSource(real, m))
    for key, label in ((lambda c: c.id, "id"), (lambda c: c.storage_key, "storage_key")):
        seen: dict[str, str] = {}
        for c in out:
            if key(c) in seen:
                problems.append(f"{label} {key(c)} 重复：{seen[key(c)]} 与 {c.dir.name}")
            seen.setdefault(key(c), c.dir.name)
    if problems:
        raise CatalogError(problems)
    if not out:
        raise CatalogError([f"{base} 下没有任何含 {MANIFEST} 的课程目录"])
    return sorted(out, key=lambda c: (c.manifest["order"], c.id))
