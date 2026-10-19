"""命令行入口：xiaotuo start | purge-events（也可 python -m xiaotuo.cli ...）。

xiaotuo.config 在导入时就构建 settings，所以本模块顶层不导入 config 及依赖它的模块；
先按参数写好环境变量，再在函数内部导入。

start 的顺序：解析课程目录 → 生成内容缓存（courses.json / items-*.json / catalog.json）→ 迁移数据库
→ 绑定端口 → uvicorn（单进程）→ 就绪后打印 READY 行并打开浏览器。因此端口能连上时 /api/courses 一定已可用。
"""
import argparse
import ipaddress
import os
import signal
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from xiaotuo.paths import bundled_examples, user_data_dir

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 13773
READY_PREFIX = "XIAOTUO_READY"   # 稳定的就绪行：XIAOTUO_READY http://127.0.0.1:<port>/（e2e、脚本可匹配）
BUILD_OUTPUTS = ("courses.json", "catalog.json")
# 正常停止用到的信号：控制台 Ctrl+C 是 SIGINT；Windows 上 CTRL_BREAK 以 SIGBREAK 送达。
# SIGTERM 不在这里接管，kill / docker stop 保留“按信号终止”的惯例退出码。
STOP_SIGNALS = (signal.SIGINT, signal.SIGBREAK) if os.name == "nt" else (signal.SIGINT,)


class CliError(Exception):
    """给用户看的错误：打印信息后以 code 退出，不打印回溯。"""

    def __init__(self, msg: str, code: int = 2):
        super().__init__(msg)
        self.code = code


def _err(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _apply_env_file(env_file: str | None) -> None:
    """默认不读当前目录的 .env（uvx 在别的项目目录下运行时会误用其中的 DATABASE_URL 等）。
    --env-file 显式指定时才读，且只读这一个文件。"""
    if env_file:
        p = Path(env_file).expanduser()
        if not p.is_file():
            raise CliError(f"--env-file 指定的文件不存在：{p}")
        os.environ["XT_ENV_FILE"] = str(p.resolve())
    else:
        os.environ["XT_ENV_FILE"] = ""


def _apply_database_url(url: str | None) -> None:
    """--database-url 优先于环境变量 DATABASE_URL；都没有时用个人数据目录下的 SQLite。
    sqlite:/// 与 postgresql:// 由 config.normalize_database_url 换成异步驱动。"""
    if url:
        os.environ["DATABASE_URL"] = url


def _env_file_value(key: str) -> str | None:
    """--env-file 里的值（设置环境变量前判断“用户是否显式给了 X”时用）。"""
    f = os.environ.get("XT_ENV_FILE")
    if not f:
        return None
    from dotenv import dotenv_values
    return dotenv_values(f).get(key)


def _resolve_courses(arg: str | None) -> Path:
    if arg:
        p = Path(arg).expanduser().resolve()
        if not p.is_dir():
            raise CliError(f"课程目录不存在：{p}")
        return p
    p = bundled_examples()
    if p is None:
        raise CliError("找不到随包的示例课程；用 --courses <目录> 指定课程根目录")
    return p.resolve()


def _build(courses: Path, cache: Path) -> None:
    from xiaotuo.content_build import INVENTORY_CACHE, build_content, check_content
    cache.mkdir(parents=True, exist_ok=True)
    for f in [*cache.glob("items-*.json"), *(cache / n for n in BUILD_OUTPUTS)]:
        f.unlink(missing_ok=True)   # 只清理本程序生成的文件，避免课程删除后残留旧条目
    print(f"生成课程内容：{courses} → {cache}", flush=True)
    log = lambda m: print(m, flush=True)  # noqa: E731
    try:
        code = build_content(courses, cache, allow_empty=True, log=log, err=_err)
    except Exception as e:  # noqa: BLE001  课程文件格式异常（脚本里会直接回溯）：给出出错的课程与原因
        raise CliError(f"课程内容生成失败：{type(e).__name__}: {e}（课程根目录 {courses}）") from e
    if code != 0:
        raise CliError("课程内容生成失败（见上方问题）。engine=course-manifest-js 的课程须自带与当前内容一致的"
                       f" {INVENTORY_CACHE}，可在课程仓库里用 build_content.py --write-cache 生成后提交")
    if check_content(courses, cache, allow_empty=True, log=log, err=_err) != 0:
        raise CliError("课程页面与题目清单不一致（见上方问题）")


def _check_cache(cache: Path) -> None:
    missing = [n for n in BUILD_OUTPUTS if not (cache / n).is_file()]
    if missing:
        raise CliError(f"--no-build 需要已生成的内容缓存，{cache} 下缺少 {', '.join(missing)}；去掉 --no-build 重新生成")


def _bind(host: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in host.strip("[]") else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    if os.name != "nt":   # Windows 上 SO_REUSEADDR 允许重复绑定同一端口，不能用
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host.strip("[]"), port))
    except OSError as e:
        sock.close()
        raise CliError(f"无法监听 {host}:{port}（{e.strerror or e}）；端口被占用时换一个 --port") from e
    sock.set_inheritable(True)
    return sock


