import pytest

from xiaotuo.config import settings
from xiaotuo.routers import auth as auth_router
from tests.conftest import Api

PW = "correct-horse-battery"


def test_me_anonymous_issues_csrf_and_pre_session():
    a = Api()
    r = a.get("/api/me")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["user"] is None and body["default_course"] == "alpha"
    assert body["features"] == {"password_reset": False}
    assert len(body["csrf_token"]) >= 32 and body["csrf_token"] == a.csrf  # 同一预会话


def test_register_creates_session_and_rotates(api):
    old_cookie, old_csrf = api.c.cookies["xt_session"], api.csrf
    r = api.post("/api/auth/register", {"email": "  XiaoTuo@Example.com ", "password": PW})
    assert r.status_code == 201
    sc = r.headers["set-cookie"]
    for attr in ("HttpOnly", "Secure", "SameSite=lax", "Path=/", "Max-Age=2592000"):
        assert attr.lower() in sc.lower()
    body = r.json()
    assert body["user"]["email"] == "xiaotuo@example.com"
    assert body["csrf_token"] != old_csrf and api.c.cookies["xt_session"] != old_cookie
    assert api.get("/api/me").json()["user"]["id"] == body["user"]["id"]


def test_register_requires_csrf(api):
    r = api.post("/api/auth/register", {"email": "a@b.co", "password": PW}, csrf=False)
    assert r.status_code == 403 and r.json()["code"] == "csrf_failed"
    assert r.headers["content-type"].startswith("application/problem+json")
    r = api.post("/api/auth/register", {"email": "a@b.co", "password": PW}, headers={"X-CSRF-Token": "x" * 32})
    assert r.status_code == 403


def test_register_duplicate_email_409(api):
    api.register()
    b = Api()
    r = b.post("/api/auth/register", {"email": "XIAOTUO@example.com", "password": PW})
    assert r.status_code == 409 and r.json()["code"] == "email_taken"


@pytest.mark.parametrize("pw,code", [("short", "validation_error"), ("x" * 129, "validation_error"),
                                     ("password123", "weak_password"), ("Qwertyuiop", "weak_password")])
def test_register_password_rules(api, pw, code):
    r = api.post("/api/auth/register", {"email": "a@b.co", "password": pw})
    assert r.status_code == 400 and r.json()["code"] == code


def test_password_no_composition_rules(api):
    api.register(password="aaaa bbbb cccc")  # 只有小写和空格也可以


def test_register_rejects_bad_email_and_extra_fields(api):
    assert api.post("/api/auth/register", {"email": "nope", "password": PW}).status_code == 400
    r = api.post("/api/auth/register", {"email": "a@b.co", "password": PW, "admin": True})
    assert r.status_code == 400 and r.json()["details"]["fields"]


def test_login_logout_flow(api):
    api.register()
    first_cookie = api.c.cookies["xt_session"]
    assert api.post("/api/auth/logout").status_code == 204
    me = api.get("/api/me").json()
    assert me["user"] is None
    api.csrf = me["csrf_token"]
    r = api.post("/api/auth/login", {"email": "xiaotuo@example.com", "password": "wrong-password-x"})
    assert r.status_code == 401 and r.json()["code"] == "invalid_credentials"
    pre_csrf, pre_cookie = api.csrf, api.c.cookies["xt_session"]
    r = api.post("/api/auth/login", {"email": "xiaotuo@example.com", "password": PW})
    assert r.status_code == 200 and r.json()["user"]["email"] == "xiaotuo@example.com"
    assert r.json()["csrf_token"] != pre_csrf
    assert api.c.cookies["xt_session"] not in (pre_cookie, first_cookie)


def test_logout_clears_cookie_and_old_cookie_invalid(user):
    cookie = user.c.cookies["xt_session"]
    r = user.post("/api/auth/logout")
    assert r.status_code == 204
    assert "max-age=0" in r.headers["set-cookie"].lower()
    stale = Api()
    stale.c.cookies.set("xt_session", cookie)
    assert stale.get("/api/progress/alpha").status_code == 401


def test_logout_requires_login_and_csrf(user):
    assert Api().post("/api/auth/logout").status_code == 401
    assert user.post("/api/auth/logout", csrf=False).status_code == 403


def test_login_rate_limit_per_email(api):
    api.register()
    for _ in range(5):
        api.post("/api/auth/login", {"email": "xiaotuo@example.com", "password": "wrong-password-x"})
    r = api.post("/api/auth/login", {"email": "xiaotuo@example.com", "password": PW})
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1 and r.json()["details"]["retry_after"] >= 1


def test_login_rate_limit_per_ip(api):
    for i in range(10):
        api.post("/api/auth/login", {"email": f"u{i}@example.com", "password": PW})
    assert api.post("/api/auth/login", {"email": "z@example.com", "password": PW}).status_code == 429


def test_register_rate_limit_per_ip():
    a = Api()
    for i in range(5):
        a = Api()
        a.post("/api/auth/register", {"email": f"r{i}@example.com", "password": PW})
    assert Api().post("/api/auth/register", {"email": "r9@example.com", "password": PW}).status_code == 429


def test_password_reset_disabled_503(api):
    r = api.post("/api/auth/password-reset/request", {"email": "a@b.co"})
    assert r.status_code == 503 and r.json()["code"] == "email_disabled"
    r = api.post("/api/auth/password-reset/confirm", {"token": "t" * 40, "new_password": "brand-new-pass"})
    assert r.status_code == 503


def test_password_reset_enabled_flow(monkeypatch, api):
    monkeypatch.setattr(settings, "email_enabled", True)
    sent = {}

    async def fake_send(email, token):
        sent[email] = token

    monkeypatch.setattr(auth_router, "send_reset_email", fake_send)
    api.register()
    other = Api()
    assert other.get("/api/me").json()["features"]["password_reset"] is True
    # 未注册邮箱同样 202，同一文案
    r1 = other.post("/api/auth/password-reset/request", {"email": "nobody@example.com"})
    r2 = other.post("/api/auth/password-reset/request", {"email": "xiaotuo@example.com"})
    assert r1.status_code == r2.status_code == 202 and r1.json() == r2.json()
    first = sent["xiaotuo@example.com"]
    other.post("/api/auth/password-reset/request", {"email": "xiaotuo@example.com"})
    second = sent["xiaotuo@example.com"]
    bad = other.post("/api/auth/password-reset/confirm", {"token": first, "new_password": "brand-new-pass"})
    assert bad.status_code == 400 and bad.json()["code"] == "reset_token_invalid"  # 新申请使旧 token 失效
    ok = other.post("/api/auth/password-reset/confirm", {"token": second, "new_password": "brand-new-pass"})
    assert ok.status_code == 204
    assert api.get("/api/progress/alpha").status_code == 401  # 全部会话失效
    again = other.post("/api/auth/password-reset/confirm", {"token": second, "new_password": "brand-new-pass2"})
    assert again.status_code == 400  # 一次性
    assert other.post("/api/auth/login", {"email": "xiaotuo@example.com", "password": "brand-new-pass"}).status_code == 200


def test_password_reset_request_rate_limit_per_email(monkeypatch, api):
    monkeypatch.setattr(settings, "email_enabled", True)
    for _ in range(3):
        assert api.post("/api/auth/password-reset/request", {"email": "a@b.co"}).status_code == 202
    assert api.post("/api/auth/password-reset/request", {"email": "a@b.co"}).status_code == 429
