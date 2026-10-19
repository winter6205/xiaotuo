from tests.conftest import Api, ev


def events(api, *evs, course="alpha"):
    return api.post(f"/api/progress/{course}/events", {"events": list(evs)})


def test_progress_requires_login_and_known_course(user):
    api = Api()
    assert api.get("/api/progress/alpha").status_code == 401
    assert api.post("/api/progress/alpha/events", {"events": [ev("01-1-quiz-x", amt=10)]}).status_code == 401
    r = user.get("/api/progress/go")
    assert r.status_code == 404 and r.json()["code"] == "course_not_found"
    assert events(user, ev("01-1-quiz-x", amt=10), course="go").status_code == 404


def test_events_require_csrf(user):
    r = user.post("/api/progress/alpha/events", {"events": [ev("01-1-quiz-x", amt=10)]}, csrf=False)
    assert r.status_code == 403 and r.json()["code"] == "csrf_failed"


def test_empty_snapshot_is_blank(user):
    r = user.get("/api/progress/alpha")
    assert r.status_code == 200
    b = r.json()
    assert b["course"] == "alpha" and b["storage_key"] == "alpha-v1" and b["content_version"] == "test-alpha"
    assert b["state"] == {"version": 1, "course": "alpha", "xp": {}, "done": {}, "rec": {}, "solved": {},
                          "fix": {}, "streak": {"cur": 0, "best": 0, "last": None}, "days": {}, "badges": {},
                          "quiet": False, "data": {}, "sections": {}}


def test_events_apply_and_idempotent_duplicate(user):
    batch = [ev("01-1-quiz-x", amt=10, solved={"rev": False, "wrong": 0}),
             ev("01-1-sim-x", amt=0, solved={"rev": True, "wrong": 2}),
             ev("01-done-a", kind="done", amt=10)]
    r = events(user, *batch)
    assert r.status_code == 200
    b = r.json()
    assert [x["status"] for x in b["results"]] == ["applied"] * 3
    assert [x["amt"] for x in b["results"]] == [10, 0, 10]
    assert b["xp_total"] == 20 and b["new_badges"] == ["first"]
    snap1 = user.get("/api/progress/alpha").json()["state"]
    # 重放同一批：全部 duplicate，结果不变
    r2 = events(user, *batch).json()
    assert [x["status"] for x in r2["results"]] == ["duplicate"] * 3
    assert r2["xp_total"] == 20 and r2["new_badges"] == [] and r2["snapshot_etag"] == b["snapshot_etag"]
    assert user.get("/api/progress/alpha").json()["state"] == snap1
    assert snap1["xp"] == {"01-1-quiz-x": 10, "01-1-sim-x": 0, "01-done-a": 10}
    assert snap1["done"] == {"01-done-a": 1}
    assert snap1["solved"]["01-1-sim-x"] == {"rev": True, "wrong": 2}
    assert snap1["days"] == {"2026-10-18": 1} and snap1["streak"] == {"cur": 1, "best": 1, "last": "2026-10-18"}
    assert snap1["badges"] == {"first": "2026-10-18"}


def test_duplicate_within_same_batch(user):
    e = ev("01-1-quiz-x", amt=10)
    r = events(user, e, dict(e)).json()
    assert [x["status"] for x in r["results"]] == ["applied", "duplicate"] and r["xp_total"] == 10


def test_amt_capped_max_and_unknown_item(user):
    r = events(user, ev("01-1-quiz-x", amt=999), ev("nope-1", amt=10),
               ev("01-1-sim-x", amt=10)).json()["results"]
    assert r[0] == {"client_event_id": r[0]["client_event_id"], "status": "applied", "amt": 10, "reason": "amt_capped"}
    assert r[1]["status"] == "rejected" and r[1]["reason"] == "unknown_item"
    assert r[2]["status"] == "applied"  # 整批不因单条失败回滚
    r = events(user, ev("01-1-sim-x", amt=15), ev("01-1-sim-x", amt=5)).json()
    assert [(x["status"], x["amt"]) for x in r["results"]] == [("raised", 15), ("unchanged", 15)]
    assert r["xp_total"] == 25


def test_course_mismatch_rejected(user):
    r = events(user, ev("01-1-quiz-x", amt=10, course="beta")).json()
    assert r["results"][0]["status"] == "rejected" and r["results"][0]["reason"] == "course_mismatch"


def test_done_uncheck_keeps_xp_and_rec(user):
    events(user, ev("01-done-a", kind="done", amt=10), ev("02-1-track-a", kind="rec"))
    r = events(user, ev("01-done-a", kind="done", amt=10, value=False), ev("02-1-track-a", kind="rec", value=False))
    assert [x["status"] for x in r.json()["results"]] == ["applied", "applied"]
    st = user.get("/api/progress/alpha").json()["state"]
    assert st["xp"]["01-done-a"] == 10 and st["done"] == {} and st["rec"] == {}
    assert st["badges"] == {"first": "2026-10-18"}  # 已得徽章不收回