def _browse_url(host: str, port: int) -> str:
    if host in ("0.0.0.0", "::", "[::]", ""):
        host = "127.0.0.1"
    elif ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{port}/"


def cmd_start(a: argparse.Namespace) -> int:
    # ---- 1. 先确定全部环境变量，再导入 config ----
    _apply_env_file(a.env_file)
    _apply_database_url(a.database_url)
    courses = _resolve_courses(a.courses)
    cache = Path(a.cache_dir).expanduser().resolve() if a.cache_dir else user_data_dir() / "content"
    os.environ["COURSE_DIR"] = str(courses)
    os.environ["CONTENT_DIR"] = str(cache)
    explicit_secure = os.environ.get("COOKIE_SECURE") or _env_file_value("COOKIE_SECURE")
    if is_loopback(a.host):
        if not explicit_secure:
            os.environ["COOKIE_SECURE"] = "false"   # 本机 http://127.0.0.1 访问，Secure Cookie 浏览器不会回传
    else:
        _err(f"警告：监听非本机地址 {a.host}，局域网内其他设备可访问。登录 Cookie 仍为 Secure，"
             "需经 HTTPS 访问（反向代理）；只在可信网络中使用")

    from xiaotuo.config import settings
    from xiaotuo.db import ensure_sqlite_dir, is_sqlite

    # ---- 2. 内容缓存 ----
    if a.build:
        _build(courses, cache)
    else:
        _check_cache(cache)

    # ---- 3. 迁移（在事件循环之外；SQLite 先建库所在目录）----
    if is_sqlite(settings.database_url):
        ensure_sqlite_dir(settings.database_url)
    print("升级数据库结构…", flush=True)
    from xiaotuo.migrate import upgrade_head
    try:
        upgrade_head()
    except Exception as e:  # noqa: BLE001
        raise CliError(f"数据库迁移失败：{type(e).__name__}: {e}") from e

    # ---- 4. 监听并启动 ----
    sock = _bind(a.host, a.port)
    port = sock.getsockname()[1]
    url = _browse_url(a.host, port)
    import uvicorn
    from xiaotuo.main import app
    config = uvicorn.Config(app, workers=1, log_level=a.log_level, proxy_headers=False, access_log=False)
    server = uvicorn.Server(config)
    ready = threading.Event()   # 我们自己记录“已就绪”，退出码不依赖 uvicorn 内部属性

    def announce():
        while not server.started:
            if server.should_exit:
                return
            threading.Event().wait(0.05)
        # 就绪标记先于打印置位：看到 READY 行后立刻停止也算“跑到正常收尾”
        ready.set()
        print(f"小驼已启动：{url}（Ctrl+C 退出）", flush=True)
        print(f"{READY_PREFIX} {url}", flush=True)
        if a.browser:
            webbrowser.open(url)

    threading.Thread(target=announce, daemon=True).start()
    # uvicorn 收尾后会恢复运行前的信号处理函数，并重新发出捕获到的信号。重新发出落到 OS 默认动作
    # 时（Windows 的控制事件），进程在被杀死前没有机会返回值，所以这里把处理函数固定为解释器的
    # default_int_handler，让重新发出的信号以 KeyboardInterrupt 落回我们手里。
    previous = {sig: signal.signal(sig, signal.default_int_handler) for sig in STOP_SIGNALS}
    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        if not ready.is_set():
            raise   # 还没就绪就被打断：交给 main()，按 130 退出
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    # 退出码看自己的就绪标记，不看 uvicorn 的 Server.started：后者不是公开契约，
    # 正常停止时它当前仍为 True，一旦上游改成收尾时清零，Ctrl+C 就会静默变成非 0。
    return 0 if ready.is_set() else 1


