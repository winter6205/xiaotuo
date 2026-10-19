from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

PROBLEM = "application/problem+json"


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None,
                 headers: dict | None = None):
        self.status, self.code, self.message, self.details, self.headers = status, code, message, details, headers


def problem(status: int, code: str, message: str, details: dict | None = None, headers: dict | None = None):
    body = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(body, status_code=status, media_type=PROBLEM, headers=headers)


async def api_error_handler(_: Request, exc: ApiError):
    return problem(exc.status, exc.code, exc.message, exc.details, exc.headers)


async def validation_handler(_: Request, exc: RequestValidationError):
    fields = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()]
    return problem(400, "validation_error", "请求字段不合法", {"fields": fields})


async def http_error_handler(_: Request, exc):
    # 未匹配路由等框架级错误，也统一为 problem+json
    if exc.status_code == 404:
        return problem(404, "course_not_found", "没有这门课")
    if exc.status_code >= 500:
        return problem(exc.status_code, "internal_error", "服务器出错了，请稍后再试")
    return problem(exc.status_code, "validation_error", str(exc.detail))


def unauthorized():
    return ApiError(401, "not_authenticated", "登录已过期，请重新登录")


def course_not_found():
    return ApiError(404, "course_not_found", "没有这门课")


def catalog_unavailable():
    return ApiError(503, "catalog_unavailable", "课程目录暂不可用：课程清单校验失败或尚未生成")
