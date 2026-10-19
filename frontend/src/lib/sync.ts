// 进度同步：iframe 内 course.js 写 localStorage → 外层收到 storage 事件 → 300ms 防抖差分 → 离线队列 → 上报
import * as ob from './outbox'
import { clearCourseLocal, markOwner, ownerDecision, readOwner } from './owner'
import type { Owner } from './outbox'
import { ApiError, getSnapshot, importState, postEvents } from './api'
import { courseById, courseByKey, getCourses, type Course } from './courses'
import { diffState, localDay, parseState, totalXP, type CourseCode, type ProgressEvent } from './state'

export type SyncStatus = 'idle' | 'pending' | 'syncing' | 'offline' | 'error' | 'gave-up' | 'expired'

const TTL_MS = 30 * 24 * 3600 * 1000 // 离线队列最长保留 30 天，短于服务端 180 天去重窗口
const DEBOUNCE_MS = 300
const RETRY_DELAYS = [1, 2, 4, 8, 16, 30, 30].map((s) => s * 1000) // 约 90 秒，覆盖应用与数据库冷启动
const BATCH_MAX = 500

let status: SyncStatus = 'idle'
let owner: Owner = null // 当前账号；未登录时事件入匿名队列、不上报
let expiredNotice = 0
const subs = new Set<(s: SyncStatus, expired: number) => void>()
const emit = () => subs.forEach((f) => f(status, expiredNotice))
const setStatus = (s: SyncStatus) => { status = s; emit() }
export const subscribe = (f: (s: SyncStatus, expired: number) => void) => { subs.add(f); f(status, expiredNotice); return () => { subs.delete(f) } }

const readOutbox = () => ob.readOutbox(owner)
const writeOutbox = (e: ProgressEvent[]) => ob.writeOutbox(owner, e)
export const pendingCount = () => readOutbox().length

/** 超过 30 天的事件不再重放（服务端去重窗口可能已过期），改为把该课程本地完整状态交给 /import 并集合并。
 *  返回已合并的课程数。导入成功后才从队列移除，失败则保留到下次重试。 */
async function mergeExpired(): Promise<number> {
  const now = Date.now()
  const stale = new Set(readOutbox().filter((e) => now - Date.parse(e.ts) >= TTL_MS).map((e) => e.course))
  for (const course of stale) {
    const c = courseById(course)
    const state = c && parseState(localStorage.getItem(c.key))
    if (state) await importState(course, state, `expired-${course}-${localDay()}`)
    writeOutbox(readOutbox().filter((e) => !(e.course === course && now - Date.parse(e.ts) >= TTL_MS)))
  }
  return stale.size
}

// ---- 防抖：窗口内以第一次事件前的状态为基线，窗口结束时与最新状态对比 ----
const windows = new Map<string, { base: string | null; timer: number }>()
let paused = false

function onStorage(e: StorageEvent) {
  const c = courseByKey(e.key)
  if (!c || paused) return
  const w = windows.get(c.key)
  if (w) { clearTimeout(w.timer); w.timer = window.setTimeout(() => close(c), DEBOUNCE_MS) }
  else windows.set(c.key, { base: e.oldValue, timer: window.setTimeout(() => close(c), DEBOUNCE_MS) })
}

function close(c: Course) {
  const w = windows.get(c.key)
  windows.delete(c.key)
  const next = parseState(localStorage.getItem(c.key))
  if (!w || !next) return
  enqueue(diffState(c.id as CourseCode, parseState(w.base), next))
}

function enqueue(drafts: ReturnType<typeof diffState>) {
  if (!drafts.length) return
  const now = new Date()
  const events = drafts.map((d) => ({ ...d, client_event_id: crypto.randomUUID(), ts: now.toISOString(), day: localDay(now) }) as ProgressEvent)
  writeOutbox([...readOutbox(), ...events])
  setStatus('pending')
  void flush()
}

// ---- 上报：按课程分批，client_event_id 保证重发幂等 ----
let flushing = false
let retryTimer = 0
let inflight: Promise<void> = Promise.resolve()
export function flush(attempt = 0): Promise<void> {
  if (flushing || owner == null) return inflight
  flushing = true
  inflight = doFlush(attempt)
  return inflight
}

