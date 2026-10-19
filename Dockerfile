# syntax=docker/dockerfile:1.7
# Xiaotuo local Docker image. See docs/local-run.md.
# The image ships only the repository's sample courses (/app/examples, the default
# COURSE_DIR); the build reads no external course directory. At startup the
# entrypoint generates the scoring manifests and the course catalog
# (GET /api/courses) from COURSE_DIR, and /course/** is served from that directory.
# To use your own courses, mount them read-only at /course and set COURSE_DIR=/course
# (docker-compose.yml does this).
# The backend is installed into the venv as a package (non-editable); the image
# keeps no backend source tree.
# Build: docker compose build. Version: --build-arg XT_VERSION=<tag or short sha>
# (there is no .git in the image; default 0.0.0+docker).

FROM node:22-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build && test -f dist/index.html

FROM python:3.12-slim AS backend
# uv matches the version that wrote backend/uv.lock; pinned by image digest
COPY --from=ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/README.pypi.md backend/LICENSE ./
COPY backend/xiaotuo/ xiaotuo/
ARG XT_VERSION=0.0.0+docker
RUN SETUPTOOLS_SCM_PRETEND_VERSION="$XT_VERSION" uv sync --frozen --no-dev --no-editable \
 && .venv/bin/python -c "import importlib.metadata as m; print('xiaotuo', m.version('xiaotuo'))"

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PATH=/app/backend/.venv/bin:$PATH
WORKDIR /app/backend
# Same venv path as in the backend stage (/app/backend/.venv) so script shebangs stay valid
COPY --from=backend /app/backend/.venv/ .venv/
COPY backend/scripts/ scripts/
COPY examples/ /app/examples/
COPY --from=frontend /src/frontend/dist/ /app/frontend/dist/
COPY docker/entrypoint.sh /usr/local/bin/xt-entrypoint
RUN chmod 755 /usr/local/bin/xt-entrypoint \
 && useradd --system --uid 10001 --no-create-home xiaotuo \
 && mkdir -p content && chown xiaotuo content
USER xiaotuo
ENV XT_ENV_FILE= CONTENT_DIR=content FRONTEND_DIST=/app/frontend/dist COURSE_DIR=/app/examples \
    HOST=0.0.0.0 PORT=13773
EXPOSE 13773
ENTRYPOINT ["xt-entrypoint"]
