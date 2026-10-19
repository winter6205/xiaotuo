import pytest
from fastapi.testclient import TestClient

from xiaotuo.config import settings
from xiaotuo.main import app

INDEX = "<!doctype html><title>shell</title>"
COURSE = "<!doctype html><title>教材 00</title>"


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "assets" / "index-abc123.css").write_text("body{}", encoding="utf-8")
    (tmp_path / "course" / "alpha").mkdir(parents=True)
    (tmp_path / "course" / "alpha" / "00-目录.html").write_text(COURSE, encoding="utf-8")
    (tmp_path / "course" / "alpha" / "index.html").write_text("<p>目录</p>", encoding="utf-8")
    (tmp_path / "index.html").write_text(INDEX, encoding="utf-8")
    (tmp_path.parent / "secret.txt").write_text("nope", encoding="utf-8")
    monkeypatch.setattr(settings, "frontend_dist", str(tmp_path))
    return TestClient(app, base_url="https://testserver")


def test_root_serves_index_no_cache(client):
    r = client.get("/")
    assert r.status_code == 200 and r.text == INDEX
    assert r.headers["content-type"].startswith("text/html") and r.headers["cache-control"] == "no-cache"


def test_course_page_real_file_not_index(client):
    r = client.get("/course/alpha/00-目录.html")
    assert r.status_code == 200 and r.text == COURSE
    assert r.headers["content-type"] == "text/html; charset=utf-8"
    assert client.get("/course/alpha/").text == "<p>目录</p>"


def test_assets_types_and_long_cache(client):
    js, css = client.get("/assets/index-abc123.js"), client.get("/assets/index-abc123.css")
    assert js.headers["content-type"].startswith("text/javascript")
    assert css.headers["content-type"].startswith("text/css")
    assert "immutable" in js.headers["cache-control"] and "max-age=31536000" in css.headers["cache-control"]


@pytest.mark.parametrize("path", ["/course/alpha/missing.html", "/course/beta/", "/assets/gone.js", "/course"])
def test_course_and_assets_missing_404(client, path):
    r = client.get(path)
    assert r.status_code == 404 and INDEX not in r.text


@pytest.mark.parametrize("path", ["/nonexist/route", "/dashboard", "/learn/alpha/03-6"])
def test_spa_fallback(client, path):
    r = client.get(path)
    assert r.status_code == 200 and r.text == INDEX and r.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("method", ["get", "post"])
def test_api_never_falls_back(client, method):
    r = getattr(client, method)("/api/nope")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "course_not_found"


def test_api_routes_still_work(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/me").json()["user"] is None


def test_no_path_traversal(client):
    assert "nope" not in client.get("/..%2Fsecret.txt").text
    assert "nope" not in client.get("/course/../../secret.txt").text


def test_missing_dist_api_still_works(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "frontend_dist", str(tmp_path / "no-dist"))
    c = TestClient(app, base_url="https://testserver")
    assert c.get("/api/health").status_code == 200
    assert c.get("/").status_code == 404 and c.get("/api/nope").status_code == 404
