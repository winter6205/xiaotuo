"""目录首页（00，graduation=false）的 Boss：徽章、快照、学习中心照常；grad 判定排除它（同 course.js gradOK）。"""
from tests.conftest import ev
from tests.test_import_reset_dashboard import blank, imp


def test_home_boss_event_badge_snapshot_dashboard(user):
    r = user.post("/api/progress/alpha/events", {"events": [ev("00-boss-s1", amt=20), ev("00-boss-clear", amt=50)]}).json()
    assert "boss00" in r["new_badges"] and "grad" not in r["new_badges"]
    st = user.get("/api/progress/alpha").json()["state"]
    assert "boss00" in st["badges"] and st["data"] == {"cleared.00": 1}
    ch00 = user.get("/api/dashboard").json()["courses"][0]["chapters"][0]
    assert ch00["chapter_id"] == "00" and ch00["has_boss"] is True and ch00["boss_cleared"] is True


def test_home_boss_import_badge(user):
    r = imp(user, blank(xp={"00-boss-clear": 50}, badges={"boss00": "2026-10-18"})).json()
    assert "boss00" in r["badges_added"]


def test_grad_excludes_home_chapter(user):
    st = blank(done={"01-done-a": 1, "01-done-b": 1, "02-done-a": 1},
               xp={"01-done-a": 10, "01-done-b": 10, "02-done-a": 10, "01-boss-clear": 50})
    r = imp(user, st).json()   # 00 的小节与 Boss 都没做
    assert "grad" in r["badges_added"] and "boss00" not in r["badges_added"]
