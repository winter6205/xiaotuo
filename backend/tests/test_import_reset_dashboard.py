from tests.conftest import Api, ev


def blank(course="alpha", **kw):
    s = {"version": 1, "course": course, "xp": {}, "done": {}, "rec": {}, "solved": {}, "fix": {},
         "streak": {"cur": 0, "best": 0, "last": None}, "days": {}, "badges": {}, "quiet": False, "data": {},
         "sections": {}}
    s.update(kw)
    return s


def imp(api, state, key=None, course="alpha", source="export_file"):
    return api.post(f"/api/progress/{course}/import", {"source": source, "state": state},
                    headers={"Idempotency-Key": key} if key else None)


def test_import_union_merge(user):
    user.post("/api/progress/alpha/events", {"events": [
        ev("01-1-sim-x", amt=10, solved={"rev": False, "wrong": 3}),
        ev("01-1-quiz-x", amt=10, solved={"rev": True, "wrong": 0})]})
    state = blank(
        xp={"01-1-sim-x": 15, "01-1-quiz-x": 5, "01-done-a": 10, "01-old-quiz": 10, "01-boss-s1": 999},
        done={"01-done-a": 1}, rec={"02-1-track-a": 1},
        solved={"01-1-sim-x": {"rev": False, "wrong": 1}, "01-1-quiz-x": {"rev": False, "wrong": 2}},
        fix={"01-1-sim-x": 1}, days={"2026-10-15": 1, "2026-10-16": 1, "2026-10-17": 1},
        streak={"cur": 99, "best": 99, "last": "2026-10-17"},
        badges={"first": "2026-10-15", "streak3": "2026-10-17", "streak7": "2026-10-17", "bogus": "2026-01-01"})
    r = imp(user, state)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["items_added"] == 3 and b["items_raised"] == 1 and b["unknown_ids"] == ["01-old-quiz"]
    assert b["xp_before"] == 20 and b["xp_after"] == 15 + 10 + 10 + 20  # boss-s1 截断到 20
    assert set(b["badges_added"]) == {"first", "streak3"}  # streak7 条件不满足、bogus 未知：不采信
    st = user.get("/api/progress/alpha").json()["state"]
    assert st["xp"] == {"01-1-sim-x": 15, "01-1-quiz-x": 10, "01-done-a": 10, "01-boss-s1": 20}
    assert st["solved"]["01-1-sim-x"] == {"rev": False, "wrong": 1}
    assert st["solved"]["01-1-quiz-x"] == {"rev": False, "wrong": 0}  # rev=false 优先、wrong 取小
    assert st["done"] == {"01-done-a": 1} and st["rec"] == {"02-1-track-a": 1} and st["fix"] == {"01-1-sim-x": 1}
    assert st["streak"]["best"] == 4  # 导入 15–17 + 事件 18；不采信导入的 streak，按活动日复算
    assert st["badges"]["first"] == "2026-10-15" and st["badges"]["streak3"] == "2026-10-17"
    assert "streak7" not in st["badges"] and "bogus" not in st["badges"]


def test_import_twice_no_double_xp(user):
    s = blank(xp={"01-1-quiz-x": 10})
    assert imp(user, s).json()["xp_after"] == 10
    r = imp(user, s).json()
    assert (r["items_added"], r["xp_before"], r["xp_after"]) == (0, 10, 10)


def test_import_idempotency_key_returns_first_result(user):
    first = imp(user, blank(xp={"01-1-quiz-x": 10}), key="expired-alpha-2026-10-18").json()
    again = imp(user, blank(xp={"01-1-sim-x": 15}), key="expired-alpha-2026-10-18").json()
    assert again == first
    assert user.get("/api/progress/alpha").json()["state"]["xp"] == {"01-1-quiz-x": 10}


def test_import_course_mismatch_422(user):
    r = imp(user, blank(course="beta"))
    assert r.status_code == 422
    assert r.json()["code"] == "import_course_mismatch"
    assert r.json()["details"] == {"expected": "alpha", "got": "beta"}
    assert imp(user, {**blank(), "version": 2}).status_code == 422


def test_import_validation_and_auth(user):
    api = Api()
    assert imp(api, blank()).status_code == 401
    assert user.post("/api/progress/alpha/import", {"source": "other", "state": blank()}).status_code == 400
    assert imp(user, blank(xp={"01-1-quiz-x": -1})).status_code == 400
    assert imp(user, blank(), key="k" * 65).status_code == 400
    r = user.post("/api/progress/alpha/import", {"source": "export_file", "state": blank()}, csrf=False)
    assert r.status_code == 403


def test_import_too_large(user):
    big = blank(data={"pad": "x" * (2 * 1024 * 1024)})
    r = imp(user, big)
    assert r.status_code == 413 and r.json()["code"] == "payload_too_large"


def test_reset_requires_exact_confirm(user):
    r = user.post("/api/progress/alpha/reset", {"confirm": "RESET all"})
    assert r.status_code == 400 and r.json() == {"code": "confirm_required", "message": "请输入 RESET alpha 确认"}
    assert user.post("/api/progress/alpha/reset", {"confirm": "RESET alpha"}, csrf=False).status_code == 403