def cmd_purge_events(a: argparse.Namespace) -> int:
    """删除早于 N 天的 progress_events（事件日志，仅供审计/排错；进度本身在 progress_items 里，不受影响）。"""
    _apply_env_file(a.env_file)
    _apply_database_url(a.database_url)
    import asyncio
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import delete, func, select

    from xiaotuo.config import settings
    from xiaotuo.db import make_engine
    from xiaotuo.models import ProgressEvent

    cutoff = datetime.now(UTC) - timedelta(days=a.older_than_days)

    async def go() -> int:
        engine = make_engine(settings.database_url)
        try:
            async with engine.begin() as conn:
                cond = ProgressEvent.received_at < cutoff
                if a.dry_run:
                    return (await conn.execute(select(func.count()).select_from(ProgressEvent).where(cond))).scalar()
                return (await conn.execute(delete(ProgressEvent).where(cond))).rowcount
        finally:
            await engine.dispose()

    try:
        n = asyncio.run(go())
    except Exception as e:  # noqa: BLE001
        raise CliError(f"清理失败：{type(e).__name__}: {e}", 1) from e
    print(f"{'would_delete' if a.dry_run else 'deleted'}={n} older_than_days={a.older_than_days} "
          f"cutoff={cutoff.isoformat().replace('+00:00', 'Z')}", flush=True)
    return 0


def _positive_int(v: str) -> int:
    n = int(v)
    if n < 1:
        raise argparse.ArgumentTypeError("须为正整数")
    return n


def _port(v: str) -> int:
    n = int(v)
    if not 0 <= n <= 65535:
        raise argparse.ArgumentTypeError("端口须在 0–65535（0 表示随机空闲端口）")
    return n


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="xiaotuo", description="小驼：本地运行课程与学习进度服务")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--database-url", help="数据库连接串（优先于环境变量 DATABASE_URL；默认个人数据目录下的 SQLite）。"
                                               "接受 sqlite:///路径 与 postgresql://…")
    common.add_argument("--env-file", help="读取指定的 .env 文件（默认不读当前目录的 .env）")

    s = sub.add_parser("start", parents=[common], help="生成课程内容、迁移数据库并启动服务")
    s.add_argument("--courses", help="课程根目录（每门课一个子目录，内含 course.json）；默认随包示例课程")
    s.add_argument("--cache-dir", help="生成内容的存放目录；默认 <个人数据目录>/content")
    s.add_argument("--build", action=argparse.BooleanOptionalAction, default=True,
                   help="启动前重新生成课程内容（默认开启；--no-build 直接用缓存）")
    s.add_argument("--host", default=DEFAULT_HOST, help=f"监听地址（默认 {DEFAULT_HOST}）")
    s.add_argument("--port", type=_port, default=DEFAULT_PORT, help=f"端口（默认 {DEFAULT_PORT}；0 为随机空闲端口）")
    s.add_argument("--no-browser", dest="browser", action="store_false", help="就绪后不打开浏览器")
    s.add_argument("--log-level", default="info", choices=["critical", "error", "warning", "info", "debug"])
    s.set_defaults(func=cmd_start)

    g = sub.add_parser("purge-events", parents=[common], help="删除早于 N 天的进度事件日志")
    g.add_argument("--older-than-days", type=_positive_int, required=True)
    g.add_argument("--dry-run", action="store_true", help="只统计将删除的条数")
    g.set_defaults(func=cmd_purge_events)
    return p


def main(argv: list[str] | None = None) -> int:
    from xiaotuo.stdio import utf8_stdio
    utf8_stdio()
    a = parser().parse_args(argv)
    try:
        return a.func(a)
    except CliError as e:
        _err(f"错误：{e}")
        return e.code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
