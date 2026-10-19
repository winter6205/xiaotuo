"""文件位置（不导入 config，CLI 在设置环境变量之前也能用）。

随包资源用 importlib.resources 定位：安装后在 site-packages/xiaotuo/ 下，仓库内即 backend/xiaotuo/。
打包前由 scripts/prepare_pkg.sh 把前端产物复制到 xiaotuo/web/、示例课程复制到 xiaotuo/examples/（均 gitignore）；
仓库内开发时这两处不存在，回退到仓库根的 frontend/dist 与 examples/。
"""
import os
from importlib.resources import files
from pathlib import Path

import platformdirs

PACKAGE_DIR = Path(str(files("xiaotuo")))
REPO_ROOT = PACKAGE_DIR.parents[1]   # 仓库内为仓库根；安装后指向 site-packages 的上级，不会被用到


def user_data_dir() -> Path:
    """个人数据目录（SQLite 库、内容缓存）：XIAOTUO_DATA_DIR 优先，否则按平台惯例
    （Linux ~/.local/share/xiaotuo，macOS ~/Library/Application Support/xiaotuo，Windows %LOCALAPPDATA%\\xiaotuo）。
    只计算路径，不创建目录。"""
    return Path(os.environ.get("XIAOTUO_DATA_DIR") or platformdirs.user_data_dir("xiaotuo", appauthor=False))


def default_database_url() -> str:
    # as_posix：Windows 盘符路径写成 sqlite+aiosqlite:///C:/...
    return "sqlite+aiosqlite:///" + (user_data_dir() / "xiaotuo.db").as_posix()


def frontend_dist() -> Path:
    """前端产物：随包的 xiaotuo/web/，否则仓库内的 frontend/dist（开发）。环境变量覆盖由 config 处理。"""
    web = PACKAGE_DIR / "web"
    if (web / "index.html").is_file():
        return web
    return REPO_ROOT / "frontend" / "dist"


def bundled_examples() -> Path | None:
    """默认课程目录：随包的 xiaotuo/examples/，否则仓库根的 examples/（开发）。"""
    for p in (PACKAGE_DIR / "examples", REPO_ROOT / "examples"):
        if p.is_dir():
            return p
    return None
