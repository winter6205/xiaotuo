# 小驼本地一键运行（Windows，不使用 Docker）。说明见 docs/local-run.md
param(
  [switch]$SkipBuild,
  [int]$Port = $(if ($env:XT_PORT) { [int]$env:XT_PORT } else { 13773 })
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

foreach ($cmd in 'uv', 'node', 'npm') {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    throw "缺少依赖：$cmd。请按 docs/local-run.md 附录 B.1 节安装后重新打开 PowerShell。"
  }
}
$nodeVer = [version]((node -v).TrimStart('v'))
if ($nodeVer -lt [version]'22.12.0') { throw "Node 版本为 $nodeVer，需要 22.12 及以上。" }
if (-not (Test-Path "$root\backend\.env")) {
  throw "缺少 backend\.env。请复制 backend\.env.example 并按 docs/local-run.md 附录 B.4 节修改。"
}

# 课程根目录：COURSE_DIR（相对路径按仓库根解析），默认 ..\course-content
$courseDir = if ($env:COURSE_DIR) { $env:COURSE_DIR } else { '..\course-content' }
if (-not [System.IO.Path]::IsPathRooted($courseDir)) { $courseDir = Join-Path $root $courseDir }
if (-not (Test-Path $courseDir -PathType Container)) {
  throw "课程根目录不存在：$courseDir。设置 COURSE_DIR 指向课程根目录（其下每个含 course.json 的子目录为一门课程）。"
}
$courseDir = (Resolve-Path $courseDir).Path

Push-Location "$root\backend"
try {
  uv sync
  if ($LASTEXITCODE) { throw 'uv sync 失败' }
  uv run python scripts/build_content.py --src "$courseDir" --out content
  if ($LASTEXITCODE) { throw "生成计分清单失败（课程根目录：$courseDir）：按上方列出的问题修正 course.json 或页面" }
  uv run python scripts/check_content.py --src "$courseDir" --content content
  if ($LASTEXITCODE) { throw "内容校验失败（课程根目录：$courseDir）：页面与计分清单不一致，见上方输出" }
  uv run alembic upgrade head
  if ($LASTEXITCODE) { throw '数据库迁移失败：确认 WSL 中 PostgreSQL 已启动（sudo service postgresql start），并检查 .env 中的 DATABASE_URL，排查见 docs/local-run.md 附录 B.6 节' }
} finally { Pop-Location }

if (-not $SkipBuild) {
  Push-Location "$root\frontend"
  try {
    npm ci
    if ($LASTEXITCODE) { throw 'npm ci 失败' }
    $prevCourseDir = $env:COURSE_DIR
    $env:COURSE_DIR = $courseDir
    npm run build
    $buildExit = $LASTEXITCODE
    $env:COURSE_DIR = $prevCourseDir
    if ($buildExit) { throw "前端构建失败：检查课程根目录（$courseDir）" }
  } finally { Pop-Location }
}

Write-Host "启动中：http://localhost:$Port （Ctrl+C 停止）"
Set-Location "$root\backend"
$env:PORT = "$Port"
uv run python -m app
