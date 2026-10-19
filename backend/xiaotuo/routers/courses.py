"""GET /api/courses：前端课程目录（运行时由内容生成步骤写出的 catalog.json，进程内缓存）。

无需登录；Cache-Control: no-cache + ETag（catalog 的 version），If-None-Match 命中返回 304。
响应体是 xiaotuo.content_build 写出的 catalog.json 原样内容，不经模型重新序列化；
下面的 Pydantic 模型只用于 OpenAPI 文档与前端 gen:api。
"""
import logging
from typing import Literal

from fastapi import APIRouter, Header, Response
from pydantic import BaseModel, ConfigDict, Field

from xiaotuo.content import catalog
from xiaotuo.errors import catalog_unavailable

router = APIRouter(prefix="/api", tags=["courses"])
log = logging.getLogger(__name__)


class Sub(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    file: str
    title: str
    ids: list[str]
    boss: str | None


class Page(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    file: str
    title: str
    xp: int
    sections: list[str]
    boss: str | None
    ids: list[str] = Field(description="计分项（max_xp > 0），已与后端计分清单对照")
    subs: list[Sub]


class CourseMeta(BaseModel):
    """一门课的元数据：由 xiaotuo.content_build 从课程清单 course.json 与页面生成，已与计分清单做 id 对照。"""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,15}$")
    dir: str = Field(description="课程根目录下的子目录名（只做展示和调试）")
    key: str = Field(description="localStorage 键：storage_key，缺省为 <id>-v<state_version>")
    title: str
    name: str
    short: str
    icon: str
    order: float
    accent: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accentLight: str | None
    accentDark: str | None
    stateVersion: Literal[1, 2]
    courseId: str | None
    engine: Literal["course-manifest-js", "static"]
    homeChapter: str | None
    graduation: list[str] | None
    generated: str | None = None
    total: int
    anchors: dict[str, dict[str, str]]
    pages: list[Page]


class CatalogResponse(BaseModel):
    version: str = Field(description="目录版本（catalog 内容的 sha256 前 12 位），同时作为 ETag")
    courses: list[CourseMeta] = Field(description="按 order、id 排序；没有课程时为空数组")


class Problem(BaseModel):
    code: str
    message: str


@router.get("/courses", response_model=CatalogResponse, operation_id="getCourses", summary="课程目录",
            responses={304: {"description": "If-None-Match 命中，目录未变"},
                       503: {"model": Problem, "description": "课程目录不可用（code=catalog_unavailable）",
                             "content": {"application/problem+json": {}}}})
async def get_courses(if_none_match: str | None = Header(default=None)):
    try:
        cat = catalog()
    except (OSError, ValueError) as e:
        log.warning("课程目录不可用：%s", e)
        raise catalog_unavailable()
    tag = f'"{cat.version}"'
    headers = {"ETag": tag, "Cache-Control": "no-cache"}
    if if_none_match and (if_none_match.strip() == "*" or tag in [t.strip().removeprefix("W/") for t in if_none_match.split(",")]):
        return Response(status_code=304, headers=headers)
    return Response(content=cat.body, media_type="application/json", headers=headers)
