#!/usr/bin/env bash
# 冒烟：启动 `xiaotuo start`（或任意等价命令），等 XIAOTUO_READY 行，检查健康、课程目录（及可选的前端首页），再按 PID 停止。
# 用法：scripts/cli_smoke.sh [--expect-index] [--expect-courses N] -- <启动命令...>
# 例：  scripts/cli_smoke.sh -- uv run python -m xiaotuo.cli start --no-browser --port 0
# 个人数据目录默认指向临时目录（XIAOTUO_DATA_DIR），不碰本机真实数据。
set -euo pipefail
expect_index=0
expect_courses=1
while [ $# -gt 0 ]; do
  case "$1" in
    --expect-index) expect_index=1; shift ;;
    --expect-courses) expect_courses="$2"; shift 2 ;;
    --) shift; break ;;
    *) echo "未知参数：$1" >&2; exit 64 ;;
  esac
done
[ $# -gt 0 ] || { echo "缺少启动命令" >&2; exit 64; }

tmp="$(mktemp -d)"
export XIAOTUO_DATA_DIR="${XIAOTUO_DATA_DIR:-$tmp/data}"
log="$tmp/server.log"
"$@" >"$log" 2>&1 &
pid=$!
stop_rc=""
# 正常停止：SIGINT 让 uvicorn 收尾，10 秒不收尾再强杀；退出码记进 stop_rc，由调用方判断。
# 只 kill 不查退出码会漏掉“正常停止却返回非 0”的回归：SKILL.md 第 4 步以退出码全部为 0 为完成标准。
stop_server() {
  if kill -0 "$pid" 2>/dev/null; then
    kill -INT "$pid" 2>/dev/null || true
    for _ in $(seq 1 50); do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
    kill -9 "$pid" 2>/dev/null || true
  fi
  stop_rc=0
  wait "$pid" 2>/dev/null || stop_rc=$?
}
cleanup() {
  [ -n "$stop_rc" ] || stop_server   # 失败路径也要把服务停掉，不留后台进程
  rm -rf "$tmp"
}
trap cleanup EXIT

url=""
for _ in $(seq 1 300); do
  url="$(sed -n 's/^XIAOTUO_READY \(http[^ ]*\)$/\1/p' "$log" | head -n1)"
  [ -n "$url" ] && break
  kill -0 "$pid" 2>/dev/null || { echo "进程提前退出：" >&2; cat "$log" >&2; exit 1; }
  sleep 0.2
done
[ -n "$url" ] || { echo "60 秒内未就绪：" >&2; cat "$log" >&2; exit 1; }
echo "就绪：$url"

code() { curl -s -o "$tmp/body" -w '%{http_code}' "$1"; }
fail() { echo "失败：$*" >&2; echo "--- 服务日志 ---" >&2; cat "$log" >&2; exit 1; }

[ "$(code "${url}api/health/ready")" = 200 ] || fail "/api/health/ready $(cat "$tmp/body")"
echo "health/ready: $(cat "$tmp/body")"
[ "$(code "${url}api/courses")" = 200 ] || fail "/api/courses $(cat "$tmp/body")"
n="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["courses"]))' "$tmp/body")"
echo "api/courses: 200, ${n} 门课"
[ "$n" = "$expect_courses" ] || fail "课程数 $n，期望 $expect_courses"
etag="$(curl -s -o /dev/null -D - "${url}api/courses" | tr -d '\r' | sed -n 's/^[Ee][Tt][Aa][Gg]: //p')"
[ "$(curl -s -o /dev/null -w '%{http_code}' -H "If-None-Match: $etag" "${url}api/courses")" = 304 ] || fail "ETag 304"
echo "api/courses ETag $etag → 304"
if [ "$expect_index" = 1 ]; then
  [ "$(code "$url")" = 200 ] && grep -qi '<!doctype html' "$tmp/body" || fail "前端首页"
  echo "index: 200 html"
fi
stop_server
[ "$stop_rc" = 0 ] || fail "正常停止 exit=$stop_rc（期望 exit=0）"
echo "stop: exit=0"
echo "OK"
