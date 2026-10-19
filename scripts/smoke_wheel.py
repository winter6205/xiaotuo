#!/usr/bin/env python3
"""Post-install smoke test for the xiaotuo wheel (Linux, macOS, Windows).

Usage: python scripts/smoke_wheel.py <wheel or dist dir> <examples dir> [--cases default,courses] [--timeout 90]

Installs the wheel into a fresh virtual environment with uv, then for each case
starts `xiaotuo start --host 127.0.0.1 --port 0 --no-browser`:
  default  no --courses (bundled sample courses); only XIAOTUO_DATA_DIR is set,
           so the default SQLite database must land in that directory
  courses  --courses <examples dir>; DATABASE_URL points at SQLite in the temp dir
Each run: a decoy .env in the working directory (must not be read); on POSIX,
HOME and XDG dirs point into the temp dir; the port is taken from the
XIAOTUO_READY line; ready means GET /api/courses returns 200. Then checks
/api/health, /api/health/ready (db ok, real version), /api/courses (non-empty),
/ (frontend HTML), one course page, and a 404 for an unknown /api path.
Afterwards: only the temp data dir was written (HOME on POSIX, the working
directory and the venv are unchanged).
"""
import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

WINDOWS = os.name == "nt"
READY_RE = re.compile(r"^XIAOTUO_READY (http://127\.0\.0\.1:\d+/)\s*$")
STRIP_ENV = ("DATABASE_URL", "COURSE_DIR", "CONTENT_DIR", "XT_ENV_FILE", "FRONTEND_DIST",
             "HOST", "PORT", "COOKIE_SECURE")
DECOY_ENV = "DATABASE_URL=postgresql://decoy:decoy@127.0.0.1:1/decoy\nPORT=1\nCOURSE_DIR=/nonexistent\n"


class SmokeError(Exception):
    pass


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def snapshot(root: Path) -> set[str]:
    out = set()
    for p in root.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            out.add(p.relative_to(root).as_posix())
    return out


def get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return 0, b""


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if WINDOWS:
        proc.terminate()
    else:
        proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        if not WINDOWS:
            raise SmokeError("did not exit within 15 s after SIGINT")


