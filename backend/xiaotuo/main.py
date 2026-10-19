import asyncio

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException

from xiaotuo import db
from xiaotuo.config import settings
from xiaotuo.content import courses
from xiaotuo.errors import ApiError, api_error_handler, http_error_handler, validation_handler
from xiaotuo.routers import auth, courses as courses_router, dashboard, progress
from xiaotuo.static import mount_frontend

app = FastAPI(title="小驼学习 API", version=settings.app_version)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_handler)
app.add_exception_handler(HTTPException, http_error_handler)
app.include_router(auth.router)
app.include_router(progress.router)
app.include_router(dashboard.router)
app.include_router(courses_router.router)

DB_CHECK_TIMEOUT_S = 2.0


async def _db_ok() -> bool:
    try:
        async with asyncio.timeout(DB_CHECK_TIMEOUT_S):
            async with db.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _content_versions() -> dict[str, str]:
    try:
        return {code: c.content_version for code, c in courses().items()}
    except (OSError, ValueError, KeyError):
        return {}


@app.get("/api/health")
async def health():
    """进程存活检查，不访问数据库；Render healthCheckPath 使用。"""
    return {"status": "ok"}


@app.get("/api/health/ready")
async def ready():
    """就绪检查：SELECT 1，超时 2 秒；监控与发布后冒烟测试使用。"""
    ok = await _db_ok()
    body = {"status": "ok" if ok else "degraded", "db": "ok" if ok else "unavailable",
            "version": settings.app_version, "content_version": _content_versions(),
            "email_enabled": settings.email_enabled}
    return JSONResponse(status_code=200 if ok else 503, content=body)


mount_frontend(app)  # 必须最后注册：catch-all 路由
