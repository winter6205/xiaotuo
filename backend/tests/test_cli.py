"""xiaotuo.cli：start（子进程，真实端口）与 purge-events；不读当前目录 .env；不写默认个人数据目录。"""
import contextlib
import io
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.conftest import BACKEND, SAMPLE_ROOT, ev
from xiaotuo import cli
from xiaotuo.content_build import INVENTORY_CACHE

# Windows：子进程放进独立进程组，才能单独向它发 CTRL_BREAK 而不波及 pytest 自身
NEW_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
READY = re.compile(r"^XIAOTUO_READY (http://127\.0\.0\.1:(\d+)/)$", re.M)


def _isolated_env(home: Path, **extra) -> dict:
    """把所有可能的个人数据目录都指向 home（空目录），并去掉会影响结果的变量。"""
    env = {k: v for k, v in os.environ.items()
           if k not in ("DATABASE_URL", "XIAOTUO_DATA_DIR", "COURSE_DIR", "CONTENT_DIR", "COOKIE_SECURE",
                        "XT_ENV_FILE", "FRONTEND_DIST", "XT_FRONTEND_DIST", "RATELIMIT_MULTIPLIER")}
    env.update(HOME=str(home), USERPROFILE=str(home), XDG_DATA_HOME=str(home / "xdg"),
               LOCALAPPDATA=str(home / "local"), APPDATA=str(home / "roaming"), PYTHONUNBUFFERED="1",
               PYTHONPATH=os.pathsep.join(filter(None, [str(BACKEND), os.environ.get("PYTHONPATH")])))  # 仓库内未安装为包
    env.update(extra)
    return env


