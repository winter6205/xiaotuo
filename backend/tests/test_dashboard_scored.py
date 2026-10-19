"""dashboard 每课 / 每章的 scored_total、scored_done、tracks_done：跟踪项（0 XP）不计入 scored。"""
from tests.conftest import ev
from tests.test_migrations_and_contract import _sql, check


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
    # 示例课程清单只声明 boss01 与 grad_badge：不再隐式补入 first、streak3 等通用徽章
    assert sorted(r["new_badges"]) == ["boss01", "grad"]
    snap = user.get("/api/progress/demo").json()
    assert snap["storage_key"] == "demo-v1" and snap["state"]["course"] == "demo"


def test_static_badges_follow_manifest(user):
    """回归：static 课程的徽章表只含清单声明的徽章（示例课程为 boss01 + grad），不叠加通用徽章（此前显示 x/6）。"""
    from app.content import courses
    demo = courses()["demo"]
    assert [b[0] for b in demo.all_badges] == ["boss01", "grad"]
    d = user.get("/api/dashboard").json()
    c = next(x for x in d["courses"] if x["course"] == "demo")
    assert (c["badges_count"], c["badges_total"]) == (0, 2)
    user.post("/api/progress/demo/events", {"events": [
        ev("01-quiz-1", amt=10, solved={"rev": False, "wrong": 0}, course="demo"),
        ev("01-boss-s1", amt=20, course="demo"), ev("01-boss-clear", amt=50, course="demo")]})
    # 库里残留清单未声明的徽章（如旧版本发放的 first）时，不计入已得数
    _sql("INSERT INTO badge_awards (user_id, course, badge_id, awarded_on) "
         "SELECT id, 'demo', 'first', CURRENT_DATE FROM users")
    d = user.get("/api/dashboard").json()
    c = next(x for x in d["courses"] if x["course"] == "demo")
    assert (c["badges_count"], c["badges_total"]) == (1, 2)
    assert [b["badge_id"] for b in d["badges"] if b["course"] == "demo"] == ["boss01"]
