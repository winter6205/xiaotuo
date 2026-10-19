// 构建期导入：从课程根目录自动发现课程（<COURSE_DIR>/<子目录>/course.json），
// 复制教材页到 public/course/<id>/，生成 src/data/courses.json。规则见课程清单规范（schema 1）。
// COURSE_DIR：课程根目录，默认 ../course-content（相对仓库根）。校验失败退出码 2。
// CONTENT_DIR：后端计分清单目录（items-<id>.json），默认 backend/content（由后端 build_content.py 生成）。
//   存在时做页面 id ↔ 清单对照；不存在时跳过对照并告警。XT_REQUIRE_ITEMS=1 时缺失即失败（CI 用）。
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'

const repo = path.resolve(import.meta.dirname, '../..')
const root = path.resolve(repo, process.env.COURSE_DIR || '../course-content')
const out = path.resolve(import.meta.dirname, '../public/course')
const outFile = path.resolve(import.meta.dirname, '../src/data/courses.json')
const contentDir = path.resolve(repo, 'backend', process.env.CONTENT_DIR || 'content')

const ID_RE = /^[a-z][a-z0-9_]{0,15}$/
const HEX_RE = /^#[0-9a-fA-F]{6}$/
const ENGINES = ['course-manifest-js', 'static']

function fail(problems) {
  console.error(`课程清单校验失败（COURSE_DIR=${root}）：\n` + problems.map((p) => '  - ' + p).join('\n'))
  process.exit(2)
}

// ---- 自动发现与校验 ----
export function discover(dir) {
  const problems = []
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) fail([`课程根目录不存在：${dir}`])
  const found = []
  for (const e of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    if (!e.isDirectory()) continue // 不跟随符号链接
    const f = path.join(dir, e.name, 'course.json')
    if (!fs.existsSync(f)) continue
    let m
    try { m = JSON.parse(fs.readFileSync(f, 'utf8')) } catch (err) { problems.push(`${e.name}/course.json 不是合法 JSON：${err.message}`); continue }
    const at = `${e.name}/course.json`
    if (m.schema !== 1) problems.push(`${at}: schema 必须为 1`)
    if (typeof m.id !== 'string' || !ID_RE.test(m.id)) problems.push(`${at}: id 不合规（${m.id}）`)
    if (typeof m.title !== 'string' || !m.title) problems.push(`${at}: 缺少 title`)
    if (typeof m.order !== 'number') problems.push(`${at}: order 必须为数字`)
    if (typeof m.accent !== 'string' || !HEX_RE.test(m.accent)) problems.push(`${at}: accent 必须为 #rrggbb`)
    for (const k of ['accent_light', 'accent_dark']) if (m[k] != null && !HEX_RE.test(m[k])) problems.push(`${at}: ${k} 必须为 #rrggbb`)
    if (m.state_version !== 1 && m.state_version !== 2) problems.push(`${at}: state_version 必须为 1 或 2`)
    const engine = m.engine
    if (!ENGINES.includes(engine)) problems.push(`${at}: engine 必填，取 ${ENGINES.join(' | ')}（${engine}）`)
    if (engine === 'static' && !(Array.isArray(m.chapters) && m.chapters.length)) problems.push(`${at}: engine=static 时 chapters 必填`)
    if (engine === 'static') for (const ch of m.chapters ?? []) if (!ch.file || !fs.existsSync(path.join(dir, e.name, ch.file))) problems.push(`${at}: 章节文件缺失 ${ch.file}`)
    if (engine === 'course-manifest-js' && !fs.existsSync(path.join(dir, e.name, 'assets/course-manifest.js'))) problems.push(`${at}: 缺少 assets/course-manifest.js`)
    if (m.storage_key != null && (typeof m.storage_key !== 'string' || !m.storage_key)) problems.push(`${at}: storage_key 必须为非空字符串`)
    if (m.graduation_chapters != null && !Array.isArray(m.graduation_chapters)) problems.push(`${at}: graduation_chapters 必须为数组`)
    found.push({ ...m, engine, dir: e.name, key: m.storage_key ?? `${m.id}-v${m.state_version}` })
  }
  const dup = (k) => found.map((c) => c[k]).filter((v, i, a) => v != null && a.indexOf(v) !== i)
  for (const v of new Set(dup('id'))) problems.push(`id 重复：${v}`)
  for (const v of new Set(dup('key'))) problems.push(`storage_key 重复：${v}`)
  if (!found.length) problems.push('未发现任何课程（子目录下需有 course.json）')
  if (problems.length) fail(problems)
  return found.sort((a, b) => a.order - b.order || a.id.localeCompare(b.id))
}

