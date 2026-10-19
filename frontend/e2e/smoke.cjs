// 冒烟：未登录跳转、注册/字段错误态、首次导入、嵌入样式、做题→事件同步、快照回写、退出确认、手机抽屉
// 内容：示例课程（COURSE_DIR=examples，课程 id demo，engine static）。课程元数据一律从后端 GET /api/courses 读取，不写死
// 后端：默认由 e2e/backend.cjs 用 CLI 起临时后端（xiaotuo.cli start --courses <COURSE_DIR> --cache-dir <临时目录>，
//   SQLite 临时库、XIAOTUO_DATA_DIR 临时目录、127.0.0.1 空闲端口或 XT_PORT），跑完按进程组 PID 停止并删除临时目录；
//   设置 XT_API 时复用已有后端（计分清单目录取 CONTENT_DIR）。前端：XT_URL 未设时自起 vite preview（127.0.0.1:4173，/api、/course 代理到后端）
// 截图写到 e2e/out/（已忽略）
const { spawn } = require('node:child_process')
const path = require('node:path')
const puppeteer = require('puppeteer-core')
const fs = require('node:fs')
const { OUT, COURSE_DIR, up, startBackend, fetchCatalog, stopProc } = require('./backend.cjs')
const UI_PORT = 4173
const BASE = process.env.XT_URL || `http://127.0.0.1:${UI_PORT}`
// 后端地址、计分清单目录与课程目录在后端起来后确定（loadCatalog() 从 /api/courses 取得课程）
let API, CONTENT_DIR
let COURSES, C, ALL, P0, P1, ID, KEY
const ITEMS = (c) => Object.fromEntries(JSON.parse(fs.readFileSync(path.join(CONTENT_DIR, `items-${c}.json`), 'utf8')).map((x) => [x.id, x]))
async function loadCatalog() {
  COURSES = await fetchCatalog(API)
  C = COURSES.find((c) => c.engine === 'static' && c.pages.some((p) => p.boss)) || COURSES[0] // 示例课程
  // 示例课程 item（按规范第 6 节约定的类型从目录中挑选，不写死 id）
  ALL = C.pages.flatMap((p) => p.ids)
  P0 = C.pages[0]; P1 = C.pages.find((p) => p.boss) || C.pages.at(-1)
  ID = {
    quiz: ALL.find((id) => /-quiz-/.test(id)),
    read0: P0.ids.find((id) => id.endsWith('-done-read')),
    read1: P1.ids.find((id) => id.endsWith('-done-read')),
    boss: ALL.filter((id) => P1.boss && id.startsWith(P1.boss + '-')),
  }
  ID.q = ID.boss // 队列 / 换账号场景用的计分项（Boss 关卡项）
  KEY = C.key
}
const { checkContent } = require('./content-check.cjs')

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const blank = (course) => ({ version: C.stateVersion, ...(C.stateVersion === 1 ? { course } : {}), xp: {}, done: {}, rec: {}, solved: {}, fix: {}, streak: { cur: 0, best: 0, last: null }, days: {}, badges: {}, quiet: false, data: {}, sections: {} })

