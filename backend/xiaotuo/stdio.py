"""命令行输出编码：Windows 上 stdout/stderr 接管道或重定向到文件时按本地代码页（如 cp1252）编码，
打印中文会抛 UnicodeEncodeError。命令行入口（xiaotuo CLI、scripts/*.py）启动时调用 utf8_stdio()：
非终端的流改为 UTF-8；终端（Windows 控制台本就走 Unicode API）不动。不依赖 PYTHONUTF8。"""
import sys


def utf8_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        enc = (getattr(s, "encoding", None) or "").lower().replace("-", "").replace("_", "")
        if s is None or enc == "utf8" or not hasattr(s, "reconfigure"):
            continue
        try:
            if s.isatty():
                continue
        except (ValueError, OSError):
            continue
        s.reconfigure(encoding="utf-8", errors="backslashreplace")