// ---- 页面静态解析：Boss 节以外的 data-id（不含 input.track）+ Boss 关卡 <boss>-s1..sN、-clear、-perfect ----
function splitBoss(html) {
  // Boss 节：<section id="boss"> 到其 </section>（Boss 节内不嵌套 section）
  const at = html.search(/<section id="boss"/)
  const close = at < 0 ? -1 : html.indexOf('</section>', at)
  const end = close < 0 ? -1 : close + '</section>'.length
  return { boss: at < 0 ? '' : html.slice(at, end < 0 ? undefined : end), rest: at < 0 ? html : html.slice(0, at) + (end < 0 ? '' : html.slice(end)) }
}
const tracksOf = (html) => [...html.matchAll(/<input[^>]*class="track"[^>]*data-id="([^"]+)"/g)].map((m) => m[1])

function pageIds(file, bossId, expect) {
  const html = fs.readFileSync(file, 'utf8')
  const { boss, rest } = splitBoss(html)
  const ids = [...rest.matchAll(/<\w+([^>]*?)data-id="([^"]+)"/g)].filter((m) => !/class="track"/.test(m[1])).map((m) => m[2])
  if (bossId && boss) {
    const n = (boss.match(/class="stage[\s"]/g) ?? []).length
    for (let i = 1; i <= n; i++) ids.push(`${bossId}-s${i}`)
    ids.push(`${bossId}-clear`, `${bossId}-perfect`)
  }
  if (expect != null && ids.length !== expect) throw new Error(`${file}: 推出 ${ids.length} 个 id，manifest items=${expect}`)
  return ids
}

// engine=course-manifest-js：读 assets/course-manifest.js
function fromManifestJs(src) {
  const ctx = { window: {} }
  vm.runInNewContext(fs.readFileSync(path.join(src, 'assets/course-manifest.js'), 'utf8'), ctx)
  const m = ctx.window.COURSE_MANIFEST
  return {
    generated: m.generated, total: m.total, anchors: m.anchors || {},
    pages: Object.entries(m.pages).map(([pid, p]) => ({
      id: pid, file: p.file, title: p.title.split(/\s*\|\s*/)[0], xp: p.xp, sections: p.sections, boss: p.boss ?? null,
      ids: p.ids ?? pageIds(path.join(src, p.file), p.boss, p.items),
      subs: (p.subpages ?? []).map((sp) => ({ key: sp.key, file: sp.file, title: sp.title.split(/\s*\|\s*/)[0].replace(/^\S+ · /, ''), ids: sp.ids ?? [], boss: sp.boss ?? null })),
    })),
  }
}

// engine=static：按 chapters 逐页解析；XP 取元素 data-xp，否则按类型取清单 xp 默认值
function fromStatic(src, c) {
  const xpDef = { done: 10, quiz: 10, check: 10, ...(c.xp ?? {}) }
  let total = 0
  const pages = c.chapters.map((ch) => {
    const html = fs.readFileSync(path.join(src, ch.file), 'utf8')
    const { boss, rest } = splitBoss(html)
    // Boss：<section id="boss"><div class="boss" data-id="<章>-boss" data-badge>，内含 .stage
    const bossId = boss.match(/class="boss"[^>]*data-id="([^"]+)"/)?.[1] ?? boss.match(/data-id="([^"]+)"[^>]*class="boss"/)?.[1] ?? null
    const ids = pageIds(path.join(src, ch.file), bossId)
    let xp = 0
    for (const m of rest.matchAll(/<\w+([^>]*?)data-id="([^"]+)"/g)) {
      if (/class="track"/.test(m[1])) continue
      const own = m[1].match(/data-xp="(\d+)"/)
      const type = m[2].includes('-done-') ? 'done' : m[2].split('-')[1]
      xp += own ? Number(own[1]) : (xpDef[type] ?? xpDef.check)
    }
    // Boss 关卡分沿用引擎约定：每关 20、通关 50、无错 30（有后端清单时以清单 max_xp 为准）
    if (bossId) xp += (boss.match(/class="stage[\s"]/g) ?? []).length * 20 + 80
    total += xp
    return { id: ch.id, file: ch.file, title: ch.title, xp, sections: ids.filter((id) => id.includes('-done-')), boss: bossId ? bossId : null, ids, subs: [] }
  })
  return { generated: null, total, anchors: {}, pages }
}

