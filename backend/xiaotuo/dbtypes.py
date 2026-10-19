"""方言无关的列类型与约束：模型（models.py）与基线迁移（0001_baseline）共用。

PostgreSQL 上生成的 DDL 与原先的原生写法逐字一致（JSONB、INET、uuid、timestamptz、bigserial、now()），
SQLite 上换成等价的可移植写法。新增方言差异都集中在这里。
"""
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.types import TypeDecorator

# JSON 文档：PG 用 JSONB（只整值存取，代码里没有 JSONB 运算符）；SQLite 存 JSON 文本
JSONType = sa.JSON().with_variant(JSONB(astext_type=sa.Text()), "postgresql")
# IP 地址：PG 用 INET；SQLite 存文本（routers/auth.py 的 _inet() 已在 Python 里规范化）
InetType = sa.Text().with_variant(INET(), "postgresql")
# 自增主键：PG 为 bigserial；SQLite 只有 INTEGER PRIMARY KEY 才是 rowid 自增
BigIntPK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
# 外部生成的 UUID（字符串进出）：PG 为原生 uuid；SQLite 存 32 位十六进制
UuidStr = sa.Uuid(as_uuid=False)


class UTCDateTime(TypeDecorator):
    """带时区时间：进出一律是 UTC 的 aware datetime。

    PG：timestamptz，驱动本身返回 aware 值，这里统一换算到 UTC。
    SQLite：没有时区类型，写入前换算到 UTC 并去掉 tzinfo（文本 YYYY-MM-DD HH:MM:SS.ffffff），
    读出后补上 UTC。拒绝写入 naive 值，避免把本地时间当成 UTC 存进去。
    """
    impl = sa.DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            raise ValueError("UTCDateTime 只接受带时区的 datetime")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):  # 聚合等未经类型处理的路径
            value = datetime.fromisoformat(value)
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class utcnow(FunctionElement):
    """服务端当前时间默认值：PG 渲染为 now()（与原 DDL 一致）；SQLite 为毫秒精度的 UTC 文本，
    格式与 UTCDateTime 写入的一致，可直接按字符串比较大小。"""
    type = sa.DateTime(timezone=True)
    inherit_cache = True


@compiles(utcnow)
def _utcnow_default(element, compiler, **kw):
    return "now()"


@compiles(utcnow, "sqlite")
def _utcnow_sqlite(element, compiler, **kw):
    return "(strftime('%Y-%m-%d %H:%M:%f', 'now'))"


# 课程 id 格式（与 catalog.py ID_RE 一致）：^[a-z][a-z0-9_]{0,15}$。库里只约束格式，不列举具体课程
COURSE_CHECK_PG = "course ~ '^[a-z][a-z0-9_]{0,15}$'"
COURSE_CHECK_SQLITE = ("length(course) BETWEEN 1 AND 16 AND substr(course, 1, 1) BETWEEN 'a' AND 'z'"
                       " AND course NOT GLOB '*[^a-z0-9_]*'")


def course_check_sql(dialect_name: str) -> str:
    return COURSE_CHECK_PG if dialect_name == "postgresql" else COURSE_CHECK_SQLITE


def course_checks(table: str) -> tuple[sa.CheckConstraint, sa.CheckConstraint]:
    """模型用：两种方言各声明一份同名约束，建表时只生成当前方言那一份。"""
    name = f"ck_{table}_course"
    return (sa.CheckConstraint(COURSE_CHECK_PG, name=name).ddl_if(dialect="postgresql"),
            sa.CheckConstraint(COURSE_CHECK_SQLITE, name=name).ddl_if(dialect="sqlite"))


def utc_iso(t: datetime) -> str:
    """API 响应里的时间：RFC 3339、UTC、以 Z 结尾。naive 值直接报错，不允许静默输出无时区时间。"""
    if t.tzinfo is None:
        raise ValueError("响应中的时间必须带时区")
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z")