;(async () => {
  let be
  try { be = await startBackend(); API = be.api; CONTENT_DIR = be.contentDir; await loadCatalog() } catch (e) { console.log('FAIL 后端 / 课程目录：' + e.message); await be?.stop(); process.exit(1) }
  // 未指定 XT_URL 时自行起 vite preview（/api、/course 代理到 API）
  const srv = process.env.XT_URL ? null : spawn('npx', ['vite', 'preview', '--host', '127.0.0.1', '--port', String(UI_PORT), '--strictPort'], { stdio: 'ignore', env: { ...process.env, XT_API: API }, detached: true })
  for (let i = 0; i < 50; i++) { try { await fetch(BASE); break } catch { await sleep(200) } }
  const b = await puppeteer.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', args: ['--no-sandbox'] })
    .catch(async (e) => { console.log('FAIL 浏览器启动：' + e.message); stopProc(srv); await be.stop(); process.exit(1) })
  const p = await b.newPage()
  await p.setViewport({ width: 1280, height: 800 })
  const fails = []
  const check = (ok, msg) => { console.log((ok ? 'PASS ' : 'FAIL ') + msg); if (!ok) fails.push(msg) }
  const api = (path) => p.evaluate((u) => fetch(u, { credentials: 'include' }).then((r) => r.json()), BASE + '/api' + path)
  const frame = async () => (await p.$('iframe.xt-frame')).contentFrame()
  const visible = async () => { await p.waitForFunction(() => document.querySelector('iframe.xt-frame')?.style.visibility === 'visible', { timeout: 15000 }); return frame() }
  const submit = async (fields) => {
    for (const [id, v] of Object.entries(fields)) { await p.$eval('#' + id, (e) => { e.value = '' }); await p.type('#' + id, v) }
    await p.click('button[type=submit]')
  }
  // 对话框焦点陷阱：Tab/Shift+Tab 各按 n 次，焦点始终在对话框内
  const trapped = async (sel, n = 6) => {
    for (const k of ['Tab', 'Shift']) for (let i = 0; i < n; i++) {
      if (k === 'Tab') await p.keyboard.press('Tab')
      else { await p.keyboard.down('Shift'); await p.keyboard.press('Tab'); await p.keyboard.up('Shift') }
      if (!(await p.evaluate((s) => !!document.activeElement?.closest(s), sel))) return false
    }
    return true
  }
  // 连续观察 n 帧的焦点元素（id / 标签），用于确认导航完成后焦点稳定且不在 body
  const watchFocus = (n = 15) => p.evaluate((n) => new Promise((res) => {
    const out = []; const tick = () => { const a = document.activeElement; out.push(a === document.body ? 'BODY' : a.id || a.tagName); out.length < n ? requestAnimationFrame(tick) : res(out) }; requestAnimationFrame(tick)
  }), n)
  const errOf = (id) => p.$eval(`#${id}-e`, (e) => e.textContent).catch(() => '')

  try {
    if (!(await up(API + '/api/health'))) throw new Error(`后端不可达：${API}（见 README「本地联调」）`)
    // 1. 未登录访问受保护页 → 登录页
    await p.goto(BASE + '/dashboard', { waitUntil: 'networkidle0' })
    check(new URL(p.url()).pathname === '/login', '未登录跳转登录页: ' + p.url())
    const me = await api('/me')
    check(!!(await p.$('a[href="/reset"]')) === me.features.password_reset, `「忘记密码」入口随 features.password_reset=${me.features.password_reset}`)
    check(!(await p.evaluate(() => [...document.querySelectorAll('.xt-notice')].some((e) => e.textContent.includes('本机已有未登录时的学习进度')))), '无匿名进度时登录页不显示并入提示')

    fs.mkdirSync(OUT, { recursive: true })
    // 2. 未登录时本机已有进度（00 页读完打卡），供首次登录导入
    await p.evaluate((k, s) => localStorage.setItem(k, JSON.stringify(s)), KEY, { ...blank(C.courseId ?? C.id), xp: { [ID.read0]: 10 }, done: { [ID.read0]: 1 }, days: { '2026-10-18': 1 } })
    await p.goto(BASE + '/login', { waitUntil: 'networkidle0' })
    check(await p.evaluate(() => [...document.querySelectorAll('.xt-notice')].some((e) => e.textContent.includes('本机已有未登录时的学习进度'))), '有匿名进度时登录页显示并入提示')

    // 3. 注册错误态
    const email = `e2e-${Date.now()}@example.com`
    await p.goto(BASE + '/register', { waitUntil: 'networkidle0' })
    await p.click('button[type=submit]')
    check((await errOf('em')).includes('请输入邮箱'), '注册空提交时邮箱字段提示')
    await submit({ em: email, pw: 'abc12345', pw2: 'abc12345' })
    check((await errOf('pw')).includes('至少 10 位'), '密码过短提示')
    check(!!(await p.$('#pw-h')), '密码报错时保留密码规则提示')
    const short = await p.evaluate(async (u) => {
      const { csrf_token } = await fetch(u + '/me').then((r) => r.json())
      const r = await fetch(u + '/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf_token }, body: JSON.stringify({ email: 'short@example.com', password: 'abc' }) })
      return r.status
    }, BASE + '/api')
    check(short === 400, `服务端密码过短返回 400 字段校验错误（${short}）`)
    await submit({ em: 'not-an-email', pw: 'long-enough-pw-1', pw2: 'long-enough-pw-1' })
    await sleep(800)
    check((await errOf('em')).includes('邮箱格式不正确'), '服务端字段校验错误映射到表单字段')
    await submit({ em: email, pw: '1234567890', pw2: '1234567890' })
    await sleep(800)
    check((await errOf('pw')).includes('过于常见'), '弱密码提示（400 weak_password）')

    // 4. 注册成功 → 学习中心，首次导入生效
    const pw = 'camel-e2e-' + Date.now()
    await submit({ em: email, pw, pw2: pw })
    await p.waitForFunction(() => location.pathname === '/dashboard' && document.querySelector('.xt-stat-v'), { timeout: 10000 })
    const first = await api(`/progress/${C.id}`)
    if (!first?.state) throw new Error(`${API} 上的后端没有课程 ${C.id}：XT_API 须指向以 --courses ${COURSE_DIR} 启动的后端`)
    console.log(`  课程 ${C.id}（content_version ${first.content_version}）`)
    const dash = await api(`/dashboard?tz=${encodeURIComponent('Asia/Hong_Kong')}`)
    check(dash.summary.xp_total === 10 && first.state.done[ID.read0] === 1, `首次登录 /import 合并本机进度 xp_total=${dash.summary.xp_total}`)
    check((await p.$eval('.xt-stat-v', (e) => e.textContent)).startsWith('10'), '学习中心显示真实数据')
    const lv = dash.courses[0]
    const want = lv.level.next_level_xp == null ? 100 : ((lv.xp - lv.level.level_min_xp) / (lv.level.next_level_xp - lv.level.level_min_xp)) * 100
    const got = await p.$eval('.xt-lvbar span', (e) => parseFloat(e.style.width))
    check(Math.abs(got - want) < 0.01, `等级进度条按本级区间 ${got}%/${want}%`)
    const li = dash.last_import
    const imp = await p.$eval('tr.xt-act-import', (e) => e.textContent).catch(() => '')
    check(!!li && imp.includes('⬆️') && imp.includes(`新增 ${li.items_added} 项`) && (li.xp_delta ? imp.includes(`+${li.xp_delta} XP`) : !imp.includes('XP')), '最近活动含 last_import 导入汇总: ' + imp.replace(/\s+/g, ' '))
    check(await p.evaluate((ch) => [...document.querySelectorAll('.xt-chapter')].some((e) => e.querySelector('.xt-chapter-no')?.textContent === ch && e.textContent.includes('本章无 Boss')), P0.id), `学习中心按 has_boss 显示「本章无 Boss」（${P0.id}）`)
    await p.evaluate(() => [...document.querySelectorAll('.xt-danger-zone button')][0].click())
    await p.waitForSelector('#xt-reset-dlg')
    const rs = await p.evaluate(() => ({ inert: document.getElementById('root').hasAttribute('inert'), dis: document.querySelector('#xt-reset-dlg .xt-btn--danger').disabled }))
    const rt = await trapped('#xt-reset-dlg')
    await p.keyboard.press('Escape'); await sleep(200)
    const rback = await p.evaluate(() => !document.querySelector('#xt-reset-dlg') && !document.getElementById('root').hasAttribute('inert') && document.activeElement?.textContent.startsWith('清空'))
    check(rs.inert && rs.dis && rt && rback, `重置对话框（确认清空禁用）Tab 循环不出框、背景 inert，关闭后复原 ${rs.inert}/${rs.dis}/${rt}/${rback}`)
    const danger = await p.$$eval('.xt-danger-zone button', (bs) => bs.map((b) => b.textContent))
    check(dash.courses.every((c) => danger.includes('清空 ' + c.title)), '危险按钮为「清空 <课程名>」: ' + danger.join('、'))

    // 5. 409：同邮箱再注册（另开无痕上下文）
    const ctx2 = await b.createBrowserContext()
    const p2 = await ctx2.newPage()
    await p2.goto(BASE + '/register', { waitUntil: 'networkidle0' })
    for (const [id, v] of Object.entries({ em: email, pw, pw2: pw })) await p2.type('#' + id, v)
    await p2.click('button[type=submit]')
    await sleep(800)
    check((await p2.$eval('#em-e', (e) => e.textContent).catch(() => '')).includes('已注册'), '邮箱已注册提示（409）')
    await ctx2.close()

    // 6. 阅读页嵌入样式与高度自适应（示例课程 00 页）
    await p.goto(BASE + `/${C.id}/` + encodeURIComponent(P0.file), { waitUntil: 'networkidle0' })
    let f = await visible()
    const info = await f.evaluate(() => ({ embed: document.documentElement.classList.contains('xt-embed'), h: document.documentElement.scrollHeight }))
    const fh = await p.$eval('iframe.xt-frame', (e) => e.getBoundingClientRect().height)
    check(info.embed, 'iframe 已加 xt-embed')
    check(Math.abs(fh - info.h) < 5, `iframe 高度自适应 ${fh}/${info.h}`)
    check(await f.evaluate((k, id) => !!JSON.parse(localStorage.getItem(k)).done[id], KEY, ID.read0), '回写后 iframe 内可见服务端进度')
    check(await f.evaluate((id) => { const b = document.querySelector(`.xt-check[data-id="${id}"]`); return !!b && b.disabled && b.getAttribute('aria-pressed') === 'true' }, ID.read0), '再次进入时读完打卡按本地状态显示已打卡')
    await p.screenshot({ path: path.join(OUT, 'reader-1280.png') })
    // 7. iframe 内写入作答状态（static 页无引擎脚本，模拟作答）→ storage 事件 → 上报
    await f.evaluate((k, id) => { const s = JSON.parse(localStorage.getItem(k)); s.xp[id] = 10; s.solved[id] = { rev: false, wrong: 1 }; localStorage.setItem(k, JSON.stringify(s)) }, KEY, ID.quiz)
    await sleep(1500)
    await p.waitForFunction((id) => document.querySelector('.xt-sync')?.classList.contains('xt-sync--synced') && !Object.keys(localStorage).some((k) => k.startsWith('xt-outbox') && localStorage.getItem(k).includes(`"${id}"`)), { timeout: 10000 }, ID.quiz).catch(() => {})
    const snap = await api(`/progress/${C.id}`)
    if (!snap.state?.xp[ID.quiz]) console.log('  debug', JSON.stringify(snap.state?.xp), await p.evaluate(() => JSON.stringify(Object.keys(localStorage))))
    check(snap.state.xp[ID.quiz] === 10 && snap.state.solved[ID.quiz]?.wrong === 1, '事件同步到服务端快照')
    check((await p.$eval('.xt-sync', (e) => e.className)).includes('xt-sync--synced'), '同步状态回到已同步')

    // 8. 模拟换机：清空本机缓存后刷新，快照写回
    await p.evaluate((k) => { localStorage.removeItem(k) }, KEY)
    await p.reload({ waitUntil: 'networkidle0' })
    f = await visible()
    const back = await f.evaluate((k) => JSON.parse(localStorage.getItem(k) || 'null'), KEY)
    check(back?.xp[ID.quiz] === 10 && back?.done[ID.read0] === 1, '刷新后快照回写 localStorage')


    // 9a. 目录：章节、Boss 入口、「继续学习」
    await p.goto(BASE + `/${C.id}`, { waitUntil: 'networkidle0' })
    const toc = await p.evaluate(() => ({ t: document.querySelector('#root').textContent, boss: document.querySelectorAll('a[href*="#boss"]').length, cont: document.querySelector('.xt-continue')?.getAttribute('href') }))
    check(C.pages.every((x) => toc.t.includes(x.title.replace(/^\S+ · /, ''))) && !toc.t.includes('|') && toc.boss >= 1, `目录 ${C.pages.length} 章、标题无「|」、Boss 入口 ${toc.boss} 个`)
    check(!!toc.cont && toc.cont.startsWith(`/${C.id}/`), '「继续学习」指向课程内页面: ' + toc.cont)
    await p.goto(BASE + `/${C.id}/` + encodeURIComponent(P1.file), { waitUntil: 'networkidle0' })
    await visible()
    // 9b. 在线时上报失败显示「同步失败」，不显示唤醒态
    await p.setRequestInterception(true)
    const fail500 = (r) => (r.url().includes('/api/progress/') && r.url().endsWith('/events') ? r.respond({ status: 500, contentType: 'application/problem+json', body: '{"code":"internal_error","message":"x"}' }) : r.continue())
    p.on('request', fail500)
    f = await frame()
    await f.evaluate((k, a) => { const s = JSON.parse(localStorage.getItem(k)); s.xp[a] = 1; localStorage.setItem(k, JSON.stringify(s)) }, KEY, ID.q[0])
    await p.waitForSelector('.xt-sync--failed', { timeout: 5000 }).catch(() => {})
    const sb = await p.$eval('.xt-sync', (e) => ({ c: e.className, t: e.textContent }))
    check(sb.c.includes('xt-sync--failed') && sb.t.includes('同步失败') && !sb.t.includes('唤醒'), '在线上报失败显示同步失败: ' + sb.t)
    p.off('request', fail500)
    await p.setRequestInterception(false)
    await p.waitForSelector('.xt-sync--synced', { timeout: 10000 }).catch(() => {})
    check(!!(await p.$('.xt-sync--synced')), '恢复后自动重试成功')

    // 10. 手机抽屉
    const w1280 = await p.evaluate(() => { const b = document.querySelector('.xt-frame-box'); return { f: document.querySelector('iframe.xt-frame').getBoundingClientRect().width, bd: getComputedStyle(b).borderLeftWidth } })
    await p.setViewport({ width: 390, height: 800 })
    await sleep(300)
    const w390 = await p.evaluate(() => ({ f: document.querySelector('iframe.xt-frame').getBoundingClientRect().width, ov: document.documentElement.scrollWidth > innerWidth }))
    check(w390.f === 390 && !w390.ov && w1280.f < 1000 && w1280.bd !== '0px', `390 下 Reader 卡片贴边（iframe ${w390.f}px、无横向溢出），1280 保持卡片边框（iframe ${w1280.f}px）`)
    const crumbs = await p.$$eval('.xt-crumbs > span', (ss) => ss.map((e) => e.getClientRects().length))
    check(crumbs.length >= 2 && crumbs.every((n) => n === 1), `390 宽度面包屑各段不拆行 ${crumbs.join(',')}`)
    await p.click('#xt-menu')
    await sleep(300)
    const opened = await p.$eval('#xt-toc', (e) => e.hasAttribute('data-open') && getComputedStyle(e).visibility === 'visible')
    await p.keyboard.press('Escape')
    await sleep(300)
    const closed = await p.$eval('#xt-toc', (e) => !e.hasAttribute('data-open'))
    check(opened && closed, '手机目录抽屉开合（Esc 关闭）')
    await p.screenshot({ path: path.join(OUT, 'reader-390.png') })
    // 抽屉打开时浏览器后退：抽屉应关闭
    await p.click('#xt-menu'); await sleep(300)
    await p.click(`#xt-toc a.xt-toc-a[href$="/${encodeURIComponent(P0.file)}"]`); await sleep(800) // 抽屉内切到另一章
    await p.click('#xt-menu'); await sleep(300)
    const openedB = await p.$eval('#xt-toc', (e) => e.hasAttribute('data-open'))
    await p.goBack(); await sleep(800)
    check(openedB && (await p.$eval('#xt-toc', (e) => !e.hasAttribute('data-open'))), '390 抽屉打开时浏览器后退，抽屉关闭')
    await p.setViewport({ width: 1280, height: 800 })

    // 11. 有未同步进度时退出：离线下弹确认，「仍然退出」后队列保留在本机，重新登录后同步
    await p.goto(BASE + '/', { waitUntil: 'networkidle0' })
    const uid = (await api('/me')).user.id
    await p.evaluate((k, id, cid) => localStorage.setItem(k, JSON.stringify([{ course: cid, item_id: id, kind: 'xp', amt: 1, client_event_id: crypto.randomUUID(), ts: new Date().toISOString(), day: '2026-10-18' }])), `xt-outbox-${uid}`, ID.q[0], C.id)
    await p.setOfflineMode(true)
    await p.click('#xt-logout')
    await p.waitForSelector('#xt-logout-dlg', { timeout: 5000 }).catch(() => {})
    check((await p.$eval('#lo-h', (e) => e.textContent).catch(() => '')).includes('还有 1 条进度未同步'), '退出前提示未同步条数')
    const dlg = await p.$eval('#xt-logout-dlg', (d) => ({ btns: [...d.querySelectorAll('button')].map((b) => b.textContent), bg: getComputedStyle(d.querySelector('.xt-dialog-ic')).backgroundColor, p: d.querySelector('.xt-p').textContent }))
    check(dlg.btns.join('|') === '取消|重试|仍然退出' && dlg.p.includes('保留在本机') && dlg.bg === 'rgb(255, 241, 168)', `退出弹窗按钮顺序/文案/警示黄 ${dlg.btns.join('|')} ${dlg.bg}`)
    const lt = await trapped('#xt-logout-dlg')
    const bg = await p.evaluate(() => document.getElementById('root').hasAttribute('inert') && document.body.style.overflow === 'hidden')
    check(lt && bg, `退出对话框 Tab/Shift+Tab 不离开对话框、背景 inert 且不滚动 ${lt}/${bg}`)
    const reopen = async () => { await p.click('#xt-logout'); await p.waitForSelector('#xt-logout-dlg', { timeout: 5000 }) }
    const closedBack = () => p.evaluate(() => !document.querySelector('#xt-logout-dlg') && document.activeElement?.id === 'xt-logout')
    await p.keyboard.press('Escape'); await sleep(200)
    const byEsc = await closedBack()
    await reopen(); await p.mouse.click(5, 790); await sleep(200)
    const byScrim = await closedBack()
    await reopen(); await p.evaluate(() => [...document.querySelectorAll('#xt-logout-dlg button')].find((x) => x.textContent === '取消').click()); await sleep(200)
    const byCancel = await closedBack()
    check(byEsc && byScrim && byCancel, `退出弹窗 Esc/遮罩/取消 关闭且焦点回到退出按钮 ${byEsc}/${byScrim}/${byCancel}`)
    await reopen()
    await p.evaluate(() => [...document.querySelectorAll('#xt-logout-dlg button')].find((x) => x.textContent.startsWith('仍然退出')).click())
    await sleep(800)
    check(!!(await p.$('.xt-top a[href="/login"]')), '离线「仍然退出」后立即进入未登录')
    check(await p.evaluate(() => !!localStorage.getItem('xt-pending-logout')), '记录待补发注销标记')
    await p.setOfflineMode(false)
    check(await p.evaluate((k) => JSON.parse(localStorage.getItem(k) || '[]').length === 1, `xt-outbox-${uid}`), '「仍然退出」后队列保留在本机')
    // 联网刷新：先补发注销，仍为未登录且服务端会话已作废
    await p.goto(BASE + '/', { waitUntil: 'networkidle0' })
    await sleep(500)
    check(!!(await p.$('.xt-top a[href="/login"]')) && await p.evaluate(() => !localStorage.getItem('xt-pending-logout')), '联网刷新后仍为未登录，补发注销成功并清标记')
    check((await api('/me')).user === null, '服务端会话已作废（/api/me user=null）')
    await p.goto(BASE + '/login', { waitUntil: 'networkidle0' })
    await submit({ em: email, pw })
    await p.waitForFunction((k) => !localStorage.getItem(k), { timeout: 10000 }, `xt-outbox-${uid}`).catch(() => {})
    check((await api(`/progress/${C.id}`)).state.xp[ID.q[0]] > 0, '再次登录后保留的进度完成同步')
    // 正常退出（已同步）：不弹框，清掉本机课程进度与归属
    await p.goto(BASE + '/', { waitUntil: 'networkidle0' })
    check(await p.evaluate((k) => !!localStorage.getItem(k) && localStorage.getItem('xt-owner') !== null, KEY), '登录后本机课程进度归属当前账号')
    await p.evaluate(() => [...document.querySelectorAll('.xt-top button')].find((x) => x.textContent === '退出').click())
    await sleep(800)
    check(!(await p.$('#xt-logout-dlg')), '队列为空时直接退出')
    check(await p.evaluate((k) => !localStorage.getItem(k) && !localStorage.getItem('xt-owner'), KEY), 'A 做题后正常退出：本机课程进度与 xt-owner 已清')

    // 12. 退出后受保护页跳转 → 登录（含错误密码 401）
    await p.goto(BASE + `/${C.id}`, { waitUntil: 'networkidle0' })
    check(new URL(p.url()).pathname === '/login', '退出后受保护页跳转登录')
    await submit({ em: email, pw: pw + 'x' })
    await sleep(800)
    check((await errOf('pw')).includes('不正确'), '错误密码提示（401）')
    await submit({ em: email, pw })
    await p.waitForFunction((cid) => location.pathname === '/' + cid, { timeout: 10000 }, C.id).catch(() => {})
    check(new URL(p.url()).pathname === `/${C.id}`, '登录后回到原地址（next）')

    // 13. A 离线退出（有未同步进度，本机进度保留）后 B 登录：不收到 A 的进度
    await p.goto(BASE + `/${C.id}/` + encodeURIComponent(P1.file), { waitUntil: 'networkidle0' })
    await visible() // 回写后本机有 A 的课程进度
    const uidA = (await api('/me')).user.id
    await p.evaluate((k, ok, id, cid) => {
      const s = JSON.parse(localStorage.getItem(k)); s.xp[id] = 1; localStorage.setItem(k, JSON.stringify(s))
      localStorage.setItem(ok, JSON.stringify([{ course: cid, item_id: id, kind: 'xp', amt: 1, client_event_id: crypto.randomUUID(), ts: new Date().toISOString(), day: '2026-10-18' }]))
    }, KEY, `xt-outbox-${uidA}`, ID.q[1], C.id)
    await p.setOfflineMode(true)
    await p.evaluate(() => [...document.querySelectorAll('.xt-top button')].find((x) => x.textContent === '退出').click())
    await p.waitForSelector('#xt-logout-dlg', { timeout: 5000 })
    await p.evaluate(() => [...document.querySelectorAll('#xt-logout-dlg button')].find((x) => x.textContent.startsWith('仍然退出')).click())
    await sleep(500)
    await p.setOfflineMode(false)
    check(await p.evaluate((k, id) => !!JSON.parse(localStorage.getItem(k) || 'null')?.xp[id], KEY, ID.q[1]), 'A 离线退出后本机进度保留（归属 A）')
    const emailB = `e2e-b-${Date.now()}@example.com`
    await p.goto(BASE + '/register', { waitUntil: 'networkidle0' })
    await submit({ em: emailB, pw, pw2: pw })
    await p.waitForFunction(() => location.pathname === '/dashboard', { timeout: 10000 })
    const uidB = (await api('/me')).user.id
    await p.waitForSelector('.xt-table--act', { timeout: 10000 })
    check(!!(await p.$('.xt-table--act tr.xt-empty')), '最近活动空状态由组件渲染')
    check(Object.keys((await api(`/progress/${C.id}`)).state.xp).length === 0, 'B 账号服务端未收到 A 的进度（未上报、未导入）')
    await p.goto(BASE + `/${C.id}/` + encodeURIComponent(P1.file), { waitUntil: 'networkidle0' })
    await visible()
    const lb = await p.evaluate((k) => ({ s: JSON.parse(localStorage.getItem(k) || 'null'), o: localStorage.getItem('xt-owner') }), KEY)
    check(lb.o === String(uidB) && Object.keys(lb.s?.xp ?? {}).length === 0, `B 本机课程进度来自 B 的快照（owner=${lb.o}）`)
    check(await p.evaluate((k) => JSON.parse(localStorage.getItem(k) || '[]').length === 1, `xt-outbox-${uidA}`), 'A 的未同步队列仍保留，待 A 下次登录')

    // 14. 焦点返回候选与背景点击（账号 B）
    const focusId = () => p.evaluate(() => (document.activeElement === document.body ? 'body' : document.activeElement?.id || document.activeElement?.textContent.trim().slice(0, 8)))
    const openReset = async () => { await p.click('.xt-danger-zone button'); await p.waitForSelector('#xt-reset-dlg') }
    await p.goto(BASE + '/dashboard', { waitUntil: 'networkidle0' })
    await p.waitForSelector('.xt-danger-zone button')
    // 对话框打开时点击背景「退出」按钮位置：只关闭对话框，不触发退出
    await openReset()
    const box = await p.$eval('#xt-logout', (e) => { const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 } })
    await p.mouse.click(box.x, box.y); await sleep(500)
    check(!(await p.$('#xt-logout-dlg')) && !!(await p.$('#xt-logout')) && (await api('/me')).user?.id === uidB, '对话框打开时点击背景按钮不触发其行为')
    await p.keyboard.press('Escape').catch(() => {})
    // 390：禁用 / 删除触发按钮后焦点落到 logo（#xt-account 隐藏）
    await p.setViewport({ width: 390, height: 800 })
    await sleep(300)
    await openReset()
    await p.evaluate(() => { document.querySelector('.xt-danger-zone button').disabled = true })
    await p.keyboard.press('Escape'); await sleep(200)
    const fDis = await focusId()
    await p.evaluate(() => { document.querySelector('.xt-danger-zone button').disabled = false })
    await openReset()
    await p.evaluate(() => document.querySelector('.xt-danger-zone button').remove())
    await p.keyboard.press('Escape'); await sleep(200)
    const fDel = await focusId()
    check(fDis === 'xt-home' && fDel === 'xt-home', `390 触发按钮禁用/删除后焦点在 logo ${fDis}/${fDel}`)
    // 真实流程：重置成功（1280 / 390）
    for (const w of [1280, 390]) {
      await p.setViewport({ width: w, height: 800 })
      await p.goto(BASE + '/dashboard', { waitUntil: 'networkidle0' })
      await p.waitForSelector('.xt-danger-zone button')
      await openReset()
      await p.type('#cf', `RESET ${C.id}`)
      await p.click('#xt-reset-dlg .xt-btn--danger')
      await p.waitForFunction(() => !document.querySelector('#xt-reset-dlg'), { timeout: 5000 }).catch(() => {})
      await sleep(300)
      const f = await focusId()
      check(f !== 'body' && !(await p.$('#xt-reset-dlg')), `${w} 重置成功后焦点不在 body（${f}）`)
    }
    // 真实流程：在学习中心有未同步进度时「仍然退出」→ 受保护页重定向 /login（1280 / 390）
    for (const w of [1280, 390]) {
      await p.setViewport({ width: w, height: 800 })
      await p.goto(BASE + '/dashboard', { waitUntil: 'networkidle0' })
      if (new URL(p.url()).pathname !== '/dashboard') { await submit({ em: emailB, pw }); await p.waitForFunction(() => location.pathname === '/dashboard', { timeout: 10000 }) }
      await p.waitForSelector('#xt-logout', { timeout: 10000 })
      await p.evaluate((k, id, cid) => localStorage.setItem(k, JSON.stringify([{ course: cid, item_id: id, kind: 'xp', amt: 1, client_event_id: crypto.randomUUID(), ts: new Date().toISOString(), day: '2026-10-18' }])), `xt-outbox-${uidB}`, ID.q[2], C.id)
      await p.setOfflineMode(true)
      await p.click('#xt-logout')
      await p.waitForSelector('#xt-logout-dlg', { timeout: 5000 })
      await p.evaluate(() => [...document.querySelectorAll('#xt-logout-dlg button')].find((x) => x.textContent === '仍然退出').click())
      await p.waitForFunction(() => location.pathname === '/login' && !document.querySelector('#xt-logout-dlg'), { timeout: 5000 }).catch(() => {})
      // 登录页挂载时焦点可能在 body 停 1–2 帧：先等焦点到 h1（≤2s），再连续观察约 300ms 保持在 h1
      const reached = await p.waitForFunction(() => document.activeElement?.tagName === 'H1', { timeout: 2000 }).then(() => true, () => false)
      const frames = reached ? await watchFocus(18) : []
      check(new URL(p.url()).pathname === '/login' && reached && frames.every((f) => f === 'H1'), `${w} 退出跳转 /login 后焦点到达登录页标题并保持约 300ms（${[...new Set(frames)].join(',') || '未到达'}）`)
      await p.setOfflineMode(false)
      await p.goto(BASE + '/', { waitUntil: 'networkidle0' })
    }
    // 会话状态未知（延迟 /api/me）时顶栏不显示「登录/注册」，且不引起布局跳动
    await p.setViewport({ width: 1280, height: 800 })
    await p.goto(BASE + '/login', { waitUntil: 'networkidle0' })
    await submit({ em: emailB, pw })
    await p.waitForSelector('#xt-logout', { timeout: 10000 })
    await p.setRequestInterception(true)
    const slowMe = (r) => (r.url().endsWith('/api/me') ? setTimeout(() => r.continue().catch(() => {}), 1500) : r.continue().catch(() => {}))
    p.on('request', slowMe)
    await p.goto(BASE + '/', { waitUntil: 'domcontentloaded' })
    await p.waitForSelector('.xt-top')
    await sleep(300)
    const pos = () => p.evaluate(() => ({ h: document.querySelector('.xt-top').getBoundingClientRect().height, logo: document.getElementById('xt-home').getBoundingClientRect().x, nav: document.getElementById('xt-account')?.getBoundingClientRect().x }))
    const early = await p.evaluate(() => ({ ph: !!document.getElementById('xt-auth-ph'), login: [...document.querySelectorAll('.xt-top a[href="/login"], .xt-top a[href="/register"]')].length }))
    const p0 = await pos()
    await p.waitForSelector('#xt-logout', { timeout: 5000 }).catch(() => {})
    const p1 = await pos()
    p.off('request', slowMe)
    await p.setRequestInterception(false)
    check(early.ph && early.login === 0, `会话未知时顶栏不显示登录/注册（占位 ${early.ph}，链接 ${early.login}）`)
    check(!!(await p.$('#xt-logout')) && p0.h === p1.h && p0.logo === p1.logo && p0.nav === p1.nav, `会话确定后无布局跳动 ${JSON.stringify(p0)} → ${JSON.stringify(p1)}`)
    await p.setViewport({ width: 1280, height: 800 })


    // 示例课程页面引擎不绑定 .xt-check（读完打卡只由外层阅读器处理）
    {
      const js = require('node:fs').readdirSync(COURSE_DIR, { withFileTypes: true }).filter((d) => d.isDirectory()).flatMap((d) => { const f = path.join(COURSE_DIR, d.name, 'assets'); return fs.existsSync(f) ? fs.readdirSync(f).filter((x) => x.endsWith('.js')).map((x) => fs.readFileSync(path.join(f, x), 'utf8')) : [] })
      const code = js.map((t) => t.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '')).join('\n')
      check(!/xt-check/.test(code), `示例课程引擎脚本（${js.length} 个）未绑定 .xt-check`)
    }
    // 15. 示例课程：跟踪项、读完打卡、作答、Boss、毕业、学习中心计分口径（独立账号 C，独立浏览器上下文）
    {
      const IT = ITEMS(C.id)
      const ctx3 = await b.createBrowserContext()
      const q = await ctx3.newPage()
      await q.setViewport({ width: 1280, height: 800 })
      const qapi = (u) => q.evaluate((u) => fetch(u, { credentials: 'include' }).then((r) => r.json()), BASE + '/api' + u)
      const settle = async () => { await sleep(1500); await q.waitForFunction(() => document.querySelector('.xt-sync--synced') && !Object.keys(localStorage).some((k) => k.startsWith('xt-outbox-') && localStorage.getItem(k) !== '[]'), { timeout: 15000 }).catch(() => {}) }
      const qframe = async () => { await q.waitForFunction(() => document.querySelector('iframe.xt-frame')?.style.visibility === 'visible', { timeout: 15000 }); return (await q.$('iframe.xt-frame')).contentFrame() }
      await q.goto(BASE + '/register', { waitUntil: 'networkidle0' })
      for (const [id, v] of Object.entries({ em: `e2e-c-${Date.now()}@example.com`, pw, pw2: pw })) await q.type('#' + id, v)
      await q.click('button[type=submit]')
      await q.waitForFunction(() => location.pathname === '/dashboard', { timeout: 10000 })
      // 15a. 00 页：跟踪项勾选（0 XP，记 rec）+ 读完打卡（done）
      await q.goto(BASE + `/${C.id}/` + encodeURIComponent(P0.file), { waitUntil: 'networkidle0' })
      let g = await qframe()
      const track = await g.$eval('input.track[data-id]', (e) => e.dataset.id)
      await g.$eval('input.track[data-id]', (e) => e.click())
      // 读完打卡只产生一次上报：统计点击后到同步结束期间 /events 请求中含该 id 的事件数
      const evCount = []; const onEv = (r) => { if (/\/api\/progress\/[^/]+\/events$/.test(r.url()) && r.method() === 'POST') { try { evCount.push(...JSON.parse(r.postData()).events.filter((e) => e.item_id === ID.read0)) } catch {} } }
      q.on('request', onEv)
      await g.$eval(`.xt-check[data-id="${ID.read0}"]`, (e) => e.click())
      await settle()
      const once = evCount.length
      await g.$eval(`.xt-check[data-id="${ID.read0}"]`, (e) => { e.disabled = false; e.click(); e.disabled = true }) // 已打卡按钮再次点击（绕过 disabled）
      await g.$eval(`.xt-check[data-id="${ID.read0}"]`, (e) => e.click())
      await settle()
      q.off('request', onEv)
      check(once === 1 && evCount.length === 1 && evCount[0].kind === 'done' && evCount[0].value === true, `读完打卡点击一次只上报 1 条 done 事件，再次点击不上报（共 ${evCount.length} 条）`)
      const btn = await g.$eval(`.xt-check[data-id="${ID.read0}"]`, (e) => ({ dis: e.disabled, pressed: e.getAttribute('aria-pressed'), cls: e.classList.contains('xt-check--done') }))
      await settle()
      let snap = await qapi(`/progress/${C.id}`)
      check(snap.state.rec[track] === 1 && !(track in snap.state.xp) && IT[track]?.max_xp === 0, `跟踪项 ${track} 勾选上报：记入 rec、0 XP`)
      check(btn.dis && btn.pressed === 'true' && btn.cls && snap.state.done[ID.read0] === 1 && snap.state.xp[ID.read0] === IT[ID.read0].max_xp, `读完打卡 ${ID.read0}：按钮已打卡（disabled/aria-pressed），服务端 done、XP ${snap.state.xp[ID.read0]}`)
      // 15b. 换设备：清本机状态后重进，按快照恢复打卡与勾选
      await q.evaluate((k) => localStorage.removeItem(k), KEY)
      await q.reload({ waitUntil: 'networkidle0' })
      g = await qframe()
      const restored = await g.evaluate((id, t) => ({ b: document.querySelector(`.xt-check[data-id="${id}"]`).disabled, t: document.querySelector(`input.track[data-id="${t}"]`).checked }), ID.read0, track)
      check(restored.b && restored.t, `换设备后读完打卡与跟踪项恢复 ${JSON.stringify(restored)}`)
      // 15c. 01 页：页面组件作答（按 data-answer 一次答对）+ Boss 单关通关 + 读完打卡 → 毕业
      await q.goto(BASE + `/${C.id}/` + encodeURIComponent(P1.file), { waitUntil: 'networkidle0' })
      g = await qframe()
      await g.evaluate(() => { for (const el of document.querySelectorAll('[data-answer]')) el.querySelector(`button[data-opt="${el.dataset.answer}"]`)?.click() })
      await sleep(500)
      await g.$eval(`.xt-check[data-id="${ID.read1}"]`, (e) => e.click())
      await settle()
      snap = await qapi(`/progress/${C.id}`)
      check(snap.state.xp[ID.quiz] === IT[ID.quiz].max_xp && snap.state.done[ID.read1] === 1, `作答 ${ID.quiz} 与读完打卡 ${ID.read1} 记入服务端`)
      check(ID.boss.length >= 3 && ID.boss.every((id) => id in snap.state.xp), `Boss 关卡项 ${ID.boss.join(',')} 记入服务端`)
      const badges = Object.keys(snap.state.badges)
      check(badges.includes('grad'), `毕业章全部完成后发放毕业徽章（徽章 ${badges.join(',')}）`)
      // 15d. 学习中心：计分口径与请求
      const dReqs = []; const onReq = (r) => { if (/\/api\//.test(r.url())) dReqs.push(new URL(r.url()).pathname) }
      q.on('request', onReq)
      await q.goto(BASE + '/dashboard', { waitUntil: 'networkidle0' })
      q.off('request', onReq)
      check(dReqs.some((u) => u.endsWith('/api/dashboard')) && !dReqs.some((u) => /\/api\/progress\//.test(u)), `学习中心只请求 /dashboard，无 /api/progress/*（${[...new Set(dReqs)].join(' ')}）`)
      const dC = await qapi('/dashboard')
      const card = dC.courses.find((c) => c.course === C.id)
      const scored = Object.values(IT).filter((x) => x.max_xp > 0).length
      check(card && card.scored_total === scored && card.scored_done === scored && card.tracks_done === 1, `学习中心计分项 ${card?.scored_done}/${card?.scored_total}（清单 ${scored}），跟踪项 tracks_done=${card?.tracks_done}`)
      const txt = await q.evaluate((t) => [...document.querySelectorAll('.xt-card')].find((e) => e.textContent.includes(t))?.textContent ?? '', C.title)
      check(txt.includes(`/ ${scored} · 已勾选 1 项记录`), '学习中心卡片显示计分项与「已勾选 1 项记录」')
      const grp = await q.$eval(`.xt-badge-group[data-course="${C.id}"] h3`, (e) => [e.textContent, getComputedStyle(e).color]).catch(() => null)
      check(grp?.[0] === C.title && grp[1] !== 'rgb(0, 0, 0)', `徽章组标题取清单 title、颜色取 --c-d（${grp?.join(' ')}）`)
      const ic = await q.goto(BASE + '/', { waitUntil: 'networkidle0' }).then(() => q.$eval(`.xt-course[data-course="${C.id}"] .xt-course-ic`, (e) => getComputedStyle(e).backgroundColor)).catch(() => '')
      check(!!ic && ic !== 'rgba(0, 0, 0, 0)', `首页课程卡图标底色由 accent 派生（${ic}）`)
      await ctx3.close()
    }
    // 16. 阅读页地址批量检查（/api/courses 中全部课程；教材页由后端从 COURSE_DIR 提供）
    const cc = await checkContent({ browser: b, base: BASE, courses: COURSES })
    check(!cc.fails.length, `阅读页地址 ${cc.routes} 个外层地址 200、教材页 ${cc.pages} 个及 /course/** 资源 200、旧锚点 ${cc.anchors} 个目标页与锚点元素存在${cc.fails.length ? `（${cc.fails.length} 处问题见上）` : ''}`)
  } catch (e) {
    check(false, '异常: ' + e.message)
  }
  await b.close()
  // 按进程组 PID 结束 vite preview 与后端，并删除后端临时目录（SQLite 库、内容缓存、XIAOTUO_DATA_DIR）
  stopProc(srv)
  await be.stop()
  process.exit(fails.length ? 1 : 0)
})()
