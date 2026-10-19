"""迁移可逆性 + 响应体对照 openapi.yaml 的 JSON Schema 校验。"""
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.jsonschema import DRAFT202012

import asyncio
import subprocess

from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import SQLITE, TEST_DB, Api, alembic, ev

SPEC = yaml.safe_load((Path(__file__).resolve().parents[2] / "api" / "openapi.yaml").read_text(encoding="utf-8"))
REGISTRY = Registry().with_resource("spec", DRAFT202012.create_resource(SPEC))


def check(resp, path: str, method: str, status: int):
    assert resp.status_code == status, resp.text
    op = SPEC["paths"][path][method]
    r = op["responses"][str(status)]
    if "$ref" in r:
        r = SPEC["components"]["responses"][r["$ref"].split("/")[-1]]
    if "content" not in r:
        return
    ctype, media = next(iter(r["content"].items()))
    assert resp.headers["content-type"].startswith(ctype)
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", **media["schema"]}
    schema = _resolve_refs(schema)
    Draft202012Validator(schema, registry=REGISTRY).validate(resp.json())


def _resolve_refs(node):
    if isinstance(node, dict):
        return {k: ("spec" + v if k == "$ref" and v.startswith("#") else _resolve_refs(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_refs(x) for x in node]
    return node


def test_alembic_head_matches_models():
    assert "No new upgrade operations detected" in alembic("check").stdout + alembic("check").stderr
    assert "0001_baseline (head)" in alembic("current").stdout


def test_contract_auth_and_errors():
    a = Api()
    check(a.get("/api/me"), "/api/me", "get", 200)
    r = a.post("/api/auth/register", {"email": "c@example.com", "password": "correct-horse-battery"})
    check(r, "/api/auth/register", "post", 201)
    check(Api().post("/api/auth/register", {"email": "c@example.com", "password": "correct-horse-battery"}),
          "/api/auth/register", "post", 409)
    check(a.post("/api/auth/register", {"email": "x", "password": "1"}), "/api/auth/register", "post", 400)
    check(a.post("/api/auth/logout", csrf=False), "/api/auth/logout", "post", 403)
    check(a.post("/api/auth/password-reset/request", {"email": "c@example.com"}),
          "/api/auth/password-reset/request", "post", 503)
    b = Api()
    check(b.post("/api/auth/login", {"email": "c@example.com", "password": "wrong-pass-123"}),
          "/api/auth/login", "post", 401)
    check(b.get("/api/dashboard"), "/api/dashboard", "get", 401)
    check(a.get("/api/progress/go"), "/api/progress/{course}", "get", 404)
    check(a.post("/api/auth/logout"), "/api/auth/logout", "post", 204)


def test_contract_progress(user):
    r = user.post("/api/progress/alpha/events", {"events": [
        ev("01-1-quiz-x", amt=10, solved={"rev": False, "wrong": 0}), ev("01-done-a", kind="done", amt=10),
        ev("nope", amt=1), ev("01-boss-q1", kind="solved", solved={"rev": False, "wrong": 1}, fix=True)]})
    check(r, "/api/progress/{course}/events", "post", 200)
    check(user.get("/api/progress/alpha"), "/api/progress/{course}", "get", 200)
    r = user.post("/api/progress/alpha/import", {"source": "local_first_login", "state": {
        "version": 1, "course": "alpha", "xp": {"01-1-sim-x": 15}, "badges": {"first": "2026-10-01"}}})
    check(r, "/api/progress/{course}/import", "post", 200)
    r = user.post("/api/progress/alpha/import", {"source": "export_file", "state": {
        "version": 1, "course": "beta", "xp": {}}})
    check(r, "/api/progress/{course}/import", "post", 422)
    check(user.get("/api/dashboard"), "/api/dashboard", "get", 200)
    check(user.post("/api/progress/alpha/reset", {"confirm": "nope"}), "/api/progress/{scope}/reset", "post", 400)
    check(user.post("/api/progress/all/reset", {"confirm": "RESET all"}), "/api/progress/{scope}/reset", "post", 200)


@pytest.mark.parametrize("n", [121])
def test_contract_rate_limited(user, n):
    for _ in range(n - 1):
        user.post("/api/progress/alpha/events", {"events": [ev("01-1-quiz-x", amt=1)]})
    check(user.post("/api/progress/alpha/events", {"events": [ev("01-1-quiz-x", amt=1)]}),
          "/api/progress/{course}/events", "post", 429)


def _sql(*qs: str):
    async def run():
        eng = create_async_engine(TEST_DB, poolclass=pool.NullPool)
        async with eng.begin() as conn:
            res = [(await conn.execute(text(q))) for q in qs][-1]
            rows = res.all() if res.returns_rows else []
        await eng.dispose()
        return rows
    return asyncio.run(run())


def _course_checks():
    if SQLITE:  # SQLite 没有约束目录，从建表语句里取 CONSTRAINT ck_<表>_course CHECK (...)
        import re
        sqls = [r[0] for r in _sql("SELECT sql FROM sqlite_master WHERE type = 'table'")]
        return dict(m for q in sqls for m in re.findall(r"CONSTRAINT (ck_\w+_course) CHECK \((.*?)\),?\s*\n", q))
    return dict(_sql("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conname LIKE 'ck_%_course'"))


def _counts():
    return tuple(_sql("SELECT (SELECT count(*) FROM progress_items), (SELECT count(*) FROM activity_days),"
                      " (SELECT count(*) FROM badge_awards)")[0])


def test_baseline_course_check_is_id_pattern(user):
    checks = _course_checks()
    assert len(checks) == 3 and all(("GLOB" if SQLITE else "~") in d for d in checks.values())
    user.post("/api/progress/demo/events", {"events": [ev("00-done-read", kind="done", amt=10, course="demo")]})
    assert _counts()[0] == 1


def test_baseline_downgrade_and_upgrade_roundtrip():
    try:
        alembic("downgrade", "base")
        assert not _sql("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'progress_items'" if SQLITE
                        else "SELECT 1 FROM pg_tables WHERE tablename = 'progress_items'")
    finally:
        alembic("upgrade", "head")
    assert "0001_baseline (head)" in alembic("current").stdout
    assert len(_course_checks()) == 3
