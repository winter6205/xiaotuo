from fastapi.testclient import TestClient

from xiaotuo import main
from xiaotuo.config import DEV_VERSION, app_version, normalize_database_url, settings


def test_health_ok(monkeypatch):
    async def ok():
        return True

    monkeypatch.setattr(main, "_db_ok", ok)
    r = TestClient(main.app).get("/api/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert (body["status"], body["db"], body["version"]) == ("ok", "ok", settings.app_version)
    cv = body["content_version"]
    assert cv.pop("demo").startswith("demo-")  # 示例课程由 build_content.py 生成
    assert cv == {"alpha": "test-alpha", "beta": "test-beta", "gamma": "test-gamma"}
    assert body["email_enabled"] is False


def test_health_db_down(monkeypatch):
    async def down():
        return False

    monkeypatch.setattr(main, "_db_ok", down)
    r = TestClient(main.app).get("/api/health/ready")
    assert r.status_code == 503
    assert {k: r.json()[k] for k in ("status", "db", "version")} == {"status": "degraded", "db": "unavailable",
                                                                    "version": settings.app_version}


def test_normalize_neon_url():
    raw = "postgresql://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require"
    assert normalize_database_url(raw) == "postgresql+asyncpg://u:p@ep-x.neon.tech/db?ssl=require"


def test_normalize_keeps_asyncpg_url():
    url = "postgresql+asyncpg://u:p@localhost:5432/db"
    assert normalize_database_url(url) == url


def test_health_liveness_ignores_db(monkeypatch):
    async def down():
        return False

    monkeypatch.setattr(main, "_db_ok", down)
    r = TestClient(main.app).get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_ready_real_db():
    r = TestClient(main.app).get("/api/health/ready")
    assert r.status_code == 200 and r.json()["db"] == "ok"


def test_app_version_from_package_metadata(monkeypatch):
    """版本取自已安装包 xiaotuo 的元数据；仓库内开发（未安装为包）时为 0.0.0+dev。"""
    import importlib.metadata as md

    from xiaotuo import config
    monkeypatch.setattr(config, "version", lambda name: "1.2.3" if name == "xiaotuo" else md.version(name))
    assert app_version() == "1.2.3"

    def missing(name):
        raise md.PackageNotFoundError(name)
    monkeypatch.setattr(config, "version", missing)
    assert app_version() == DEV_VERSION == "0.0.0+dev"
