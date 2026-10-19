# syntax=docker/dockerfile:1.7
# 小驼本地 Docker 镜像。说明见 docs/local-run.md
# 课程内容不进镜像：构建期仅经命名上下文 course 读取课程目录生成前端目录数据，
# 运行时 /course/** 由只读挂载的课程目录提供（COURSE_DIR）；计分清单在容器启动时生成（docker/entrypoint.sh）。
# 构建：docker compose build（compose 提供 course 上下文）

FROM node:22-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV COURSE_DIR=/course
RUN --mount=type=bind,from=course,target=/course,ro npm run build \
 && rm -rf dist/course

FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 PATH=/app/backend/.venv/bin:$PATH
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/alembic.ini ./
COPY backend/app/ app/
COPY backend/migrations/ migrations/
COPY backend/scripts/ scripts/
COPY --from=frontend /src/frontend/dist/ /app/frontend/dist/
COPY docker/entrypoint.sh /usr/local/bin/xt-entrypoint
RUN chmod 755 /usr/local/bin/xt-entrypoint \
 && useradd --system --uid 10001 --no-create-home xiaotuo \
 && mkdir -p content && chown xiaotuo content
USER xiaotuo
ENV XT_ENV_FILE= CONTENT_DIR=content FRONTEND_DIST=/app/frontend/dist COURSE_DIR=/course \
    HOST=0.0.0.0 PORT=13773
EXPOSE 13773
ENTRYPOINT ["xt-entrypoint"]
