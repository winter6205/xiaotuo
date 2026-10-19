"""COURSE_DIR 设置时，/course/<id>/** 从课程目录只读提供（Docker 挂载）；id → 子目录取自 courses.json 的 dir。"""
import pytest
from fastapi.testclient import TestClient

from xiaotuo.config import settings
from xiaotuo.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "course" / "alpha").mkdir(parents=True)
    (dist / "course" / "alpha" / "00-a.html").write_text("dist copy", encoding="utf-8")
    (dist / "index.html").write_text("<!doctype html>shell", encoding="utf-8")
    repo = tmp_path / "repo"
    for d in ("alpha", "beta", "gamma", "sample-course"):
        (repo / d / "assets" / "__pycache__").mkdir(parents=True)
        (repo / d / "00-a.html").write_text(f"<p>{d}</p>", encoding="utf-8")
        (repo / d / "assets" / "course.js").write_text("var x=1", encoding="utf-8")
        (repo / d / "assets" / "__pycache__" / "x.pyc").write_text("x", encoding="utf-8")
        (repo / d / "notes.md").write_text("draft", encoding="utf-8")
        (repo / d / "design").mkdir()
        (repo / d / "design" / "s.html").write_text("design", encoding="utf-8")
    (repo / "secret.html").write_text("nope", encoding="utf-8")
    monkeypatch.setattr(settings, "frontend_dist", str(dist))
    monkeypatch.setattr(settings, "course_dir", str(repo))
    return TestClient(app, base_url="https://testserver")


@pytest.mark.parametrize("code,d", [("alpha", "alpha"), ("beta", "beta"), ("gamma", "gamma"), ("demo", "sample-course")])
def test_serves_from_course_dir(client, code, d):
    r = client.get(f"/course/{code}/00-a.html")
    assert r.status_code == 200 and r.text == f"<p>{d}</p>"  # 读挂载目录，而不是 dist 副本
    assert r.headers["content-type"] == "text/html; charset=utf-8" and r.headers["cache-control"] == "no-cache"
    js = client.get(f"/course/{code}/assets/course.js")
    assert js.status_code == 200 and js.headers["content-type"] == "text/javascript; charset=utf-8"


@pytest.mark.parametrize("path", [
    "/course/alpha/notes.md", "/course/alpha/design/s.html", "/course/alpha/assets/__pycache__/x.pyc",
    "/course/alpha/assets", "/course/alpha/", "/course/alpha/missing.html", "/course/xx/00-a.html",
    "/course/alpha/..%2Fsecret.html", "/course/alpha/assets/..%2F..%2Fsecret.html",
    "/course/alpha/%2e%2e/secret.html", "/course/alpha/%2e%2e%2fsecret.html",
    "/course/alpha/%2Fetc%2Fpasswd", "/course/alpha//etc/passwd",
])
def test_rejects_outside_scope(client, path):
    r = client.get(path)
    assert r.status_code == 404 and "nope" not in r.text


def test_unset_course_dir_uses_dist(client, monkeypatch):
    monkeypatch.setattr(settings, "course_dir", "")
    assert client.get("/course/alpha/00-a.html").text == "dist copy"
