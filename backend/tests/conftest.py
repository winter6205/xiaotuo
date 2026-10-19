"""API 测试跑在真实数据库上，用 XT_TEST_DB 选择：

- sqlite（默认，本机不装 PostgreSQL 也能跑）：临时目录下的文件库，结束后删除；
- postgres：默认每次运行新建临时库 xiaotuo_test_<pid>（TEST_DATABASE_BASE 指定服务器），结束后删除。

两种都可以用 TEST_DATABASE_URL 指定现成的库（不建不删）。
会话开始时对空库执行 alembic upgrade → downgrade base → upgrade，顺带验证迁移可逆。
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

# 隔离外部环境：shell 或 CI 里设的 COURSE_DIR 只用于构建与检查脚本，不得影响 xiaotuo 的 settings。
# 须在导入 xiaotuo 之前清除；需要 COURSE_DIR 行为的测试自行 monkeypatch settings.course_dir。
os.environ.pop("COURSE_DIR", None)

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
SAMPLE_ROOT = REPO / "examples"          # 课程根目录：内含 examples/sample-course（id demo）
FIXTURES = Path(__file__).parent / "fixtures" / "content"


def _build_content() -> str:
    """会话级内容：用 build_content.py 从示例课程生成，再并入测试专用的课程（alpha / beta / gamma）。"""
    out = Path(tempfile.mkdtemp(prefix="xt-content-"))
    r = subprocess.run([sys.executable, str(BACKEND / "scripts" / "build_content.py"), "--src", str(SAMPLE_ROOT),
                        "--out", str(out)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if r.returncode != 0:
        raise RuntimeError(f"build_content.py 失败（{r.returncode}）\n{r.stdout}\n{r.stderr}")
    meta = json.loads((out / "courses.json").read_text(encoding="utf-8"))
    meta.update(json.loads((FIXTURES / "courses.json").read_text(encoding="utf-8")))
    (out / "courses.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    for f in FIXTURES.glob("items-*.json"):
        shutil.copy(f, out / f.name)
    return str(out)

DB_KIND = os.environ.get("XT_TEST_DB", "sqlite")
assert DB_KIND in ("sqlite", "postgres"), f"XT_TEST_DB 须为 sqlite 或 postgres：{DB_KIND}"
SQLITE = DB_KIND == "sqlite"
# 每次运行使用独立的临时库（xiaotuo_test_<pid> 或临时目录下的文件），避免多人或多进程共用一个库互相清表导致死锁。
# 设置 TEST_DATABASE_URL 时直接使用该库，不建不删。
_BASE = os.environ.get("TEST_DATABASE_BASE", "postgresql+asyncpg://postgres:postgres@localhost:5432")
_OWN_DB = "TEST_DATABASE_URL" not in os.environ
_DB_NAME = f"xiaotuo_test_{os.getpid()}"
# 本模块会被导入两次（pytest 的 conftest 与测试里的 tests.conftest），临时目录经环境变量共用同一个
_SQLITE_DIR = Path(os.environ.setdefault("XT_TEST_SQLITE_DIR", tempfile.mkdtemp(prefix="xt-test-db-"))) \
    if SQLITE and _OWN_DB else None
TEST_DB = os.environ.get("TEST_DATABASE_URL") or (
    "sqlite+aiosqlite:///" + (_SQLITE_DIR / "test.db").as_posix() if SQLITE else f"{_BASE}/{_DB_NAME}")


def _admin(sql: str) -> None:
    import asyncpg

    async def run():
        conn = await asyncpg.connect(_BASE.replace("postgresql+asyncpg://", "postgresql://") + "/postgres")
        try:
            await conn.execute(sql)
        finally:
            await conn.close()
    asyncio.run(run())


if _OWN_DB and not SQLITE:
    _admin(f'DROP DATABASE IF EXISTS "{_DB_NAME}"')
    _admin(f'CREATE DATABASE "{_DB_NAME}"')
# 测试与本地 .env、外部环境变量隔离：不读 .env，并固定会影响断言的配置
os.environ["XT_ENV_FILE"] = ""
os.environ["COOKIE_SECURE"] = "true"
os.environ["RATELIMIT_MULTIPLIER"] = "1"
os.environ["DATABASE_URL"] = TEST_DB
os.environ["CONTENT_DIR"] = CONTENT_DIR = _build_content()
os.environ["EMAIL_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import pool, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from xiaotuo import db, ratelimit  # noqa: E402
from xiaotuo.main import app  # noqa: E402

# TestClient 每个请求可能用不同事件循环：测试里不复用连接。make_engine 带上 SQLite 的 PRAGMA 与 BEGIN IMMEDIATE
db.engine = db.make_engine(TEST_DB, poolclass=pool.NullPool)
db.SessionLocal = async_sessionmaker(db.engine, expire_on_commit=False)

TABLES = ("users", "sessions", "password_resets", "progress_items", "progress_events", "badge_awards",
          "activity_days", "imports", "progress_resets", "content_versions")


def alembic(*args: str) -> subprocess.CompletedProcess:
    """在 backend/ 下运行 alembic（读 backend/alembic.ini）。子进程输出按 UTF-8 收发（Windows 默认按本地代码页）；
    失败时把 stdout / stderr 带进报错，不吞掉原因。"""
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND,
                       env={**os.environ, "DATABASE_URL": TEST_DB, "PYTHONIOENCODING": "utf-8"},
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        pytest.fail(f"alembic {' '.join(args)} 退出码 {r.returncode}\n--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}",
                    pytrace=False)
    return r


@pytest.fixture(scope="session", autouse=True)
def schema():
    alembic("downgrade", "base")
    alembic("upgrade", "head")
    alembic("downgrade", "base")
    alembic("upgrade", "head")
    yield
    asyncio.run(db.engine.dispose())
    if _OWN_DB and SQLITE:
        shutil.rmtree(_SQLITE_DIR, ignore_errors=True)
    elif _OWN_DB:
        _admin(f'DROP DATABASE IF EXISTS "{_DB_NAME}" WITH (FORCE)')
    shutil.rmtree(CONTENT_DIR, ignore_errors=True)


async def _truncate():
    eng = create_async_engine(TEST_DB, poolclass=pool.NullPool)
    async with eng.begin() as conn:
        if SQLITE:  # 没有 TRUNCATE；此连接未开 foreign_keys，删除顺序不受外键限制。rowid 主键清空后从 1 重新计数
            for t in TABLES:
                await conn.execute(text(f"DELETE FROM {t}"))
        else:
            await conn.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    await eng.dispose()


@pytest.fixture(autouse=True)
def clean():
    asyncio.run(_truncate())
    ratelimit.reset()
    yield


class Api:
    """带 Cookie 与 CSRF 的测试客户端。"""

    def __init__(self):
        self.c = TestClient(app, base_url="https://testserver")
        self.csrf = self.c.get("/api/me").json()["csrf_token"]

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None, headers=None, csrf=True, **kw):
        h = {"X-CSRF-Token": self.csrf} if csrf else {}
        r = self.c.post(url, json=json, headers={**h, **(headers or {})}, **kw)
        if r.status_code in (200, 201) and isinstance(r.json(), dict) and "csrf_token" in r.json():
            self.csrf = r.json()["csrf_token"]
        return r

    def register(self, email="xiaotuo@example.com", password="correct-horse-battery"):
        r = self.post("/api/auth/register", {"email": email, "password": password})
        assert r.status_code == 201, r.text
        return r


@pytest.fixture
def api():
    return Api()


@pytest.fixture
def user(api):
    api.register()
    return api


def ev(item_id, kind="xp", amt=None, course="alpha", ts="2026-10-18T08:21:04+08:00", day="2026-10-18", **kw):
    e = {"course": course, "item_id": item_id, "kind": kind, "client_event_id": str(uuid.uuid4()), "ts": ts}
    if amt is not None:
        e["amt"] = amt
    if day:
        e["day"] = day
    e.update(kw)
    return e