def run_case(name: str, exe: Path, root: Path, examples: Path, timeout: float) -> None:
    case = root / name
    home, work, data = case / "home", case / "work", case / "data"
    for d in (home, work):
        d.mkdir(parents=True)
    (work / ".env").write_text(DECOY_ENV, encoding="utf-8")

    # Drop app settings inherited from the caller so only the packaged defaults apply
    env = {k: v for k, v in os.environ.items()
           if k not in STRIP_ENV and not k.startswith(("XIAOTUO_", "XT_"))}
    env["XIAOTUO_DATA_DIR"] = str(data)
    env["PYTHONIOENCODING"] = "utf-8"
    if not WINDOWS:
        env.update(HOME=str(home), XDG_DATA_HOME=str(home / ".local/share"),
                   XDG_CACHE_HOME=str(home / ".cache"), XDG_CONFIG_HOME=str(home / ".config"))
    args = [str(exe), "start", "--host", "127.0.0.1", "--port", "0", "--no-browser"]
    db_file = data / "xiaotuo.db"
    if name == "courses":
        db_file = data / "explicit.db"
        env["DATABASE_URL"] = "sqlite:///" + db_file.as_posix()
        args += ["--courses", str(examples)]

    print(f"== {name}: {' '.join(args[1:])}", flush=True)
    log: list[str] = []
    proc = subprocess.Popen(args, cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    found: dict[str, str] = {}

    def reader() -> None:
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            log.append(line)
            m = READY_RE.match(line)
            if m and "url" not in found:
                found["url"] = m.group(1)

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        deadline = time.monotonic() + timeout
        while "url" not in found:
            if proc.poll() is not None:
                raise SmokeError(f"process exited early with code {proc.returncode}")
            if time.monotonic() > deadline:
                raise SmokeError(f"no XIAOTUO_READY line within {timeout:.0f} s")
            time.sleep(0.2)
        url = found["url"]
        while get(url + "api/courses")[0] != 200:
            if time.monotonic() > deadline:
                raise SmokeError("/api/courses did not return 200")
            time.sleep(0.2)
        print(f"ready: {url}", flush=True)

        for path in ("api/health", "api/health/ready", "api/courses", ""):
            status, body = get(url + path)
            if status != 200:
                raise SmokeError(f"/{path} returned {status}: {body[:300]!r}")
            print(f"ok 200 /{path}", flush=True)
        ready = json.loads(get(url + "api/health/ready")[1])
        if ready.get("db") != "ok" or not ready.get("version") or ready["version"] == "0.0.0+dev":
            raise SmokeError(f"/api/health/ready unexpected: {ready}")
        courses = json.loads(get(url + "api/courses")[1])["courses"]
        if not courses:
            raise SmokeError("/api/courses returned no courses")
        page = f"course/{courses[0]['id']}/{courses[0]['pages'][0]['file']}"
        if get(url + urllib.parse.quote(page))[0] != 200:
            raise SmokeError(f"/{page} did not return 200")
        print(f"ok 200 /{page}", flush=True)
        status, body = get(url)
        if b"<!doctype html" not in body[:200].lower():
            raise SmokeError("/ is not the frontend HTML")
        if get(url + "api/no-such")[0] != 404:
            raise SmokeError("unknown /api path should return 404")
        print(f"ok version {ready['version']}, {len(courses)} course(s)", flush=True)
    except SmokeError:
        stop(proc)
        t.join(timeout=5)
        print("--- server log ---\n" + "\n".join(log), file=sys.stderr)
        raise
    stop(proc)
    t.join(timeout=5)

    if not db_file.is_file():
        raise SmokeError(f"database not created at {db_file}")
    if name == "courses" and (data / "xiaotuo.db").exists():
        raise SmokeError("DATABASE_URL was set but the default database was written")
    if not WINDOWS and any(home.iterdir()):
        raise SmokeError(f"files written under HOME: {sorted(snapshot(home))}")
    if sorted(p.name for p in work.iterdir()) != [".env"]:
        raise SmokeError(f"files written in the working directory: {sorted(p.name for p in work.iterdir())}")
    print(f"ok only wrote {data}: {sorted(snapshot(data))}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("wheel")
    ap.add_argument("examples")
    ap.add_argument("--cases", default="default,courses")
    ap.add_argument("--timeout", type=float, default=90)
    a = ap.parse_args()
    wheel, examples = Path(a.wheel).resolve(), Path(a.examples).resolve()
    if wheel.is_dir():
        found = sorted(wheel.glob("xiaotuo-*.whl"))
        if len(found) != 1:
            print(f"expected exactly 1 wheel in {wheel}, found {len(found)}", file=sys.stderr)
            return 2
        wheel = found[0]
    if not wheel.is_file() or not examples.is_dir():
        print("wheel or examples dir not found", file=sys.stderr)
        return 2
    uv = shutil.which("uv")
    if not uv:
        print("uv is required", file=sys.stderr)
        return 2

    root = Path(tempfile.mkdtemp(prefix="xt-smoke-"))
    try:
        venv = root / "venv"
        run([uv, "venv", "-q", "--python", "3.12", str(venv)])
        run([uv, "pip", "install", "-q", "--python", str(venv), str(wheel)])
        exe = venv / ("Scripts/xiaotuo.exe" if WINDOWS else "bin/xiaotuo")
        if not exe.is_file():
            raise SmokeError("the wheel did not install a xiaotuo command")
        before = snapshot(venv)
        for case in a.cases.split(","):
            run_case(case.strip(), exe, root, examples, a.timeout)
        added = snapshot(venv) - before
        if added:
            raise SmokeError(f"files written inside the venv: {sorted(added)}")
        print(f"smoke test passed: {wheel.name}")
        return 0
    except SmokeError as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
