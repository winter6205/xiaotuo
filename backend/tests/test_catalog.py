"""课程自动发现（app/catalog.py）与 build_content.py 的 static 引擎。"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.catalog import CatalogError, discover, storage_key
from tests.conftest import BACKEND, SAMPLE_ROOT

GOOD = {"schema": 1, "id": "c1", "title": "课程", "order": 1, "accent": "#112233", "state_version": 1,
        "engine": "course-manifest-js"}


def mk(root: Path, name: str, manifest) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "course.json").write_text(manifest if isinstance(manifest, str) else json.dumps(manifest), encoding="utf-8")
    return d


def test_discovers_sample_course():
    [c] = discover(SAMPLE_ROOT)
    assert c.id == "demo" and c.dir.name == "sample-course" and c.storage_key == "demo-v1"


def test_order_and_ignores_dirs_without_manifest(tmp_path):
    mk(tmp_path, "z", {**GOOD, "id": "b", "order": 1})
    mk(tmp_path, "a", {**GOOD, "id": "a", "order": 2})
    (tmp_path / "shared").mkdir()
    assert [c.id for c in discover(tmp_path)] == ["b", "a"]


def test_storage_key_default_and_explicit():
    assert storage_key({"id": "x", "state_version": 2}) == "x-v2"
    assert storage_key({"id": "x", "state_version": 1, "storage_key": "k"}) == "k"


@pytest.mark.parametrize("bad,msg", [
    ({k: v for k, v in GOOD.items() if k != "accent"}, "缺少必填字段 accent"),
    ({**GOOD, "id": "Bad-Id"}, "不符合"),
    ({**GOOD, "schema": 2}, "schema 须为 1"),
    ({**GOOD, "accent": "blue"}, "accent 须为 #rrggbb"),
    ({**GOOD, "state_version": 3}, "state_version 须为 1 或 2"),
    ({**GOOD, "engine": "x"}, "engine 须为"),
    ({**GOOD, "engine": "static"}, "chapters 必填"),
    ({**GOOD, "engine": "static", "chapters": [{"id": "01", "title": "t", "file": "missing.html"}]}, "不存在"),
    ("{not json", "无法解析"),
])
def test_invalid_manifest(tmp_path, bad, msg):
    mk(tmp_path, "c", bad)
    with pytest.raises(CatalogError) as e:
        discover(tmp_path)
    assert any(msg in p for p in e.value.problems), e.value.problems


def test_duplicate_id_and_storage_key_report_all(tmp_path):
    mk(tmp_path, "a", GOOD)
    mk(tmp_path, "b", GOOD)
    with pytest.raises(CatalogError) as e:
        discover(tmp_path)
    assert any("id c1 重复" in p for p in e.value.problems)
    assert any("storage_key c1-v1 重复" in p for p in e.value.problems)


def test_missing_root_and_empty_root(tmp_path):
    with pytest.raises(CatalogError, match="不存在"):
        discover(tmp_path / "nope")
    with pytest.raises(CatalogError, match="没有任何"):
        discover(tmp_path)


def test_symlink_outside_root_rejected(tmp_path):
    outside = mk(tmp_path / "elsewhere", "c", GOOD)
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(outside)
    with pytest.raises(CatalogError, match="课程根之外"):
        discover(root)


def test_build_content_cli_fails_on_bad_catalog(tmp_path):
    mk(tmp_path, "c", {**GOOD, "id": "Bad"})
    r = subprocess.run([sys.executable, str(BACKEND / "scripts" / "build_content.py"), "--src", str(tmp_path),
                        "--out", str(tmp_path / "out")], capture_output=True, text=True)
    assert r.returncode == 2 and "不符合" in r.stderr and not (tmp_path / "out").exists()


def test_static_engine_items(tmp_path):
    out = tmp_path / "out"
    subprocess.run([sys.executable, str(BACKEND / "scripts" / "build_content.py"), "--src", str(SAMPLE_ROOT),
                    "--out", str(out)], check=True, capture_output=True, text=True)
    meta = json.loads((out / "courses.json").read_text(encoding="utf-8"))["demo"]
    items = json.loads((out / "items-demo.json").read_text(encoding="utf-8"))
    assert [(i["id"], i["type"], i["max_xp"]) for i in items] == [
        ("00-rec-setup", "track", 0), ("00-done-read", "done", 10), ("01-quiz-1", "quiz", 10),
        ("01-done-read", "done", 10), ("01-boss-s1", "boss", 20), ("01-boss-clear", "boss", 50),
        ("01-boss-perfect", "boss", 30)]
    assert meta["dir"] == "sample-course" and meta["storage_key"] == "demo-v1" and meta["total"] == 130
    assert meta["pages"]["00"] == {"sections": ["00-done-read"], "boss": None, "graduation": False}
    assert meta["pages"]["01"] == {"sections": ["01-done-read"], "boss": "01-boss", "badge": "boss01"}
    r = subprocess.run([sys.executable, str(BACKEND / "scripts" / "check_content.py"), "--src", str(SAMPLE_ROOT),
                        "--content", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_static_engine_rejects_bad_ids(tmp_path):
    root = tmp_path / "root"
    shutil.copytree(SAMPLE_ROOT / "sample-course", root / "c")
    page = root / "c" / "01-基础.html"
    page.write_text(page.read_text(encoding="utf-8").replace('data-id="01-quiz-1"', 'data-id="00-done-read"'),
                    encoding="utf-8")
    r = subprocess.run([sys.executable, str(BACKEND / "scripts" / "build_content.py"), "--src", str(root),
                        "--out", str(tmp_path / "out")], capture_output=True, text=True)
    assert r.returncode == 2 and "00-done-read" in r.stderr