def _start(args, env, cwd) -> tuple[subprocess.Popen, str, list[str]]:
    p = subprocess.Popen([sys.executable, "-m", "xiaotuo.cli", "start", "--port", "0", "--no-browser", *args],
                         cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace", creationflags=NEW_GROUP)
    lines, deadline = [], time.time() + 60
    while time.time() < deadline:
        line = p.stdout.readline()
        if not line:
            break
        lines.append(line)
        if (m := READY.match(line.rstrip("\n"))):
            return p, m.group(1), lines
    p.kill()
    pytest.fail("未就绪：\n" + "".join(lines) + (p.stdout.read() or ""))


def _stop(p: subprocess.Popen) -> int:
    """正常停止（uvicorn 收尾、关闭 SQLite）：POSIX 发 SIGINT；Windows 不支持向子进程发 SIGINT，
    改为向它的独立进程组发 CTRL_BREAK（uvicorn 在 Windows 上处理 SIGBREAK）。超时再强杀。

    停止之后必须断言退出码：`xiaotuo start` 跑到正常收尾再退出 0 是对外契约
    （SKILL.md 第 4 步以“退出码全部为 0”为完成标准），只 wait 不查状态会漏掉它变成非 0 的回归。"""
    p.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
    killed_after_timeout = False
    try:
        p.wait(15)
    except subprocess.TimeoutExpired:
        killed_after_timeout = True
        p.kill()
        p.wait()
    if p.stdout:
        p.stdout.close()
    assert not killed_after_timeout, f"15 秒内没有正常退出，已强杀（退出码 {p.returncode}）"
    assert p.returncode == 0, f"正常停止后退出码应为 0，实得 {p.returncode}"
    return p.returncode


def _get(url: str, data: bytes | None = None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.headers, r.read()


def test_start_with_database_url_and_cache_dir_writes_nothing_to_user_data_dir(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"   # cwd 里放一个会误导的 .env：默认不得读取
    work.mkdir()
    (work / ".env").write_text(f"DATABASE_URL=sqlite:///{(tmp_path / 'dotenv.db').as_posix()}\n", encoding="utf-8")
    db = tmp_path / "e2e.db"
    env = _isolated_env(home, DATABASE_URL=f"sqlite:///{db.as_posix()}")
    p, url, lines = _start(["--courses", str(SAMPLE_ROOT), "--cache-dir", str(tmp_path / "cache")], env, work)
    try:
        st, h, body = _get(url + "api/courses")
        cat = json.loads(body)
        assert st == 200 and [c["id"] for c in cat["courses"]] == ["demo"]
        assert cat == json.loads((tmp_path / "cache" / "catalog.json").read_bytes())
        st, _, body = _get(url + "api/health/ready")
        assert st == 200 and json.loads(body)["db"] == "ok"
        # 回环地址：COOKIE_SECURE=false，登录 Cookie 不带 Secure（http://127.0.0.1 下浏览器才会回传）
        st, h, body = _get(url + "api/me")
        cookie = h.get("Set-Cookie")
        assert st == 200 and cookie and "secure" not in cookie.lower()
        st, h, _ = _get(url + "api/auth/register", json.dumps(
            {"email": "cli@example.com", "password": "correct-horse-battery"}).encode(),
            {"Cookie": cookie.split(";")[0], "X-CSRF-Token": json.loads(body)["csrf_token"]})
        assert st == 201 and "secure" not in h.get("Set-Cookie").lower()
    finally:
        _stop(p)
    assert db.is_file() and not (tmp_path / "dotenv.db").exists()
    assert list(home.rglob("*")) == [], list(home.rglob("*"))   # 默认个人数据目录一个文件、目录都没建


def test_start_defaults_use_user_data_dir(tmp_path):
    """不给 DATABASE_URL / --cache-dir：库与缓存都在个人数据目录（XIAOTUO_DATA_DIR 覆盖平台默认），默认示例课程。"""
    data = tmp_path / "data"
    env = _isolated_env(tmp_path / "home", XIAOTUO_DATA_DIR=str(data))
    p, url, _ = _start([], env, tmp_path)
    try:
        st, _, body = _get(url + "api/courses")
        assert st == 200 and [c["id"] for c in json.loads(body)["courses"]] == ["demo"]
    finally:
        _stop(p)
    assert (data / "xiaotuo.db").is_file() and (data / "content" / "catalog.json").is_file()


def test_start_empty_course_root_serves_empty_catalog(tmp_path):
    (tmp_path / "courses").mkdir()
    env = _isolated_env(tmp_path / "home", XIAOTUO_DATA_DIR=str(tmp_path / "data"))
    p, url, _ = _start(["--courses", str(tmp_path / "courses")], env, tmp_path)
    try:
        st, _, body = _get(url + "api/courses")
        assert st == 200 and json.loads(body)["courses"] == []
    finally:
        _stop(p)


def test_start_exit_code_does_not_follow_uvicorn_started(tmp_path, monkeypatch):
    """退出码只由自己的就绪标记决定。

    uvicorn 在正常停止时目前保留 Server.started=True，但那不是公开契约：某些版本在
    shutdown 里把它清掉。若退出码跟着这个属性走，一次正常的 Ctrl+C 就会变成非 0，
    而 .agents/skills/course-authoring/SKILL.md 第 4 步把“退出码全部为 0”当作完成标准。
    """
    import uvicorn

    a = cli.parser().parse_args(["start", "--no-browser", "--port", "0", "--courses", str(SAMPLE_ROOT),
                                 "--cache-dir", str(tmp_path / "cache"),
                                 "--database-url", f"sqlite:///{(tmp_path / 'x.db').as_posix()}"])
    out = io.StringIO()
    # 内容生成与迁移不是这条契约的一部分；只留下“就绪 → 停止 → 退出码”
    monkeypatch.setattr(cli, "_build", lambda courses, cache: None)
    monkeypatch.setattr("xiaotuo.migrate.upgrade_head", lambda: None)

    class FutureUvicornServer:
        """A uvicorn.Server that clears .started on the way out, the way a later release may."""

        def __init__(self, config):
            self.started = False
            self.should_exit = False

        def run(self, sockets=None):
            self.started = True                       # startup, as uvicorn does today
            deadline = time.time() + 20
            while "XIAOTUO_READY" not in out.getvalue() and time.time() < deadline:
                time.sleep(0.01)
            self.started = False                      # the upstream change we must not depend on

    monkeypatch.setattr(uvicorn, "Server", FutureUvicornServer)
    saved_env = dict(os.environ)   # cmd_start 会写 XT_ENV_FILE / COURSE_DIR / CONTENT_DIR / COOKIE_SECURE
    try:
        with contextlib.redirect_stdout(out):
            rc = cli.cmd_start(a)
    finally:
        os.environ.clear()
        os.environ.update(saved_env)
    assert "XIAOTUO_READY" in out.getvalue(), out.getvalue()
    assert rc == 0, f"normal stop after ready must exit 0, got {rc}"


def _run(args, env, cwd):
    return subprocess.run([sys.executable, "-m", "xiaotuo.cli", *args], cwd=cwd, env=env, capture_output=True,
                          text=True, encoding="utf-8", timeout=60)


def test_start_errors_are_clear(tmp_path):
    env = _isolated_env(tmp_path / "home", XIAOTUO_DATA_DIR=str(tmp_path / "data"))
    r = _run(["start", "--no-browser", "--no-build", "--cache-dir", str(tmp_path / "nocache")], env, tmp_path)
    assert r.returncode == 2 and "--no-build" in r.stderr and "catalog.json" in r.stderr
    r = _run(["start", "--no-browser", "--no-build", "--host", "0.0.0.0", "--cache-dir", str(tmp_path / "x")],
             env, tmp_path)
    assert r.returncode == 2 and "警告：监听非本机地址 0.0.0.0" in r.stderr   # 非回环：保留 Secure Cookie 并警告
    r = _run(["start", "--no-browser", "--courses", str(tmp_path / "missing")], env, tmp_path)
    assert r.returncode == 2 and "课程目录不存在" in r.stderr
    # engine=course-manifest-js 且没有清单缓存：说明须自带 INVENTORY_CACHE（.xiaotuo-inventory.json），不起服务
    root = tmp_path / "cmj"
    d = root / "c1"
    (d / "assets").mkdir(parents=True)
    (d / "course.json").write_text(json.dumps({"schema": 1, "id": "c1", "title": "课程", "order": 1,
                                               "accent": "#112233", "state_version": 1,
                                               "engine": "course-manifest-js"}), encoding="utf-8")
    (d / "assets" / "course-manifest.js").write_text('window.COURSE_MANIFEST={"badges":{}};\n', encoding="utf-8")
    (d / "assets" / "course.js").write_text("var BADGES=[['b1','徽章']];\nvar HOME_PAGE='00';\n", encoding="utf-8")
    (d / "00-x.html").write_text("<html></html>\n", encoding="utf-8")
    r = _run(["start", "--no-browser", "--courses", str(root), "--cache-dir", str(tmp_path / "c")],
             {**env, "PATH": ""}, tmp_path)   # PATH 置空：没有 node 可用
    assert r.returncode == 2 and INVENTORY_CACHE in r.stderr, r.stdout + r.stderr
    assert not (tmp_path / "data" / "xiaotuo.db").exists()   # 内容出错时不迁移、不建库
    # 清单本身读不了（格式不对）：同样是清楚的错误而不是回溯
    (d / "assets" / "course-manifest.js").write_text("broken\n", encoding="utf-8")
    r = _run(["start", "--no-browser", "--courses", str(root), "--cache-dir", str(tmp_path / "c")], env, tmp_path)
    assert r.returncode == 2 and "Traceback" not in r.stderr and "课程内容生成失败" in r.stderr, r.stderr


def test_env_file_is_opt_in(tmp_path):
    (tmp_path / ".env").write_text("COOKIE_SECURE=false\nRATELIMIT_MULTIPLIER=7\n", encoding="utf-8")
    other = tmp_path / "other.env"
    other.write_text("RATELIMIT_MULTIPLIER=3\n", encoding="utf-8")
    code = ("import sys; from xiaotuo import cli; cli._apply_env_file(sys.argv[1] or None); "
            "from xiaotuo.config import settings as s; print(s.ratelimit_multiplier)")
    env = _isolated_env(tmp_path / "home")

    def val(arg):
        r = subprocess.run([sys.executable, "-c", code, arg], cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()
    assert val("") == "1"                 # 默认不读 cwd/.env
    assert val(str(other)) == "3"         # --env-file 显式指定才读
    r = _run(["start", "--env-file", str(tmp_path / "nope.env")], env, tmp_path)
    assert r.returncode == 2 and "--env-file" in r.stderr


def test_is_loopback():
    assert all(cli.is_loopback(h) for h in ("127.0.0.1", "localhost", "::1", "[::1]", "127.1.2.3"))
    assert not any(cli.is_loopback(h) for h in ("0.0.0.0", "192.168.1.5", "::", "example.com"))
    assert cli._browse_url("0.0.0.0", 8000) == "http://127.0.0.1:8000/"
    assert cli._browse_url("::1", 8000) == "http://[::1]:8000/"


def test_purge_events(user, monkeypatch, capsys):
    """在当前测试库（sqlite 或 postgres）上删早于 N 天的事件；逐题进度不受影响。"""
    from xiaotuo.models import ProgressEvent
    from tests.test_dialects import _with_session, run
    from sqlalchemy import func, select, update

    user.post("/api/progress/alpha/events", {"events": [ev("01-done-a", kind="done", amt=10),
                                                         ev("01-1-quiz-x", amt=5)]})

    async def age(s):
        first = (await s.execute(select(func.min(ProgressEvent.id)))).scalar()
        await s.execute(update(ProgressEvent).where(ProgressEvent.id == first)
                        .values(received_at=datetime.now(UTC) - timedelta(days=200)))
        await s.commit()
    run(_with_session(age))
    monkeypatch.setenv("XT_ENV_FILE", "")
    assert cli.main(["purge-events", "--older-than-days", "180", "--dry-run"]) == 0
    assert "would_delete=1 " in capsys.readouterr().out
    assert cli.main(["purge-events", "--older-than-days", "180"]) == 0
    assert re.search(r"^deleted=1 older_than_days=180 cutoff=\S+Z$", capsys.readouterr().out, re.M)

    async def count(s):
        return (await s.execute(select(func.count()).select_from(ProgressEvent))).scalar()
    assert run(_with_session(count)) == 1
    assert set(user.get("/api/progress/alpha").json()["state"]["xp"]) == {"01-done-a", "01-1-quiz-x"}
    with pytest.raises(SystemExit):
        cli.main(["purge-events", "--older-than-days", "0"])
