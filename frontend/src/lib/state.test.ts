import { describe, expect, it } from 'vitest'
import { diffState, type CourseState } from './state'

const base = (): CourseState => ({
  version: 1, course: 'sample-course', xp: {}, done: {}, rec: {}, solved: {}, fix: {},
  streak: { cur: 0, best: 0, last: null }, days: {}, badges: {}, quiet: false, data: {}, sections: {},
})

describe('diffState', () => {
  it('同一 id 的 xp/solved/fix 合并为一条，0 分有效', () => {
    const n = base(); n.xp = { q1: 5, q2: 0 }; n.solved = { q1: { rev: false, wrong: 1 }, q2: { rev: true, wrong: 2 } }; n.fix = { q1: 1 }
    expect(diffState('alpha', base(), n)).toEqual([
      { course: 'alpha', item_id: 'q1', kind: 'xp', amt: 5, solved: { rev: false, wrong: 1 }, fix: true },
      { course: 'alpha', item_id: 'q2', kind: 'xp', amt: 0, solved: { rev: true, wrong: 2 } },
    ])
  })
  it('打卡与取消打卡', () => {
    const n = base(); n.done = { s1: 1 }; n.xp = { s1: 10 }
    expect(diffState('alpha', base(), n)).toEqual([{ course: 'alpha', item_id: 's1', kind: 'done', amt: 10, value: true }])
    const off = structuredClone(n); off.done = {}
    expect(diffState('alpha', n, off)).toEqual([{ course: 'alpha', item_id: 's1', kind: 'done', amt: 10, value: false }])
  })
  it('Boss 内只写 solved 的题', () => {
    const n = base(); n.solved = { 'b-q': { rev: false, wrong: 0 } }
    expect(diffState('alpha', base(), n)).toEqual([{ course: 'alpha', item_id: 'b-q', kind: 'solved', solved: { rev: false, wrong: 0 } }])
  })
  it('本地重置不上报', () => {
    const p = base(); p.xp = { q1: 10 }; p.done = { s1: 1 }
    expect(diffState('alpha', p, base())).toEqual([])
  })
  it('不上报 streak、quiet、badges、data', () => {
    const n = base(); n.streak = { cur: 2, best: 2, last: '2026-10-18' }; n.quiet = true; n.badges = { first: '2026-10-18' }; n.data = { 'cleared.03': 1 }
    expect(diffState('alpha', base(), n)).toEqual([])
  })
})

import { blankState, markRead } from './state'
describe('读完打卡', () => {
  it('写入 done 与 xp，差分为一条 done 事件；重复打卡不变', () => {
    const s0 = blankState(1, 'sample')
    const s1 = markRead(s0, 'c-done-read', 10, '2026-10-19')
    expect(diffState('alpha', s0, s1)).toEqual([{ course: 'alpha', item_id: 'c-done-read', kind: 'done', amt: 10, value: true }])
    expect(markRead(s1, 'c-done-read')).toBe(s1)
  })
  it('state_version 2 的空状态不带 course 字段', () => {
    expect('course' in blankState(2, 'x')).toBe(false)
  })
})
