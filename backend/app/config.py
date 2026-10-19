import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """把 Neon 控制台的连接串转换成 asyncpg 可用的格式。

    改写驱动前缀；把 sslmode 换成 asyncpg 认的 ssl；删掉 asyncpg 不支持的 channel_binding。
    """
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
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/xiaotuo"
    email_enabled: bool = False
    # 生成的内容数据目录：courses.json + items-<课程 id>.json（见 app/content.py，build_content.py 生成）
    content_dir: str = "content"
    cookie_secure: bool = True
    # 本地运行端口与监听地址（python -m app 读取）
    host: str = "127.0.0.1"
    port: int = 13773
    # 限流阈值倍数：生产保持 1；本地反复跑 e2e 时可设为 20 等较大值
    ratelimit_multiplier: int = 1
    app_version: str = "0.2.2"
    # 前端构建产物（含 course/<课程 id>/ 教材页）；不存在时只提供 API
    frontend_dist: str = str(Path(__file__).resolve().parents[2] / "frontend" / "dist")
    # 课程根目录（自动发现课程的 COURSE_DIR）；设置后 /course/<课程 id>/ 运行时直接读对应子目录（Docker 只读挂载），
    # 不设置时读 FRONTEND_DIST/course（构建期复制的副本）
    course_dir: str = ""

    @field_validator("database_url")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_database_url(v)


settings = Settings()
