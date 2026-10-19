"""Pin how the default SQLite URL round-trips, and why it must not be percent-encoded.

A code review claimed xiaotuo.paths.default_database_url() must quote the data-dir path because
"URL parsers" would mangle spaces, '#' and '%'. It must not. Two parsers read this URL:

1. sqlalchemy.engine.make_url keeps everything after the authority as the database name, so a
   space, a '#' and a '%' survive byte-identical (urllib.parse.urlsplit is not what reads it).
2. alembic's Config stores sqlalchemy.url in a configparser with BasicInterpolation, and
   before_set() rejects any literal '%' in the value: ValueError: invalid interpolation syntax.
   Percent-encoding would therefore put %20 into every path containing a space -- including the
   common profile directories with a space in the account name -- and break those at migration.

A data directory whose name contains '%' already fails before SQLAlchemy is consulted: the CLI
wraps upgrade_head() and exits 2 with 错误：数据库迁移失败：ValueError: invalid interpolation
syntax..., so the app never opens some other file silently. Adding quote() would turn that loud,
rare failure into a silent one for a much larger set of paths.
"""
import pytest
from alembic.config import Config
from sqlalchemy.engine.url import make_url

from xiaotuo.paths import default_database_url, user_data_dir

# Data directories a real install may meet: plain, a space, a '#', a Windows drive letter
# (paths.py writes it with as_posix()), and a UNC-style path with an extra leading slash.
AWKWARD_DATA_DIRS = [
    "/var/lib/xiaotuo",
    "/srv/John Smith/.xiaotuo",
    "/tmp/xiaotuo#1",
    "C:/ProgramData/xiaotuo",
    "//server/share/xiaotuo",
]

SCHEME_PREFIX = "sqlite+aiosqlite:///"


@pytest.mark.parametrize("data_dir", AWKWARD_DATA_DIRS)
def test_default_database_url_round_trips_through_make_url(data_dir, monkeypatch):
    monkeypatch.setenv("XIAOTUO_DATA_DIR", data_dir)
    path = (user_data_dir() / "xiaotuo.db").as_posix()
    parsed = make_url(default_database_url())
    assert parsed.database == path
    # Parsed as a file path, not as an authority: a misparse would show up as host/port being set.
    assert parsed.get_driver_name() == "aiosqlite"
    assert not parsed.host and not parsed.port and not parsed.username and not parsed.password


@pytest.mark.parametrize("data_dir", AWKWARD_DATA_DIRS)
def test_default_database_url_does_not_percent_encode(data_dir, monkeypatch):
    """The URL carries the path verbatim after the scheme prefix (no quote(), no escaping)."""
    monkeypatch.setenv("XIAOTUO_DATA_DIR", data_dir)
    url = default_database_url()
    assert url.startswith(SCHEME_PREFIX)
    assert url[len(SCHEME_PREFIX):] == (user_data_dir() / "xiaotuo.db").as_posix()


@pytest.mark.parametrize("data_dir", AWKWARD_DATA_DIRS)
def test_default_database_url_survives_alembic_config(data_dir, monkeypatch):
    """The migration step reads the URL through configparser interpolation; unquoted paths pass."""
    monkeypatch.setenv("XIAOTUO_DATA_DIR", data_dir)
    config = Config()
    config.set_main_option("script_location", "xiaotuo:migrations")
    config.set_main_option("sqlalchemy.url", default_database_url())
    assert make_url(config.get_main_option("sqlalchemy.url")).database == (
        user_data_dir() / "xiaotuo.db").as_posix()


def test_percent_in_data_dir_is_rejected_by_alembic_not_silently_decoded(monkeypatch):
    """Why quote() is off the table: '%' cannot appear in sqlalchemy.url at all.

    A literal %20 in the directory name reaches make_url() as a space if the CLI is skipped, so
    pinning only that would be misleading. Through the real route it dies here instead, and the
    CLI turns it into exit 2 (see cmd_start's upgrade_head wrapper). Percent-encoding every path
    would move this rejection onto paths with a space.
    """
    monkeypatch.setenv("XIAOTUO_DATA_DIR", "/tmp/xt-50%off")
    config = Config()
    with pytest.raises(ValueError, match="invalid interpolation syntax"):
        config.set_main_option("sqlalchemy.url", default_database_url())