def test_reset_clears_course_only(user):
    user.post("/api/progress/alpha/events", {"events": [ev("01-done-a", kind="done", amt=10)]})
    user.post("/api/progress/beta/events", {"events": [ev("J1-done-a", kind="done", amt=10, course="beta")]})
    r = user.post("/api/progress/alpha/reset", {"confirm": "RESET alpha"})
    assert r.status_code == 200
    assert r.json()["courses"] == ["alpha"] and r.json()["items_deleted"] == 1
    st = user.get("/api/progress/alpha").json()["state"]
    assert st["xp"] == {} and st["badges"] == {} and st["days"] == {}
    assert user.get("/api/progress/beta").json()["state"]["xp"] == {"J1-done-a": 10}
    d = user.get("/api/dashboard").json()
    assert [x["course"] for x in d["recent"]] == ["beta"]  # 清空前的事件不再出现在最近活动
    r = user.post("/api/progress/all/reset", {"confirm": "RESET all"}).json()
    assert r["courses"] == ["alpha", "beta", "gamma", "demo"] and r["items_deleted"] == 1


def test_dashboard(user):
    api = Api()
    assert api.get("/api/dashboard").status_code == 401
    user.post("/api/progress/alpha/events", {"events": [
        ev("01-done-a", kind="done", amt=10, day="2026-10-17", ts="2026-10-17T08:00:00+08:00"),
        ev("01-1-quiz-x", amt=10), ev("01-boss-s1", amt=20), ev("01-boss-clear", amt=50)]})
    user.post("/api/progress/beta/events", {"events": [ev("J1-1-quiz-a", amt=10, course="beta", day="2026-10-16",
                                                          ts="2026-10-16T08:00:00+08:00")]})
    imp(user, blank(xp={"01-1-sim-x": 15}))
    d = user.get("/api/dashboard").json()
    assert d["user"]["email"] == "xiaotuo@example.com"
    a = d["courses"][0]
    assert a["course"] == "alpha" and a["title"] == "测试课程 A"
    assert a["xp"] == 105 and a["xp_max"] == 425 and a["items_total"] == 24  # fixtures 加了 00 章 4 项 / 110 XP
    assert a["level"] == {"level": 2, "level_name": "起步", "level_min_xp": 100, "next_level_xp": 300,
                           "next_level_name": "进阶"}
    assert a["items_done"] == 5
    ch01 = a["chapters"][1]  # [0] 为新增的 00 章
    assert ch01 == {"chapter_id": "01", "title": "第一章", "items_done": 5, "items_total": 8, "xp": 105,
                    "xp_max": 155, "has_boss": True, "boss_cleared": True,
                    "scored_total": 8, "scored_done": 5, "tracks_done": 0}
    ch02 = a["chapters"][2]
    assert ch02["chapter_id"] == "02" and ch02["has_boss"] is False and ch02["boss_cleared"] is False
    assert a["badges_total"] == 8 and a["badges_count"] == 2  # first + boss01
    assert d["summary"]["xp_total"] == 115 and d["summary"]["days_total"] == 3
    assert d["summary"]["streak_best"] == 3 and d["summary"]["badges_total"] == 24  # alpha 8 + beta 5 + gamma 9 + demo 2（清单只声明 boss01、grad）
    assert {b["badge_id"] for b in d["badges"]} == {"first", "boss01"}
    assert len(d["recent"]) == 5 and d["recent"][0]["course"] == "beta"
    r0 = next(x for x in d["recent"] if x["item_id"] == "01-1-quiz-x")
    assert r0["chapter_id"] == "01" and r0["page_id"] == "01-1" and r0["amt"] == 10
    assert d["last_import"]["course"] == "alpha" and d["last_import"]["items_added"] == 1
    assert d["last_import"]["xp_delta"] == 15


def test_dashboard_empty(user):
    d = user.get("/api/dashboard").json()
    assert d["recent"] == [] and d["last_import"] is None and d["badges"] == []
    assert d["courses"][0]["level"]["level"] == 1


def test_dashboard_tz(user, monkeypatch):
    from datetime import datetime as real_dt, timezone

    from app.routers import dashboard as dash

    class FakeDT(real_dt):  # 2026-10-18 17:00 UTC = 2026-10-19 01:00 香港
        @classmethod
        def now(cls, tz=None):
            return real_dt(2026, 10, 18, 17, 0, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(dash, "datetime", FakeDT)
    user.post("/api/progress/alpha/events", {"events": [
        ev("01-1-quiz-x", amt=10, day="2026-10-17", ts="2026-10-17T08:00:00+08:00")]})
    # UTC 今天 10-18：最近活动 10-17 相差 1 天，连学仍算 1
    assert user.get("/api/dashboard").json()["summary"]["streak_cur"] == 1
    # 香港已到 10-19：相差 2 天，连学断档
    hk = user.get("/api/dashboard", params={"tz": "Asia/Hong_Kong"}).json()
    assert hk["summary"]["streak_cur"] == 0 and hk["courses"][0]["streak_cur"] == 0
    r = user.get("/api/dashboard", params={"tz": "Mars/Base"})
    assert r.status_code == 400 and r.json()["code"] == "validation_error"
    assert user.get("/api/dashboard", params={"tz": "../etc/passwd"}).status_code == 400
