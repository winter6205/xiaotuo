import type { CSSProperties } from 'react'
import type { components } from './api-types'
import type { CourseState } from './state'

type S = components['schemas']
/** 课程元数据全部来自课程清单 course.json，运行时由后端 GET /api/courses 提供（启动时从课程目录生成），代码里不写死任何课程。
 *  类型由 api/openapi.yaml 生成（npm run gen:api），不手写 */
export type Course = S['CourseMeta']
export type Page = S['CoursePage']
export type Sub = S['CourseSub']
/** GET /api/courses 响应 */
export type CatalogResponse = S['CatalogResponse']

/** 目录加载失败：status=0 为网络错误，503 为后端目录不可用（catalog_unavailable） */
export class CatalogError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) { super(message); this.status = status; this.code = code }
}

// ---- 模块级缓存：loadCourses() 只请求一次（失败后可重试）；加载完成前同步 getter 返回空 ----
const URL_COURSES = `${import.meta.env.BASE_URL}api/courses`
const sortCourses = (list: Course[]) => list.slice().sort((a, b) => a.order - b.order || a.id.localeCompare(b.id))
/** 已加载的课程列表（ES 模块活绑定：加载后各处 import 的 courses 同步更新）。函数内读取，不要在模块顶层拷贝 */
export let courses: Course[] = []
let version: string | null = null
let loaded = false
let pending: Promise<Course[]> | null = null

export const getCourses = () => courses
export const catalogVersion = () => version
export const catalogLoaded = () => loaded

async function fetchCatalog(): Promise<Course[]> {
  let res: Response
  try {
    res = await fetch(URL_COURSES, { credentials: 'include', headers: { Accept: 'application/json' } })
  } catch {
    throw new CatalogError(0, 'network', '网络不可用，无法加载课程目录')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { code?: string; message?: string }
    throw new CatalogError(res.status, err.code ?? 'internal_error', err.message ?? `课程目录加载失败（HTTP ${res.status}）`)
  }
  const body = await res.json().catch(() => null) as CatalogResponse | null
  if (!body || !Array.isArray(body.courses)) throw new CatalogError(res.status, 'bad_response', '课程目录格式不正确')
  setCourses(body.courses, body.version ?? null)
  return courses
}

/** 加载课程目录（模块级缓存）。并发调用共用同一请求；失败时清掉缓存的 Promise，下次调用重新请求。
 *  force=true 时忽略已加载的结果重新请求（空目录「重新检查」用） */
export function loadCourses(force = false): Promise<Course[]> {
  if (pending) return pending // 进行中的请求直接复用（含 force）
  if (force) loaded = false
  if (loaded) return Promise.resolve(courses)
  pending = fetchCatalog().finally(() => { pending = null })
  return pending
}

/** 直接写入目录（单测与 loadCourses 内部使用） */
export function setCourses(list: Course[], v: string | null = null) {
  courses = sortCourses(list)
  version = v
  loaded = true
}

/** 仅测试用：恢复未加载状态 */
export function resetCourses() {
  courses = []; version = null; loaded = false; pending = null
}

export const courseById = (id?: string) => courses.find((c) => c.id === id)
/** 课程主题色变量：--c 取 accent（仅用于色块/装饰）；--c-l、--c-d 未在清单给出时由 xt.css 用 color-mix 派生。
 *  按钮文字与白字色底一律用 --c-d。 */
export function courseVars(c: Pick<Course, 'accent' | 'accentLight' | 'accentDark'>): CSSProperties {
  const v: Record<string, string> = { '--c': c.accent }
  if (c.accentLight) v['--c-l'] = c.accentLight
  if (c.accentDark) v['--c-d'] = c.accentDark
  return v as CSSProperties
}
export const courseByKey = (key: string | null) => courses.find((c) => c.key === key)

/** 旧锚点映射：目录页#旧锚点 → 小页#锚点，与 course.js 行为一致 */
export function resolveAnchor(c: Course, file: string, hash: string): { file: string; hash: string } {
  const target = c.anchors[file]?.[hash]
  return target ? { file: target, hash } : { file, hash }
}

/** 教材页地址，与外层同源，位于 <base>/course/<id>/ */
export const pageUrl = (c: Course, file: string, hash = '') =>
  `${import.meta.env.BASE_URL}course/${c.id}/${encodeURIComponent(file)}${hash ? '#' + hash : ''}`

// ---- 小节进度（口径同 course.js idDone）----
export const itemDone = (s: CourseState | null, id: string) =>
  !!s && (id.includes('-done-') ? id in s.done : id in s.done || id in s.rec || id in s.xp)

export type Status = 'done' | 'part' | 'todo'
export function progress(s: CourseState | null, ids: string[]): { done: number; total: number; status: Status } {
  const done = ids.filter((id) => itemDone(s, id)).length
  return { done, total: ids.length, status: ids.length && done === ids.length ? 'done' : done ? 'part' : 'todo' }
}

/** 章内学习单元：拆分页为各小节（不含 Boss 小节），单页章为整页 */
export const units = (p: Page): Sub[] =>
  p.subs.length ? p.subs.filter((u) => !u.boss) : [{ key: p.id, file: p.file, title: `${p.title.replace(/^\S+ · /, '')}（单页）`, ids: p.ids, boss: null }]

/** Boss 入口：拆分页指向 Boss 小节，单页章指向页内 Boss 节（教材约定 <section id="boss">，与 anchors 的 boss 键一致） */
export function bossTarget(p: Page): { file: string; hash: string; title: string; ids: string[] } | null {
  if (!p.boss) return null
  const sub = p.subs.find((u) => u.boss)
  const ids = p.ids.filter((id) => id.startsWith(p.boss + '-'))
  return sub ? { file: sub.file, hash: '', title: sub.title, ids } : { file: p.file, hash: 'boss', title: '👑 Boss 关', ids }
}

/** 页面所在章与小节（小页或章入口页） */
export function locate(c: Course, file: string): { page?: Page; sub?: Sub } {
  for (const page of c.pages) {
    if (page.file === file) return { page }
    const sub = page.subs.find((u) => u.file === file)
    if (sub) return { page, sub }
  }
  return {}
}

/** 继续学习：按顺序第一个未完成的单元（跳过无计分项的小节，否则会停在那里），全部完成时回到第一章 */
/** 「继续学习」不落到清单 home_chapter（目录首页章）；全部完成时回到第一个非首页章 */
export function continueTarget(c: Course, s: CourseState | null): { page: Page; unit: Sub } {
  const pages = c.pages.filter((p) => p.id !== c.homeChapter)
  const list = pages.length ? pages : c.pages
  for (const page of list) for (const unit of units(page)) if (unit.ids.length && progress(s, unit.ids).status !== 'done') return { page, unit }
  return { page: list[0], unit: units(list[0])[0] }
}

export const readerPath = (c: Course, file: string, hash = '') => `/${c.id}/${encodeURIComponent(file)}${hash ? '#' + hash : ''}`
