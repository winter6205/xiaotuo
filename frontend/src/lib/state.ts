// course.js 的 localStorage 状态（见 shared/assets/course.js blank()）与差分规则（OpenAPI v0.2.0）
import type { components } from './api-types'

/** 课程 id（来自课程清单，^[a-z][a-z0-9_]{0,15}$） */
export type CourseCode = string
export type ProgressEvent = Omit<components['schemas']['ProgressEvent'], 'course'> & { course: CourseCode }

export interface CourseState {
  version: 1 | 2 // 由清单 state_version 决定：1 带 course 字段，2 不带
  course?: string
  xp: Record<string, number>
  done: Record<string, 1>
  rec: Record<string, 1>
  solved: Record<string, { rev: boolean; wrong: number }>
  fix: Record<string, 1>
  streak: { cur: number; best: number; last: string | null }
  days: Record<string, 1>
  badges: Record<string, string>
  quiet: boolean
  data: Record<string, unknown>
  sections: Record<string, string[]>
}

export function parseState(raw: string | null): CourseState | null {
  if (!raw) return null
  try {
    const s = JSON.parse(raw)
    return s && (s.version === 1 || s.version === 2) ? (s as CourseState) : null
  } catch {
    return null
  }
}

/** 空状态（与 course.js blank() 同构）；version 由清单 state_version 决定，version 1 时带 course（清单 course_id，缺省为课程 id） */
export const blankState = (version: 1 | 2, course?: string | null): CourseState => ({
  version, ...(version === 1 ? { course: course ?? undefined } : {}),
  xp: {}, done: {}, rec: {}, solved: {}, fix: {}, streak: { cur: 0, best: 0, last: null }, days: {}, badges: {}, quiet: false, data: {}, sections: {},
})

/** 读完打卡（static 引擎页面的 .xt-check）：写入 done 与 xp，返回新状态；已打卡则原样返回 */
export function markRead(s: CourseState, id: string, xp = DONE_XP, day = localDay()): CourseState {
  if (id in s.done) return s
  return { ...s, done: { ...s.done, [id]: 1 }, xp: { ...s.xp, [id]: xp }, days: { ...s.days, [day]: 1 } }
}

const progressSize = (s: CourseState | null) =>
  s ? Object.keys(s.xp).length + Object.keys(s.done).length + Object.keys(s.solved).length + Object.keys(s.rec).length : 0

/** 本地重置（教材页清空或覆盖式导入）：已完成项从有变无。此时不上报，下次回写由服务端快照恢复。 */
export const isLocalReset = (prev: CourseState | null, next: CourseState) => progressSize(prev) > 0 && progressSize(next) === 0

const DONE_XP = 10 // 打卡分值，course.js setDone L722

/** 学员时区的日期，用于活动日 */
export const localDay = (d = new Date()) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(d)

type Draft = Omit<ProgressEvent, 'client_event_id' | 'ts' | 'day'>

/** 对比前后状态生成事件。同一 id 的 xp/solved/fix 合并为一条；徽章、data、sections、streak、quiet 不上报。 */
export function diffState(course: CourseCode, prev: CourseState | null, next: CourseState): Draft[] {
  if (isLocalReset(prev, next)) return []
  const p = prev ?? ({ xp: {}, done: {}, rec: {}, solved: {}, fix: {} } as unknown as CourseState)
  const out: Draft[] = []
  const doneIds = new Set<string>()

  for (const id of Object.keys(next.done)) if (!(id in p.done)) { doneIds.add(id); out.push({ course, item_id: id, kind: 'done', amt: next.xp[id] ?? DONE_XP, value: true }) }
  for (const id of Object.keys(p.done)) if (!(id in next.done)) { doneIds.add(id); out.push({ course, item_id: id, kind: 'done', amt: next.xp[id] ?? DONE_XP, value: false }) }
  for (const id of Object.keys(next.rec)) if (!(id in p.rec)) out.push({ course, item_id: id, kind: 'rec', value: true })
  for (const id of Object.keys(p.rec)) if (!(id in next.rec)) out.push({ course, item_id: id, kind: 'rec', value: false })

  for (const id of Object.keys(next.xp)) {
    if (id in p.xp || doneIds.has(id)) continue
    const e: Draft = { course, item_id: id, kind: 'xp', amt: next.xp[id] }
    if (next.solved[id]) e.solved = next.solved[id]
    if (next.fix[id] && !p.fix[id]) e.fix = true
    out.push(e)
  }
  // Boss 内的题只写 solved 不写 xp
  for (const id of Object.keys(next.solved)) {
    if (id in p.solved || id in next.xp) continue
    const e: Draft = { course, item_id: id, kind: 'solved', solved: next.solved[id] }
    if (next.fix[id]) e.fix = true
    out.push(e)
  }
  return out
}

export const totalXP = (s: CourseState | null) => (s ? Object.values(s.xp).reduce((a, b) => a + b, 0) : 0)