def test_boss_solved_kind_and_clear_badge(user):
    r = events(user, ev("01-boss-q1", kind="solved", solved={"rev": False, "wrong": 1}, fix=True),
               ev("01-boss-s1", amt=20), ev("01-boss-clear", amt=50))
    assert r.json()["new_badges"] == ["boss01"]
    st = user.get("/api/progress/alpha").json()["state"]
    assert "01-boss-q1" not in st["xp"] and st["solved"]["01-boss-q1"] == {"rev": False, "wrong": 1}
    assert st["fix"] == {"01-boss-q1": 1} and st["data"] == {"cleared.01": 1}
    assert "01-boss-s1" not in st["solved"]  # Boss 阶段不是练习组件，不补 solved


def test_snapshot_fills_missing_solved_for_practice(user):
    events(user, ev("01-1-quiz-x", amt=5))
    assert user.get("/api/progress/alpha").json()["state"]["solved"] == {"01-1-quiz-x": {"rev": True, "wrong": 0}}


def test_amt_zero_does_not_touch_day(user):
    events(user, ev("01-1-sim-x", amt=0))
    st = user.get("/api/progress/alpha").json()["state"]
    assert st["xp"] == {"01-1-sim-x": 0} and st["days"] == {}


def test_future_ts_clamped(user):
    events(user, ev("01-1-quiz-x", amt=10, ts="2099-01-01T00:00:00Z", day=None))
    days = user.get("/api/progress/alpha").json()["state"]["days"]
    assert list(days) != ["2099-01-01"] and len(days) == 1


def test_streak_and_badges(user):
    evs = [ev(f"02-1-fill-{i}", amt=15, day=f"2026-10-{10 + i:02d}", ts=f"2026-10-{10 + i:02d}T08:00:00+08:00",
              solved={"rev": False, "wrong": 1}, fix=True) for i in range(10)]
    r = events(user, *evs).json()
    assert set(r["new_badges"]) == {"streak3", "streak7", "comeback", "coder"}
    st = user.get("/api/progress/alpha").json()["state"]
    assert st["streak"] == {"cur": 10, "best": 10, "last": "2026-10-19"}


def test_snapshot_etag_304(user):
    events(user, ev("01-1-quiz-x", amt=10))
    r = user.get("/api/progress/alpha")
    tag = r.headers["etag"]
    assert tag.startswith('W/"alpha-')
    assert user.get("/api/progress/alpha", headers={"If-None-Match": tag}).status_code == 304
    events(user, ev("01-1-sim-x", amt=10))
    assert user.get("/api/progress/alpha", headers={"If-None-Match": tag}).status_code == 200


def test_events_validation(user):
    assert events(user, ev("01-1-quiz-x")).status_code == 400  # xp 缺 amt
    assert events(user, ev("01-1-quiz-x", amt=1001)).status_code == 400
    assert events(user, ev("a/b", amt=1)).status_code == 400
    assert events(user, {**ev("01-1-quiz-x", amt=1), "client_event_id": "not-a-uuid"}).status_code == 400
    assert user.post("/api/progress/alpha/events", {"events": []}).status_code == 400
    many = [ev("01-1-quiz-x", amt=1) for _ in range(501)]
    r = user.post("/api/progress/alpha/events", {"events": many})
    assert r.status_code == 400 and r.json()["code"] == "validation_error"


def test_events_payload_too_large(user):
    body = '{"events":[' + ",".join(['{"x":"' + "a" * 1000 + '"}'] * 1100) + "]}"
    r = user.c.post("/api/progress/alpha/events", content=body,
                    headers={"X-CSRF-Token": user.csrf, "Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["code"] == "payload_too_large"


def test_events_rate_limit(user):
    for _ in range(120):
        events(user, ev("01-1-quiz-x", amt=1))
    r = events(user, ev("01-1-quiz-x", amt=1))
    assert r.status_code == 429 and "retry-after" in r.headers


def test_users_isolated(user):
    events(user, ev("01-1-quiz-x", amt=10))
    other = Api()
    other.register(email="other@example.com")
    assert other.get("/api/progress/alpha").json()["state"]["xp"] == {}


def test_course_not_found_404(user):
    for url in ("/api/progress/nosuch", "/api/progress/Bad-Id"):
        r = user.get(url)
        assert r.status_code == 404 and r.json()["code"] == "course_not_found"
    assert events(user, ev("01-1-quiz-x", amt=1), course="nosuch").status_code == 404
    r = user.post("/api/progress/nosuch/reset", {"confirm": "RESET nosuch"})
    assert r.status_code == 400 and r.json()["code"] == "validation_error"
