import os
from importlib.metadata import PackageNotFoundError, version
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from xiaotuo.paths import default_database_url, frontend_dist

DEV_VERSION = "0.0.0+dev"


def app_version() -> str:
    """包版本（发布时由 git tag 决定）；未安装为包（仓库内开发、Docker）时为 0.0.0+dev。"""
    try:
        return version("xiaotuo")
    except PackageNotFoundError:
        return DEV_VERSION


def normalize_database_url(url: str) -> str:
    """把连接串转换成异步驱动可用的格式。

    SQLite：sqlite:// 补成 sqlite+aiosqlite://。
    PostgreSQL（Neon 控制台原始连接串）：改写驱动前缀；把 sslmode 换成 asyncpg 认的 ssl；
    删掉 asyncpg 不支持的 channel_binding。
    """
    if url.startswith("sqlite://"):
        return "sqlite+aiosqlite://" + url[len("sqlite://"):]
    if url.startswith("sqlite+"):
        return url
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix):]
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "channel_binding":
            continue
        if key == "sslmode":
            key = "ssl"
        query.append((key, value))
    return urlunsplit(parts._replace(query=urlencode(query)))


class Settings(BaseSettings):
    # XT_ENV_FILE 为空字符串时不读任何 .env（测试用），默认读 .env
    model_config = SettingsConfigDict(env_file=os.environ.get("XT_ENV_FILE", ".env") or None, extra="ignore")
    # 默认个人使用的 SQLite（<用户数据目录>/xiaotuo.db）；Docker、Render、CI 显式传 PostgreSQL 连接串
    database_url: str = Field(default_factory=default_database_url)
    email_enabled: bool = False
    # 生成的内容数据目录：courses.json + items-<课程 id>.json（见 xiaotuo/content.py，build_content.py 生成）
    content_dir: str = "content"
    cookie_secure: bool = True
    # 本地运行端口与监听地址（python -m xiaotuo 读取）
    host: str = "127.0.0.1"
    port: int = 13773
    # 限流阈值倍数：生产保持 1；本地反复跑 e2e 时可设为 20 等较大值
    ratelimit_multiplier: int = 1
    app_version: str = Field(default_factory=app_version)
    # 前端构建产物；不存在时只提供 API。XT_FRONTEND_DIST（或 FRONTEND_DIST，Docker 用）覆盖，
    # 否则随包的 xiaotuo/web/，再否则仓库内 frontend/dist
    frontend_dist: str = Field(default_factory=lambda: str(frontend_dist()),
                               validation_alias=AliasChoices("XT_FRONTEND_DIST", "FRONTEND_DIST", "frontend_dist"))
    # 课程根目录（自动发现课程的 COURSE_DIR）；设置后 /course/<课程 id>/ 运行时直接读对应子目录（Docker 只读挂载），
    # 不设置时读 FRONTEND_DIST/course（构建期复制的副本）
    course_dir: str = ""

    @field_validator("database_url")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_database_url(v)


settings = Settings()
