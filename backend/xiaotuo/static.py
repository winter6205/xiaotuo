"""同源托管外层 SPA 与教材页（docs/deploy.md 第 4 条静态规则）。

- 先匹配 FRONTEND_DIST 下的真实文件（目录则找其 index.html）；
- /api/** 不回退，未知接口返回 JSON 404；
- /course/** 与 /assets/** 未命中返回 404，不回退；
- 其余 GET/HEAD 回退 index.html（history 路由）。
"""
import logging
import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response

from xiaotuo.config import settings
from xiaotuo.content import get_course
from xiaotuo.errors import problem

log = logging.getLogger(__name__)
for ext, mt in ((".js", "text/javascript"), (".mjs", "text/javascript"), (".css", "text/css"),
                (".html", "text/html"), (".svg", "image/svg+xml"), (".json", "application/json"),
                (".webmanifest", "application/manifest+json"), (".woff2", "font/woff2")):
    mimetypes.add_type(mt, ext)

NO_FALLBACK = ("course", "assets")
LONG_CACHE = "public, max-age=31536000, immutable"  # Vite 产物文件名带哈希


def _file(dist: Path, rel: str) -> Path | None:
    p = (dist / rel).resolve()
    if not p.is_relative_to(dist):
        return None
    if p.is_dir():
        p = p / "index.html"
    return p if p.is_file() else None


def _send(p: Path, dist: Path) -> FileResponse:
    rel = p.relative_to(dist).parts
    cache = LONG_CACHE if rel[0] == "assets" else "no-cache"
    resp = FileResponse(p, headers={"Cache-Control": cache})
    if p.suffix in (".html", ".js", ".css", ".mjs", ".svg", ".json"):
        resp.media_type = resp.headers["content-type"] = f"{mimetypes.guess_type(p.name)[0]}; charset=utf-8"
    return resp


def _course_file(path: str) -> Path | None:
    """COURSE_DIR 已设置时，按构建期同样的范围（顶层 *.html 与 assets/**）从课程目录取文件。
    课程 id → 子目录取自生成的 courses.json（dir 字段），与自动发现结果一致。"""
    parts = path.split("/")
    if len(parts) < 3 or parts[0] != "course":
        return None
    c = get_course(parts[1])
    if not c or not c.dir or "/" in c.dir or c.dir in (".", ".."):
        return None
    root = Path(settings.course_dir).resolve()
    base = (root / c.dir).resolve()
    if not base.is_relative_to(root):
        return None
    rest = parts[2:]
    if not ((len(rest) == 1 and rest[0].endswith(".html")) or (rest[0] == "assets" and "__pycache__" not in rest)):
        return None
    p = (base / "/".join(rest)).resolve()
    return p if p.is_relative_to(base) and p.is_file() else None


def _send_course(p: Path) -> FileResponse:
    resp = FileResponse(p, headers={"Cache-Control": "no-cache"})
    if p.suffix in (".html", ".js", ".css", ".mjs", ".svg", ".json"):
        resp.media_type = resp.headers["content-type"] = f"{mimetypes.guess_type(p.name)[0]}; charset=utf-8"
    return resp


def _dist() -> Path:
    return Path(settings.frontend_dist).resolve()


def mount_frontend(app: FastAPI) -> None:
    if not (_dist() / "index.html").is_file():
        log.warning("FRONTEND_DIST %s 下没有 index.html：只提供 API，不托管前端", _dist())

    @app.api_route("/api/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"],
                   include_in_schema=False)
    async def api_not_found(path: str):
        return problem(404, "course_not_found", "接口不存在")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def frontend(path: str):
        dist = _dist()
        if settings.course_dir and path.startswith("course/"):
            if (p := _course_file(path)):
                return _send_course(p)
            return Response("Not Found", status_code=404, media_type="text/plain; charset=utf-8")
        if (p := _file(dist, path)):
            return _send(p, dist)
        if path.split("/", 1)[0] in NO_FALLBACK or not (dist / "index.html").is_file():
            return Response("Not Found", status_code=404, media_type="text/plain; charset=utf-8")
        return _send(dist / "index.html", dist)
