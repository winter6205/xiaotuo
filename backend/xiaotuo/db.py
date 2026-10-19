"""数据库引擎：PostgreSQL（asyncpg）或 SQLite（aiosqlite，个人单进程使用）。

SQLite 连接设置：WAL（多读单写）、busy_timeout（等待写锁而不是立即报 database is locked）、
foreign_keys=ON（否则 ondelete=CASCADE 不生效）。事务一律以 BEGIN IMMEDIATE 开始：一开始就拿写锁，
避免 WAL 下「先读后写」的事务在别的连接提交后升级失败（SQLITE_BUSY_SNAPSHOT，busy_timeout 无效）。
"""
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from xiaotuo.config import settings

SQLITE_PRAGMAS = ("PRAGMA journal_mode=WAL", "PRAGMA busy_timeout=5000", "PRAGMA foreign_keys=ON",
                  "PRAGMA synchronous=NORMAL")


class Base(DeclarativeBase):
    pass


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def ensure_sqlite_dir(url: str) -> None:
    """SQLite 文件所在目录不存在时创建（用户数据目录首次运行时为空）。"""
    if is_sqlite(url):
        db = make_url(url).database
        if db and db != ":memory:" and not db.startswith("file:"):
            Path(db).expanduser().parent.mkdir(parents=True, exist_ok=True)


def make_engine(url: str, **kw) -> AsyncEngine:
    if not is_sqlite(url):
        return create_async_engine(url, pool_pre_ping=True, **kw)
    ensure_sqlite_dir(url)
    eng = create_async_engine(url, **kw)

    @event.listens_for(eng.sync_engine, "connect")
    def _on_connect(dbapi_conn, _record):
        dbapi_conn.isolation_level = None  # 由下面的 begin 事件自己发 BEGIN
        cur = dbapi_conn.cursor()
        for p in SQLITE_PRAGMAS:
            cur.execute(p)
        cur.close()

    @event.listens_for(eng.sync_engine, "begin")
    def _on_begin(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return eng


engine = make_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
