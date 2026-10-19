#!/usr/bin/env bash
# 小驼本地启停：xiaotuo start|stop|restart|status|logs
set -e
cd "$(dirname "$(readlink -f "$0")")/.."
PORT="$(grep -E '^XT_PORT=' .env 2>/dev/null | cut -d= -f2)"; PORT="${PORT:-13773}"
URL="http://localhost:${PORT}"
case "$1" in
  start)
    docker compose up -d
    echo "小驼已启动：${URL}"
    command -v cmd.exe >/dev/null && cmd.exe /c start "${URL}" >/dev/null 2>&1 || true ;;
  stop)    docker compose down ;;   # 不带 -v，保留学习数据
  restart) docker compose restart ;;
  status)  docker compose ps ;;
  logs)    docker compose logs -f --tail=100 app ;;
  *) echo "用法：xiaotuo start|stop|restart|status|logs"; exit 1 ;;
esac
