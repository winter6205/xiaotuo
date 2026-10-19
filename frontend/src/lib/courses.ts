import data from '../data/courses.json'
import type { CSSProperties } from 'react'
import type { CourseState } from './state'

export interface Sub { key: string; file: string; title: string; ids: string[]; boss: string | null }
export interface Page { id: string; file: string; title: string; xp: number; sections: string[]; boss: string | null; ids: string[]; subs: Sub[] }
/** 课程元数据全部来自课程清单 course.json（构建期由 scripts/import-course.mjs 生成 courses.json），代码里不写死任何课程 */
export interface Course {
  id: string; dir: string; key: string; title: string; name: string; short: string; icon: string
  order: number; accent: string; accentLight: string | null; accentDark: string | null
  stateVersion: 1 | 2; courseId: string | null; engine: 'course-manifest-js' | 'static'
  homeChapter: string | null; graduation: string[] | null
  generated: string | null; total: number
  anchors: Record<string, Record<string, string>>; pages: Page[]
}
export const courses = (data as unknown as Course[]).slice().sort((a, b) => a.order - b.order || a.id.localeCompare(b.id))
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