async function doFlush(attempt: number): Promise<void> {
  clearTimeout(retryTimer)
  try {
    if (navigator.onLine && (await mergeExpired())) { expiredNotice += 1; emit() }
    while (readOutbox().length) {
      if (!navigator.onLine) return setStatus('offline')
      setStatus('syncing')
      const all = readOutbox()
      const course = all[0].course
      const batch = all.filter((e) => e.course === course).slice(0, BATCH_MAX)
      try {
        await postEvents(course, batch)
      } catch (e) {
        // 400/404/413/422 重发也不会成功：丢弃该批，避免阻塞队列（逐条拒收由服务端在 200 结果里返回，不走这里）
        if (!(e instanceof ApiError && e.permanent)) throw e
        console.warn('[sync] 丢弃无法上报的事件批', e.status, e.code)
      }
      const sent = new Set(batch.map((e) => e.client_event_id))
      writeOutbox(readOutbox().filter((e) => !sent.has(e.client_event_id)))
    }
    setStatus('idle')
  } catch (e) {
    const err = e instanceof ApiError ? e : null
    if (err?.status === 401) setStatus('expired') // 等重新登录后由 setOwner 触发上报
    else if (!navigator.onLine) setStatus('offline')
    else if (attempt < RETRY_DELAYS.length) {
      setStatus('error')
      const delay = Math.max(RETRY_DELAYS[attempt], (err?.retryAfter ?? 0) * 1000) // 429 遵守 Retry-After
      retryTimer = window.setTimeout(() => void flush(attempt + 1), delay)
    }
    else setStatus('gave-up') // 界面显示手动重试
  } finally {
    flushing = false
  }
}

/** 回写：加载 iframe 前调用。先上报本地独有进度，再以服务端快照为准写回；quiet/sections 保留本地，data 取并集（本地优先）。 */
export async function writeBack(courseId: string): Promise<void> {
  const c = courseById(courseId)
  if (!c || owner == null) return
  const code = c.id as CourseCode
  // 本机进度属于其他账号时不参与差分，直接以快照覆盖
  if (ownerDecision(readOwner(), owner) === 'other') clearCourseLocal()
  const local = parseState(localStorage.getItem(c.key))
  let snap = await getSnapshot(code)
  if (!snap) return
  const extra = local ? diffState(code, snap, local) : []
  if (extra.length) {
    enqueue(extra)
    await inflight
    snap = (await getSnapshot(code)) ?? snap
  }
  paused = true
  try {
    localStorage.setItem(c.key, JSON.stringify({ ...snap, quiet: local?.quiet ?? snap.quiet, data: { ...snap.data, ...local?.data }, sections: local?.sections ?? snap.sections }))
    markOwner(owner)
  } finally {
    paused = false
  }
}

/** 登录后首次：把本机未登录时的进度经 /import 并集合并到账号，每个账号每门课只做一次 */
export async function importLocalOnce(userId: number): Promise<number> {
  let n = 0
  for (const c of getCourses()) {
    const flag = `xt-imported-${userId}-${c.id}`
    const state = parseState(localStorage.getItem(c.key))
    if (localStorage.getItem(flag) || !state || totalXP(state) + Object.keys(state.done).length === 0) continue
    await importState(c.id as CourseCode, state, `first-login-${userId}-${c.id}`)
    localStorage.setItem(flag, '1')
    n++
  }
  return n
}

/** 切换账号：登录时并入匿名/旧版队列并上报；退出时停止重试，队列留在本机待该账号下次登录 */
export function setOwner(uid: Owner) {
  if (uid === owner) return
  clearTimeout(retryTimer)
  owner = uid
  if (uid != null) { ob.adoptOutbox(uid); void flush() }
  else setStatus(readOutbox().length ? 'pending' : 'idle')
}

/** 退出前调用：立即尝试上报，返回仍未同步的条数 */
export async function drain(): Promise<number> {
  await inflight
  await flush()
  return pendingCount()
}

/** 由 App 在课程目录加载闸门放行后调用（课程未载入时 storage 事件无法映射到课程） */
export function startSync() {
  const onOnline = () => void flush()
  window.addEventListener('storage', onStorage)
  window.addEventListener('online', onOnline)
  void flush()
  return () => { window.removeEventListener('storage', onStorage); window.removeEventListener('online', onOnline) }
}

/** 服务端清空后丢弃对应课程的待上报事件 */
export const dropQueued = (codes: string[]) => writeOutbox(readOutbox().filter((e) => !codes.includes(e.course)))
