// 离线队列按账号隔离：已登录 xt-outbox-<uid>，未登录 xt-outbox-anon；旧版单一队列 xt-outbox 登录时迁移
import type { ProgressEvent } from './state'

export type Owner = number | null
const LEGACY = 'xt-outbox'
const ANON = 'xt-outbox-anon'
export const outboxKey = (uid: Owner) => (uid == null ? ANON : `xt-outbox-${uid}`)

const parse = (key: string): ProgressEvent[] => {
  try { return JSON.parse(localStorage.getItem(key) || '[]') } catch { return [] }
}
export const readOutbox = (uid: Owner) => parse(outboxKey(uid))
export function writeOutbox(uid: Owner, events: ProgressEvent[]) {
  if (events.length) localStorage.setItem(outboxKey(uid), JSON.stringify(events))
  else localStorage.removeItem(outboxKey(uid))
}

/** 登录后把匿名队列与旧版队列并入该用户队列（按 client_event_id 去重），然后删除来源 */
export function adoptOutbox(uid: number): number {
  const mine = readOutbox(uid)
  const seen = new Set(mine.map((e) => e.client_event_id))
  const moved = [...parse(ANON), ...parse(LEGACY)].filter((e) => !seen.has(e.client_event_id) && seen.add(e.client_event_id))
  writeOutbox(uid, [...mine, ...moved])
  localStorage.removeItem(ANON)
  localStorage.removeItem(LEGACY)
  return moved.length
}
