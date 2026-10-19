"""以编程方式运行 Alembic 迁移：迁移脚本随包分发在 xiaotuo/migrations/，不依赖当前工作目录。

配置全部在代码里设置，不读取 alembic.ini：ini 由 configparser 按本地编码读取（Windows 上常为 cp1252），
随包的 ini 也就不会成为跨平台问题；日志由调用方（CLI / uvicorn）负责，这里不配置。
"""
from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path

from alembic import command
from alembic.config import Config


def migrations_dir():
    return files("xiaotuo") / "migrations"


def alembic_config(script_location: Path | str | None = None) -> Config:
    cfg = Config()   # 不带 ini 文件
    cfg.set_main_option("script_location", str(script_location or migrations_dir()))
    cfg.set_main_option("path_separator", "os")
    cfg.attributes["skip_logging"] = True
    return cfg


@contextmanager
def _config():
    with as_file(migrations_dir()) as path:   # 普通安装（目录）时即原路径
        yield alembic_config(path)


def upgrade_head() -> None:
    """升级到 head。env.py 内部用 asyncio.run，必须在事件循环之外调用（CLI 在启动 uvicorn 之前）。"""
    with _config() as cfg:
        command.upgrade(cfg, "head")


def current_heads() -> set[str]:
    from alembic.script import ScriptDirectory
    with _config() as cfg:
        return set(ScriptDirectory.from_config(cfg).get_heads())
