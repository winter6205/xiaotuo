#!/bin/sh
# Startup: generate scoring manifests and the course catalog from the course directory
# (COURSE_DIR: the bundled samples at /app/examples by default; compose mounts courses at
# /course) -> cross-check -> migrate -> serve. An empty course directory yields an empty
# catalog (GET /api/courses returns []). Any failure exits the container
# (see `docker compose logs app`). Restart the container after changing courses.
# DATABASE_URL is required: unset, the app falls back to the personal SQLite file from
# xiaotuo/config.py inside the container's writable layer -- data lost with the container,
# while /api/health/ready still answers db=ok. Refuse to start rather than serve that silently.
set -e
if [ -z "${DATABASE_URL:-}" ]; then
  echo "FATAL: DATABASE_URL is not set, so this image would use the ephemeral SQLite default" >&2
  echo "(<user data dir>/xiaotuo.db inside the container). Pass a real database URL, e.g." >&2
  echo "-e DATABASE_URL=postgresql://user:password@host:5432/db. docker-compose.yml sets it" >&2
  echo "for the bundled postgres service; see docs/deploy.md." >&2
  exit 1
fi
python scripts/build_content.py --allow-empty --src "$COURSE_DIR" --out "$CONTENT_DIR"
python scripts/check_content.py --allow-empty --src "$COURSE_DIR" --content "$CONTENT_DIR"
# Migrations ship inside the installed package (xiaotuo/migrations); no source tree needed
python -c "from xiaotuo.migrate import upgrade_head; upgrade_head()"
exec uvicorn xiaotuo.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-13773}" --proxy-headers --forwarded-allow-ips='*'
