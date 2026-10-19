#!/usr/bin/env bash
# 把私有仓库 HEAD 导出为开源仓库的一个快照提交。
#
# 用法：scripts/export-oss.sh <目标目录> <词表文件> [提交说明]
#   目标目录：开源仓库工作副本。不存在或为空时 git init（首次发布）；已是 git 仓库时在其上新增一个提交。
#   词表文件：私有词表（每行一个，按固定字符串、忽略大小写匹配），必须放在仓库之外，本脚本不含任何词条。
#             也可用环境变量 XT_SCAN_TERMS 指定。
#   提交说明：默认 "Initial open-source release"（首次）或 "Sync from upstream <短哈希>"。
# 环境变量：XT_OSS_AUTHOR_NAME / XT_OSS_AUTHOR_EMAIL 设置开源仓库的本地提交身份（默认沿用 git 配置）。
#
# 任一扫描命中即退出码 3，不修改目标目录、不提交。脚本不推送，推送由维护者手动执行。
set -euo pipefail

TARGET=${1:?用法：export-oss.sh <目标目录> <词表文件> [提交说明]}
TERMS=${2:-${XT_SCAN_TERMS:-}}
MSG=${3:-}
[ -n "$TERMS" ] && [ -s "$TERMS" ] || { echo "缺少词表文件" >&2; exit 2; }

SRC=$(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)
TERMS=$(realpath "$TERMS")
case "$TERMS" in "$SRC"/*) echo "词表文件不得位于仓库内：$TERMS" >&2; exit 2 ;; esac
mkdir -p "$TARGET"; TARGET=$(realpath "$TARGET")
case "$TARGET" in "$SRC"|"$SRC"/*) echo "目标目录不得位于私有仓库内" >&2; exit 2 ;; esac
[ -z "$(git -C "$SRC" status --porcelain)" ] || { echo "私有仓库有未提交改动，先提交再导出" >&2; exit 2; }
REV=$(git -C "$SRC" rev-parse --short HEAD)

STAGE=$(mktemp -d); trap 'rm -rf "$STAGE"' EXIT
git -C "$SRC" archive HEAD | tar -x -C "$STAGE"

# 导出时排除的路径（相对仓库根）
EXCLUDES=()
for p in "${EXCLUDES[@]}"; do rm -rf "${STAGE:?}/$p"; done

hits=0
scan() {  # $1 规则名，其余为 grep 参数；命中即计数并打印
  local name=$1; shift
  local out
  out=$(cd "$STAGE" && grep -rnI --exclude-dir=node_modules "$@" . || true)
  if [ -n "$out" ]; then echo "== 命中：$name"; echo "$out" | cut -c1-200; hits=$((hits + 1)); fi
}
scan "私有词表" -iF -f "$TERMS"

# 正则规则：跳过本脚本（含规则字面量）、锁文件与第三方词表；再滤掉已知的占位值
RX_EXCL=(--exclude=export-oss.sh --exclude=uv.lock --exclude=package-lock.json --exclude=common-passwords.txt)
ALLOW='noreply|example\.(com|org)|"a@b\.co"|u:p@ep-x|127\.0\.0\.1|0\.0\.0\.0|"1\.2\.3\.4"|172\.16\.0\.0/12|/mnt/c/\.\.\.'
scanrx() {
  local name=$1 rx=$2 out
  out=$(cd "$STAGE" && grep -rnIE "${RX_EXCL[@]}" "$rx" . | grep -viE "$ALLOW" || true)
  if [ -n "$out" ]; then echo "== 命中：$name"; echo "$out" | cut -c1-200; hits=$((hits + 1)); fi
}
scanrx "邮箱" '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}'
scanrx "个人路径" '/home/[A-Za-z0-9_.-]+|/Users/[A-Za-z0-9_.-]+|/mnt/[a-z]/|[A-Za-z]:\\+Users'
scanrx "IP 地址" '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b'
scanrx "私钥" 'BEGIN [A-Z ]*PRIVATE KEY'

if [ "$hits" -gt 0 ]; then echo "扫描命中 $hits 类，未提交。" >&2; exit 3; fi
echo "扫描通过：0 命中"

if [ -d "$TARGET/.git" ]; then
  [ -z "$(git -C "$TARGET" status --porcelain)" ] || { echo "目标仓库有未提交改动" >&2; exit 2; }
  FIRST=0
else
  [ -z "$(ls -A "$TARGET")" ] || { echo "目标目录非空且不是 git 仓库" >&2; exit 2; }
  git -C "$TARGET" init -q -b main
  FIRST=1
fi
[ -n "${XT_OSS_AUTHOR_NAME:-}" ] && git -C "$TARGET" config user.name "$XT_OSS_AUTHOR_NAME"
[ -n "${XT_OSS_AUTHOR_EMAIL:-}" ] && git -C "$TARGET" config user.email "$XT_OSS_AUTHOR_EMAIL"

# 用快照替换目标工作树（保留 .git）
find "$TARGET" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
(cd "$STAGE" && tar -cf - .) | tar -xf - -C "$TARGET"
git -C "$TARGET" add -A
if git -C "$TARGET" diff --cached --quiet && [ "$FIRST" = 0 ]; then echo "与上次导出相同，无需提交"; exit 0; fi
if [ -z "$MSG" ]; then
  if [ "$FIRST" = 1 ]; then MSG="Initial open-source release"; else MSG="Sync from upstream $REV"; fi
fi
git -C "$TARGET" commit -q -m "$MSG"
git -C "$TARGET" log --oneline -1
echo "已提交，未推送。推送：cd $TARGET && git push -u origin main"