// 页面推出的 id 与后端清单对照：差异必须恰好是 0 XP 跟踪项（input.track），否则失败。
// 通过后各章 / 小节的 ids 取清单里的计分项（max_xp > 0），按 items 的 page 字段归到所在章或小节。
function checkIds(c, course, back, src) {
  const tracks = new Set(fs.readdirSync(src).filter((f) => f.endsWith('.html')).flatMap((f) => tracksOf(fs.readFileSync(path.join(src, f), 'utf8'))))
  const front = new Set(course.pages.flatMap((p) => p.ids))
  const extra = [...front].filter((id) => !back.some((x) => x.id === id))
  const missing = back.filter((x) => !front.has(x.id)).map((x) => x.id)
  const wrong = missing.filter((id) => !tracks.has(id)).concat([...tracks].filter((id) => !missing.includes(id)))
  if (extra.length || wrong.length) throw new Error(`${c.id}: 页面 id 与 items-${c.id}.json 不一致，多出 [${extra}]，非跟踪项差异 [${wrong}]`)
  const of = (key) => back.filter((x) => x.page === key && x.max_xp > 0).map((x) => x.id)
  for (const p of course.pages) {
    for (const sp of p.subs) sp.ids = of(sp.key)
    p.ids = [...of(p.id), ...p.subs.flatMap((sp) => sp.ids)]
  }
  if (c.engine === 'static') {
    const xpOf = (key) => back.filter((x) => x.page === key).reduce((a, x) => a + x.max_xp, 0)
    for (const p of course.pages) p.xp = xpOf(p.id) + p.subs.reduce((a, sp) => a + xpOf(sp.key), 0)
    course.total = course.pages.reduce((a, p) => a + p.xp, 0)
  }
  const keys = new Set(course.pages.flatMap((p) => [p.id, ...p.subs.map((sp) => sp.key)]))
  const n = back.filter((x) => keys.has(x.page)).length
  if (n !== back.length) throw new Error(`${c.id}: 有 ${back.length - n} 个清单项的 page 不在章或小节里`)
}

const list = discover(root)
fs.rmSync(out, { recursive: true, force: true })
const data = []
const skipped = []
for (const c of list) {
  const src = path.join(root, c.dir)
  const dst = path.join(out, c.id)
  fs.mkdirSync(dst, { recursive: true })
  for (const f of fs.readdirSync(src)) if (f.endsWith('.html')) fs.copyFileSync(path.join(src, f), path.join(dst, f))
  if (fs.existsSync(path.join(src, 'assets'))) fs.cpSync(path.join(src, 'assets'), path.join(dst, 'assets'), { recursive: true, filter: (p) => !p.includes('__pycache__') })
  const body = c.engine === 'static' ? fromStatic(src, c) : fromManifestJs(src)
  const course = {
    id: c.id, dir: c.dir, key: c.key, title: c.title, name: c.name ?? c.title, short: c.short ?? c.name ?? c.title, icon: c.icon ?? '📘',
    order: c.order, accent: c.accent, accentLight: c.accent_light ?? null, accentDark: c.accent_dark ?? null,
    stateVersion: c.state_version, courseId: c.course_id ?? null, engine: c.engine,
    homeChapter: c.home_chapter ?? null, graduation: c.graduation_chapters ?? null, ...body,
  }
  const itemsFile = path.join(contentDir, `items-${c.id}.json`)
  if (fs.existsSync(itemsFile)) checkIds(c, course, JSON.parse(fs.readFileSync(itemsFile, 'utf8')), src)
  else {
    skipped.push(c.id)
    // 无清单时 ids 去掉 Boss 以外的跟踪项已在解析中完成；计分口径以页面为准
  }
  data.push(course)
}
if (skipped.length) {
  const msg = `未找到后端计分清单 ${contentDir}/items-{${skipped}}.json，已跳过 id 对照（先运行 backend/scripts/build_content.py 生成）`
  if (process.env.XT_REQUIRE_ITEMS === '1') { console.error(msg); process.exit(2) }
  console.warn('WARN ' + msg)
}
fs.mkdirSync(path.dirname(outFile), { recursive: true })
fs.writeFileSync(outFile, JSON.stringify(data, null, 1))
console.log('imported', data.map((c) => `${c.id}:${c.pages.length} pages`).join(', '))
