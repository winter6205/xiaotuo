// e2e 共用：用 CLI 起一个临时后端（SQLite），读取运行时课程目录（GET /api/courses），结束后按进程组 PID 停止并删除临时目录。
// 自起（默认）：在 backend/ 下执行
//   uv run --frozen python -m xiaotuo.cli start --courses <repo>/examples --cache-dir <tmp>/content
//     --host 127.0.0.1 --port <空闲端口或 XT_PORT> --no-browser
//   环境：DATABASE_URL=sqlite:///<tmp>/e2e.db、XIAOTUO_DATA_DIR=<tmp>/data、RATELIMIT_MULTIPLIER=20
//   （CLI 负责生成内容缓存、迁移数据库，并对 127.0.0.1 设 COOKIE_SECURE=false）。就绪判断：/api/courses 返回 200。
// 复用：设置 XT_API 指向已在运行的后端时不自起；此时计分清单目录取 CONTENT_DIR（smoke 读 items-<id>.json）。
// 课程目录：COURSE_DIR（相对仓库根，默认 examples）。教材页 /course/** 由后端从该目录直接提供，前端构建产物里没有课程。
const { spawn } = require('node:child_process')
const fs = require('node:fs')
const net = require('node:net')
const os = require('node:os')
const path = require('node:path')

const REPO = path.resolve(__dirname, '../..')
const BACKEND = path.resolve(REPO, 'backend')
const OUT = path.resolve(__dirname, 'out')
const COURSE_DIR = path.resolve(REPO, process.env.COURSE_DIR || 'examples')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const up = (u) => fetch(u).then((r) => r.ok, () => false)

const freePort = () => new Promise((resolve, reject) => {
  const s = net.createServer().once('error', reject).listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => resolve(port)) })
})

/** 起后端（或复用 XT_API）。返回 { api, contentDir, stop }；stop() 按进程组 PID 结束后端并删除临时目录（可重复调用） */
async function startBackend({ log = console.log } = {}) {
  if (process.env.XT_API) {
    const api = process.env.XT_API.replace(/\/$/, '')
    return { api, contentDir: path.resolve(process.env.CONTENT_DIR || path.join(OUT, 'content')), tmp: null, pid: null, stop: async () => {} }
  }
  const port = Number(process.env.XT_PORT) || (await freePort())
  const api = `http://127.0.0.1:${port}`
  if (await up(api + '/api/health')) throw new Error(`${api} 已被占用：停止该进程，或用 XT_API 显式复用已有后端`)
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'xt-e2e-'))
  const contentDir = path.join(tmp, 'content')
  const dataDir = path.join(tmp, 'data')
  fs.mkdirSync(dataDir)
  const logFile = path.join(tmp, 'server.log')
  const fd = fs.openSync(logFile, 'w')
  const env = { ...process.env, DATABASE_URL: `sqlite:///${path.join(tmp, 'e2e.db')}`, XIAOTUO_DATA_DIR: dataDir, RATELIMIT_MULTIPLIER: '20' }
  delete env.CONTENT_DIR; delete env.COURSE_DIR; delete env.XT_FRONTEND_DIST // 由 CLI 参数决定
  const args = ['run', '--frozen', 'python', '-m', 'xiaotuo.cli', 'start', '--courses', COURSE_DIR, '--cache-dir', contentDir,
    '--host', '127.0.0.1', '--port', String(port), '--no-browser']
  const proc = spawn('uv', args, { cwd: BACKEND, env, stdio: ['ignore', fd, fd], detached: true })
  fs.closeSync(fd)
  let exited = null
  proc.on('exit', (code, sig) => { exited = { code, sig } })

  let stopped = false
  const stop = async () => {
    if (stopped) return
    stopped = true
    if (exited == null) {
      try { process.kill(-proc.pid, 'SIGINT') } catch { /* 已退出 */ }
      for (let i = 0; i < 50 && exited == null; i++) await sleep(100)
      if (exited == null) try { process.kill(-proc.pid, 'SIGKILL') } catch { /* 已退出 */ }
      for (let i = 0; i < 20 && exited == null; i++) await sleep(100)
    }
    fs.rmSync(tmp, { recursive: true, force: true })
  }
  // Ctrl-C 等中断时也清理（同步尽力而为）
  const onSig = () => { try { process.kill(-proc.pid, 'SIGKILL') } catch { /* 已退出 */ } fs.rmSync(tmp, { recursive: true, force: true }); process.exit(130) }
  process.once('SIGINT', onSig); process.once('SIGTERM', onSig)

  for (let i = 0; i < 600; i++) { // 最长 120 秒（首次 uv run 可能要准备环境）
    if (exited) break
    const st = await fetch(api + '/api/courses').then((r) => r.status, () => 0)
    if (st === 200) { log(`  后端就绪：${api}（pid ${proc.pid}，SQLite，临时目录 ${tmp}）`); return { api, contentDir, tmp, pid: proc.pid, stop } }
    await sleep(200)
  }
  const out = fs.existsSync(logFile) ? fs.readFileSync(logFile, 'utf8') : ''
  await stop()
  throw new Error(`后端未就绪（${exited ? `进程退出 ${exited.code ?? exited.sig}` : '超时'}）：\n${out.slice(-4000)}`)
}

/** 运行时课程目录：GET ${api}/api/courses → courses（按 order、id 排序，与前端 lib/courses.ts 同口径） */
async function fetchCatalog(api) {
  const res = await fetch(api + '/api/courses').catch((e) => { throw new Error(`无法访问 ${api}/api/courses：${e.message}`) })
  if (!res.ok) throw new Error(`${api}/api/courses 返回 ${res.status}（后端未提供课程目录接口，或课程目录校验失败）`)
  const body = await res.json()
  if (!Array.isArray(body?.courses)) throw new Error(`${api}/api/courses 响应缺少 courses 数组`)
  if (!body.courses.length) throw new Error(`${api}/api/courses 为空：后端须以 --courses ${COURSE_DIR} 启动`)
  return body.courses.slice().sort((a, b) => a.order - b.order || a.id.localeCompare(b.id))
}

/** 按进程组 PID 结束子进程（vite preview 等；避免 npx 的子进程残留占用端口） */
const stopProc = (...procs) => { for (const c of procs) if (c) try { process.kill(-c.pid) } catch { /* 已退出 */ } }

module.exports = { REPO, BACKEND, OUT, COURSE_DIR, sleep, up, startBackend, fetchCatalog, stopProc }
