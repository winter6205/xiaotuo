"""GET /api/courses（运行时课程目录）与 content_build 生成的 catalog.json。"""
import json
from pathlib import Path

import pytest

from tests.conftest import CONTENT_DIR, SAMPLE_ROOT, Api
from tests.test_migrations_and_contract import check
from xiaotuo import content
from xiaotuo.config import settings
from xiaotuo.content_build import build_content, dumps_courses


@pytest.fixture
def content_dir(monkeypatch):
    """切换 CONTENT_DIR 时清掉进程内缓存，结束后恢复。"""
    def use(path):
        monkeypatch.setattr(settings, "content_dir", str(path))
        content.catalog.cache_clear()
        content.courses.cache_clear()
    yield use
    content.catalog.cache_clear()
    content.courses.cache_clear()


def test_courses_ok_no_auth_and_contract():
    a = Api()   # 未登录
    r = a.get("/api/courses")
    check(r, "/api/courses", "get", 200)
    assert r.headers["cache-control"] == "no-cache"
    body = r.json()
    assert [c["id"] for c in body["courses"]] == ["demo"]
    demo = body["courses"][0]
    assert demo["key"] == "demo-v1" and demo["dir"] == "sample-course" and demo["total"] == 130
    assert [p["id"] for p in demo["pages"]] == ["00", "01"]
    assert r.headers["etag"] == f'"{body["version"]}"'


def test_courses_etag_304():
    a = Api()
    tag = a.get("/api/courses").headers["etag"]
    r = a.get("/api/courses", headers={"If-None-Match": tag})
    assert r.status_code == 304 and r.headers["etag"] == tag and r.content == b""
    assert a.get("/api/courses", headers={"If-None-Match": f"W/{tag}"}).status_code == 304
    assert a.get("/api/courses", headers={"If-None-Match": '"other"'}).status_code == 200


def test_courses_empty_is_200(tmp_path, content_dir):
    (tmp_path / "root").mkdir()
    assert build_content(tmp_path / "root", tmp_path / "out", allow_empty=True) == 0
    content_dir(tmp_path / "out")
    r = Api().get("/api/courses")
    check(r, "/api/courses", "get", 200)
    assert r.json()["courses"] == []


def test_courses_unavailable_503(tmp_path, content_dir):
    from fastapi.testclient import TestClient
    from xiaotuo.main import app
    content_dir(tmp_path)   # 没有 catalog.json
    c = TestClient(app, base_url="https://testserver")
    r = c.get("/api/courses")
    check(r, "/api/courses", "get", 503)
    assert r.json()["code"] == "catalog_unavailable"
    (tmp_path / "catalog.json").write_text("{\"nope\": 1}", encoding="utf-8")
    content.catalog.cache_clear()
    assert c.get("/api/courses").status_code == 503


def test_courses_in_fastapi_openapi():
    from xiaotuo.main import app
    op = app.openapi()["paths"]["/api/courses"]["get"]
    assert op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/CatalogResponse")
    assert "503" in op["responses"]


def test_catalog_written_with_content(tmp_path):
    doc = json.loads((Path(CONTENT_DIR) / "catalog.json").read_text(encoding="utf-8"))
    assert set(doc) == {"version", "courses"} and len(doc["version"]) == 12


CATALOG_FIXTURE = Path(__file__).parent / "fixtures" / "catalog-examples.json"


def test_catalog_courses_match_fixture(tmp_path):
    """The courses array built from the bundled example course is byte-identical to the recorded
    baseline: field order, defaults, indentation and the missing trailing newline all count. The
    baseline is the build-time output the frontend used before it started reading the runtime
    catalog, and frontend CourseMeta still follows its shape."""
    out = tmp_path / "content"
    assert build_content(SAMPLE_ROOT, out) == 0
    ours = dumps_courses(json.loads((out / "catalog.json").read_text(encoding="utf-8"))["courses"]).encode()
    assert ours == CATALOG_FIXTURE.read_bytes()
