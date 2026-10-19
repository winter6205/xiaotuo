"""Cross-platform (Windows) constraints for the migration and CLI entry points.

Windows reads text files with the ANSI code page (cp1252), not UTF-8, so any
locale-encoded read of a UTF-8 file holding non-ASCII content fails there. Alembic
reads its ini with encoding="locale", which makes a non-ASCII ini abort every
migration command with exit code 1. These tests assert the rules on any platform.
"""
import io
import os
import subprocess
import sys

import pytest

from tests.conftest import BACKEND
from xiaotuo import migrate
from xiaotuo.stdio import utf8_stdio

PY = sys.executable


def _alembic(*args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "alembic", *args], cwd=BACKEND,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env={**os.environ, **env})


def test_alembic_ini_files_are_ascii():
    """configparser / logging.fileConfig read ini files with the locale encoding; keep them ASCII."""
    for p in (BACKEND / "alembic.ini", BACKEND / "xiaotuo" / "migrations" / "alembic.ini"):
        p.read_bytes().decode("ascii")


def test_alembic_cli_runs_under_a_byte_oriented_locale(tmp_path):
    """Run the migration CLI the way the test session does, with the locale encoding forced to a
    single-byte one (POSIX LC_ALL=C; on Windows that is the fixed ANSI code page). Reproduces the
    windows-latest failure on Linux when an ini stops being ASCII."""
    if os.name == "nt" or not str(BACKEND).isascii():
        pytest.skip("POSIX locale override; the repo path itself must be ASCII")
    env = {"LC_ALL": "C", "PYTHONCOERCECLOCALE": "0", "PYTHONUTF8": "0",
           "DATABASE_URL": "sqlite+aiosqlite:///" + (tmp_path / "locale.db").as_posix()}
    preferred = subprocess.run([PY, "-c", "import locale; print(locale.getpreferredencoding(False))"],
                               cwd=BACKEND, env={**os.environ, **env},
                               capture_output=True, text=True, encoding="utf-8")
    if preferred.stdout.strip().lower().replace("-", "").replace("_", "") == "utf8":
        pytest.skip("platform keeps UTF-8 under LC_ALL=C, nothing to reproduce")
    run = _alembic("upgrade", "head", env=env)
    assert run.returncode == 0, run.stdout + run.stderr


def test_programmatic_migration_config_reads_no_ini():
    cfg = migrate.alembic_config()
    assert cfg.config_file_name is None
    assert migrate.current_heads() == {"0001_baseline"}


def test_utf8_stdio_reconfigures_non_tty_streams(monkeypatch):
    raw = io.BytesIO()
    out = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="utf-8"))
    utf8_stdio()
    print("course title", file=out)
    out.flush()
    assert raw.getvalue().decode("utf-8").strip() == "course title"
