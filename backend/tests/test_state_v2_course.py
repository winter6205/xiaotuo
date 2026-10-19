"""state_version 2 的课（测试课程 gamma）：快照无 course 字段、自带徽章与等级、组件徽章、目录首页不参与毕业。"""
from xiaotuo.content import Course, courses
from tests.conftest import ev
from tests.test_import_reset_dashboard import imp
from tests.test_migrations_and_contract import check


def v2_state(**kw):
    s = {"version": 2, "xp": {}, "done": {}, "rec": {}, "solved": {}, "fix": {},
         "streak": {"cur": 0, "best": 0, "last": None}, "days": {}, "badges": {}, "quiet": False, "data": {},
         "sections": {}, "migratedV1": True}
    s.update(kw)
    return s


def test_v2_course_loads():
    c: Course = courses()["gamma"]
    assert c.state_version == 2 and c.total == 470 and len(c.items) == 24
    assert [b[0] for b in c.all_badges] == ["first", "streak3", "streak7", "comeback", "skill",
                                            "planner", "boss01", "boss02", "grad"]
    assert c.badge("coder") is None and c.level(0)["level_name"] == "新手"
    assert list(c.grad_pages) == ["01", "02"]


def test_v2_events_snapshot_and_boss_badge(user):
    r = user.post("/api/progress/gamma/events", {"events": [
        ev("00-done-a", kind="done", amt=10, course="gamma"),
        ev("01-boss-s1", amt=20, course="gamma"), ev("01-boss-clear", amt=50, course="gamma"),
        ev("00-boss-clear", amt=50, course="gamma"),
        ev("00-boss-q1", kind="solved", solved={"rev": False, "wrong": 0}, course="gamma"),  # Boss 关内题
        ev("01-boss-s9", amt=20, course="gamma"), ev("01-boss-perfect", amt=999, course="gamma")]}).json()
    st = [(x["status"], x.get("reason")) for x in r["results"]]
    assert st[:4] == [("applied", None)] * 4
    assert st[4] == ("rejected", "unknown_item") and st[5] == ("rejected", "unknown_item")
    assert r["xp_total"] == 10 + 20 + 50 + 50 + 30  # perfect 截断到 30
    assert {"first", "boss01", "planner"} <= set(r["new_badges"]) and "grad" not in r["new_badges"]
    snap = user.get("/api/progress/gamma")
    check(snap, "/api/progress/{course}", "get", 200)
    b = snap.json()
    assert b["storage_key"] == "gamma-v2" and b["state"]["version"] == 2 and "course" not in b["state"]
    assert b["state"]["data"] == {"cleared.00": 1, "cleared.01": 1}
    assert user.get("/api/progress/alpha").json()["state"]["xp"] == {}


def test_v2_item_badge(user):
    r = user.post("/api/progress/gamma/events", {"events": [
        ev("01-exp-mem", amt=15, solved={"rev": False, "wrong": 0}, course="gamma")]}).json()
    assert "skill" in r["new_badges"]


def test_v2_import_and_grad(user):
    c = courses()["gamma"]
    done = {s: 1 for p in c.grad_pages.values() for s in p["sections"]}
    xp = {**{s: 10 for s in done}, **{f"{p['boss']}-clear": 50 for p in c.grad_pages.values()}}
    r = imp(user, v2_state(done=done, xp=xp), course="gamma")
    check(r, "/api/progress/{course}/import", "post", 200)
    b = r.json()
    assert "grad" in b["badges_added"] and "planner" not in b["badges_added"]
    assert imp(user, {"version": 1, "course": "alpha", "xp": {}}, course="gamma").status_code == 422
    assert imp(user, v2_state(), course="alpha").status_code == 422


def test_v2_reset_and_dashboard(user):
    user.post("/api/progress/gamma/events", {"events": [ev("00-done-a", kind="done", amt=10, course="gamma")]})
    d = user.get("/api/dashboard")
    check(d, "/api/dashboard", "get", 200)
    g = next(x for x in d.json()["courses"] if x["course"] == "gamma")
    assert g["xp"] == 10 and g["xp_max"] == 470 and g["badges_total"] == 9
    r = user.post("/api/progress/gamma/reset", {"confirm": "RESET gamma"})
    check(r, "/api/progress/{scope}/reset", "post", 200)
    assert r.json()["courses"] == ["gamma"] and r.json()["items_deleted"] == 1
