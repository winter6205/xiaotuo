"""dashboard 每课 / 每章的 scored_total、scored_done、tracks_done：跟踪项（0 XP）不计入 scored。"""
from tests.conftest import ev
from tests.test_migrations_and_contract import check


def _by(d):
    return {c["course"]: c for c in d["courses"]}


def test_sample_course_scored_totals(user):
    d = user.get("/api/dashboard")
    check(d, "/api/dashboard", "get", 200)
    demo = _by(d.json())["demo"]
    # 示例课程：1 个跟踪项 + 2 个读完打卡 + 1 道题 + Boss 3 项
    assert (demo["items_total"], demo["scored_total"], demo["xp_max"]) == (7, 6, 130)
    assert [ch["scored_total"] for ch in demo["chapters"]] == [1, 5]
    for c in _by(d.json()).values():
        assert c["scored_done"] == c["tracks_done"] == 0
        assert c["scored_total"] == sum(ch["scored_total"] for ch in c["chapters"])


def test_scored_and_tracks_done(user):
    def gamma():
        d = user.get("/api/dashboard")
        check(d, "/api/dashboard", "get", 200)
        return _by(d.json())["gamma"]

    before = gamma()
    assert before["scored_done"] == before["tracks_done"] == 0
    r = user.post("/api/progress/gamma/events", {"events": [
        ev("01-boss-s1", amt=20, course="gamma"),
        ev("02-plan-d0", kind="rec", course="gamma")]}).json()
    assert [x["status"] for x in r["results"]] == ["applied", "applied"]
    after = gamma()
    assert after["scored_done"] == 1 and after["tracks_done"] == 1 and after["items_done"] == 2
    assert after["scored_total"] == before["scored_total"] and after["items_total"] == before["items_total"]
    ch = {c["chapter_id"]: c for c in after["chapters"]}
    assert (ch["01"]["scored_done"], ch["01"]["tracks_done"]) == (1, 0)
    assert (ch["02"]["scored_done"], ch["02"]["tracks_done"]) == (0, 1)


def test_sample_course_events(user):
    r = user.post("/api/progress/demo/events", {"events": [
        ev("00-done-read", kind="done", amt=10, course="demo"), ev("00-rec-setup", kind="rec", course="demo"),
        ev("01-quiz-1", amt=10, solved={"rev": False, "wrong": 0}, course="demo"),
        ev("01-boss-s1", amt=20, course="demo"), ev("01-boss-clear", amt=50, course="demo"),
        ev("01-done-read", kind="done", amt=10, course="demo")]}).json()
    assert all(x["status"] == "applied" for x in r["results"])
    assert {"first", "boss01", "grad"} <= set(r["new_badges"])
    snap = user.get("/api/progress/demo").json()
    assert snap["storage_key"] == "demo-v1" and snap["state"]["course"] == "demo"
