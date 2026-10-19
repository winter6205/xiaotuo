#!/usr/bin/env bash
# 小驼本地一键运行（WSL / Linux，不使用 Docker）。说明见 docs/local-run.md 附录 B
# 用法：scripts/run-local.sh [--skip-build] [--port N]
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
port="${XT_PORT:-13773}"
skip_build=0
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-build) skip_build=1 ;;
    --port) port="$2"; shift ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
  shift
done

die() { echo "错误：$*" >&2; exit 1; }

for cmd in uv node npm; do
  command -v "$cmd" >/dev/null 2>&1 || die "缺少依赖：$cmd。请按 docs/local-run.md 附录 B.1 节安装后重开终端。"
done
case "$(command -v node)" in
  /mnt/*) die "当前 node 来自 Windows（$(command -v node)），请在 WSL 内安装 Node（见附录 B.1 节）。" ;;
esac
node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>22||(a===22&&b>=12)?0:1)' \
  || die "Node 版本为 $(node -v)，需要 22.12 及以上。"
[ -f "$root/backend/.env" ] || die "缺少 backend/.env。请复制 backend/.env.example 并按 docs/local-run.md 附录 B.4 节修改。"

if command -v pg_isready >/dev/null 2>&1 && ! pg_isready -q -h localhost; then
  die "PostgreSQL 未运行：执行 sudo service postgresql start 后重试。"
fi

# 课程根目录：COURSE_DIR（相对路径按仓库根解析），默认 ../course-content
course_dir="${COURSE_DIR:-../course-content}"
case "$course_dir" in /*) ;; *) course_dir="$root/$course_dir" ;; esac
[ -d "$course_dir" ] || die "课程根目录不存在：$course_dir。设置 COURSE_DIR 指向课程根目录（其下每个含 course.json 的子目录为一门课程）。"
course_dir="$(cd "$course_dir" && pwd)"

cd "$root/backend"
uv sync || die "uv sync 失败"
uv run python scripts/build_content.py --src "$course_dir" --out content \
  || die "生成计分清单失败（课程根目录：$course_dir）：按上方列出的问题修正 course.json 或页面"
uv run python scripts/check_content.py --src "$course_dir" --content content \
  || die "内容校验失败（课程根目录：$course_dir）：页面与计分清单不一致，见上方输出"
uv run alembic upgrade head \
  || die "数据库迁移失败：检查 PostgreSQL 是否运行及 .env 中的 DATABASE_URL，排查见 docs/local-run.md 附录 B.6 节"

if [ "$skip_build" -eq 0 ]; then
  cd "$root/frontend"
  npm ci || die "npm ci 失败"
  COURSE_DIR="$course_dir" npm run build || die "前端构建失败：检查课程根目录（$course_dir）"
fi

echo "启动中：http://localhost:$port （Ctrl+C 停止）"
cd "$root/backend"
PORT="$port" exec uv run python -m app
