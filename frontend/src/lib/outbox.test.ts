// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { adoptOutbox, outboxKey, readOutbox, writeOutbox } from './outbox'
import type { ProgressEvent } from './state'

const ev = (id: string): ProgressEvent => ({ course: 'alpha', item_id: 'q', kind: 'rec', client_event_id: id, ts: '2026-10-18T00:00:00Z', day: '2026-10-18' }) as ProgressEvent

describe('outbox 按账号隔离', () => {
  beforeEach(() => localStorage.clear())

  it('不同 uid 与匿名队列互不可见', () => {
    writeOutbox(1, [ev('a')])
    writeOutbox(null, [ev('b')])
    expect(readOutbox(1).map((e) => e.client_event_id)).toEqual(['a'])
    expect(readOutbox(2)).toEqual([])
    expect(readOutbox(null).map((e) => e.client_event_id)).toEqual(['b'])
    expect(outboxKey(1)).toBe('xt-outbox-1')
  })

  it('登录时并入匿名与旧版队列、去重并删除来源', () => {
    writeOutbox(1, [ev('a')])
    writeOutbox(null, [ev('b'), ev('a')])
    localStorage.setItem('xt-outbox', JSON.stringify([ev('c')]))
    expect(adoptOutbox(1)).toBe(2)
    expect(readOutbox(1).map((e) => e.client_event_id)).toEqual(['a', 'b', 'c'])
    expect(localStorage.getItem('xt-outbox-anon')).toBeNull()
    expect(localStorage.getItem('xt-outbox')).toBeNull()
  })

  it('其他账号的队列不被并入，空队列不留 key', () => {
    writeOutbox(2, [ev('x')])
    adoptOutbox(1)
    expect(readOutbox(1)).toEqual([])
    expect(localStorage.getItem('xt-outbox-1')).toBeNull()
    expect(readOutbox(2)).toHaveLength(1)
  })
})
