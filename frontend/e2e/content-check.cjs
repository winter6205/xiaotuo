// 阅读页地址批量检查：遍历前端生成的全部阅读页地址（各课章入口页、小节页、单页章 Boss 锚点）
// - 外层地址 /<课程>/<文件> 返回 200（SPA 回退）
// - 教材页 /course/<课程>/<文件> 及其加载的 /course/** 资源均 200，页面无 JS 报错
// - 旧锚点映射（课程目录 anchors：目录页#旧锚点 → 小页）目标页存在、锚点元素存在；单页章 Boss 锚点元素存在
// 课程列表由调用方传入（GET /api/courses 的 courses）。教材页 /course/** 由后端从课程目录提供，前端构建产物里没有课程。
// 用法：被 smoke.cjs 调用；也可单独运行 `npm run e2e:content`（先 npm run build）：默认由 e2e/backend.cjs 用 CLI 起临时后端
//   （--courses <COURSE_DIR，默认 examples>、SQLite 临时库，跑完按 PID 停止并删除临时目录），设置 XT_API 时复用已有后端；
//   XT_URL 未设时自起 vite preview（127.0.0.1:4174，/api、/course 代理到后端）

const enc = encodeURIComponent
async function checkContent({ browser, base, courses, log = console.log }) {
  if (!Array.isArray(courses)) throw new Error('checkContent 需要 courses（GET /api/courses 的课程列表）')
  const fails = []
  const fail = (m) => { fails.push(m); log('  ✗ ' + m) }
  // 前端生成的阅读页地址（与 lib/courses.ts readerPath / units / bossTarget 同口径）
  const routes = [] // { c, file, hash, why }
  for (const c of courses) for (const p of c.pages) {
    routes.push({ c: c.id, file: p.file, hash: '', why: `${p.id} 入口页` })
    for (const s of p.subs) routes.push({ c: c.id, file: s.file, hash: '', why: `小节 ${s.key}` })
    if (p.boss && !p.subs.some((s) => s.boss)) routes.push({ c: c.id, file: p.file, hash: 'boss', why: `${p.id} Boss 锚点` })
  }
  const anchors = [] // { c, from, hash, to }
  for (const c of courses) for (const [from, m] of Object.entries(c.anchors)) for (const [hash, to] of Object.entries(m)) anchors.push({ c: c.id, from, hash, to })
  const files = new Map() // `${c}/${file}` → { ids:Set }
  for (const r of routes) files.set(`${r.c}/${r.file}`, null)
  for (const a of anchors) { files.set(`${a.c}/${a.to}`, null); files.set(`${a.c}/${a.from}`, null) }

  // 1. 外层地址 200
  for (const r of routes) {
    const u = `${base}/${r.c}/${enc(r.file)}`
    const st = await fetch(u).then((x) => x.status, () => 0)
    if (st !== 200) fail(`外层地址 ${st}: /${r.c}/${r.file}（${r.why}）`)
  }
  // 2. 教材页及资源（浏览器加载，记录 /course/** 非 200 响应与 JS 报错，收集页面上的 id）
  const pg = await browser.newPage()
  let bad = []
  const onResp = (res) => { const u = res.url(); if (u.includes('/course/') && res.status() >= 400) bad.push(`${res.status()} ${decodeURIComponent(new URL(u).pathname)}`) }
  const onFailed = (req) => { const u = req.url(); if (u.includes('/course/')) bad.push(`ERR ${decodeURIComponent(new URL(u).pathname)} ${req.failure()?.errorText}`) }
  let errs = []
  pg.on('response', onResp); pg.on('requestfailed', onFailed); pg.on('pageerror', (e) => errs.push(e.message))
  for (const key of files.keys()) {
    const [c, ...rest] = key.split('/'); const file = rest.join('/')
    bad = []; errs = []
    const u = `${base}/course/${c}/${enc(file)}`
    const res = await pg.goto(u, { waitUntil: 'load' }).catch((e) => ({ status: () => 0, err: e.message }))
    const ct = res?.headers?.()['content-type'] || ''
    if (res?.status() !== 200 || !ct.includes('html')) { fail(`教材页 ${res?.status()} ${ct}: /course/${key}`); continue }
    await new Promise((r) => setTimeout(r, 150))
    const ids = await pg.evaluate(() => [...document.querySelectorAll('[id]')].map((e) => e.id))
    files.set(key, new Set(ids))
    for (const b of new Set(bad)) fail(`资源非 200（${key}）：${b}`)
    for (const e of errs) fail(`JS 报错（${key}）：${e}`)
  }
  await pg.close()
  // 3. Boss 锚点、旧锚点映射
  for (const r of routes.filter((x) => x.hash)) {
    const ids = files.get(`${r.c}/${r.file}`)
    if (ids && !ids.has(r.hash)) fail(`锚点元素不存在：/${r.c}/${r.file}#${r.hash}（${r.why}）`)
  }
  const known = new Set(routes.map((r) => `${r.c}/${r.file}`))
  for (const a of anchors) {
    if (!known.has(`${a.c}/${a.to}`)) fail(`旧锚点目标不在阅读页列表：/${a.c}/${a.from}#${a.hash} → ${a.to}`)
    const ids = files.get(`${a.c}/${a.to}`)
    if (ids && !ids.has(a.hash)) fail(`旧锚点目标页缺锚点元素：/${a.c}/${a.from}#${a.hash} → /${a.c}/${a.to}#${a.hash}`)
  }
  return { routes: routes.length, pages: files.size, anchors: anchors.length, fails }
}
module.exports = { checkContent }

if (require.main === module) (async () => {
  const { spawn } = require('node:child_process')
  const puppeteer = require('puppeteer-core')
  const { startBackend, fetchCatalog, stopProc } = require('./backend.cjs')
  const UI_PORT = 4174
  const base = process.env.XT_URL || `http://127.0.0.1:${UI_PORT}`
  let be, courses
  try { be = await startBackend(); courses = await fetchCatalog(be.api) } catch (e) { console.log('FAIL 后端 / 课程目录：' + e.message); await be?.stop(); process.exit(1) }
  const srv = process.env.XT_URL ? null : spawn('npx', ['vite', 'preview', '--host', '127.0.0.1', '--port', String(UI_PORT), '--strictPort'], { stdio: 'ignore', env: { ...process.env, XT_API: be.api }, detached: true })
  for (let i = 0; i < 50; i++) { try { await fetch(base); break } catch { await new Promise((r) => setTimeout(r, 200)) } }
  let r, browser
  try {
    browser = await puppeteer.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', args: ['--no-sandbox'] })
    r = await checkContent({ browser, base, courses })
  } catch (e) { r = { routes: 0, pages: 0, anchors: 0, fails: ['异常: ' + e.message] } } finally { await browser?.close(); stopProc(srv); await be.stop() }
  console.log(`${r.fails.length ? 'FAIL' : 'PASS'} 阅读页地址 ${r.routes} 个、教材页 ${r.pages} 个、旧锚点 ${r.anchors} 个${r.fails.length ? `，${r.fails.length} 处问题` : ''}`)
  process.exit(r.fails.length ? 1 : 0)
})()
