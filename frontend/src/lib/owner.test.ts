import { describe, expect, it } from 'vitest'
import { classifyLogout } from './api'
import { ownerDecision } from './owner'

describe('本机课程进度归属', () => {
  it('无标记为匿名，可首次导入', () => {
    expect(ownerDecision(null, 7)).toBe('anon')
    expect(ownerDecision('', 7)).toBe('anon')
  })
  it('同账号 / 其他账号', () => {
    expect(ownerDecision('7', 7)).toBe('same')
    expect(ownerDecision('8', 7)).toBe('other')
  })
})

describe('注销响应分类', () => {
  it('204/401 视为已作废', () => {
    expect(classifyLogout(204)).toBe('done')
    expect(classifyLogout(401)).toBe('done')
  })
  it('403 取 CSRF 后重试', () => expect(classifyLogout(403)).toBe('csrf'))
  it('网络错误与 5xx 保留标记', () => {
    for (const s of [0, 500, 502, 503]) expect(classifyLogout(s)).toBe('keep')
  })
})

import { levelPct } from './level'
import { progress, units, bossTarget, type Page } from './courses'
import type { CourseState } from './state'

describe('等级进度条', () => {
  it('按本级区间计算', () => {
    expect(levelPct(820, { level_min_xp: 600, next_level_xp: 1000 })).toBe('55%')
    expect(levelPct(600, { level_min_xp: 600, next_level_xp: 1000 })).toBe('0%')
    expect(levelPct(5000, { level_min_xp: 3700, next_level_xp: null })).toBe('100%')
  })
})

describe('小节进度与 Boss 入口', () => {
  const st = { xp: { 'a-quiz': 10 }, done: { 'a-done-x': 1 }, rec: {}, solved: {}, fix: {} } as unknown as CourseState
  it('完成状态口径同 idDone', () => {
    expect(progress(st, ['a-done-x', 'a-quiz']).status).toBe('done')
    expect(progress(st, ['a-done-x', 'a-done-y']).status).toBe('part')
    expect(progress(null, ['a-done-x']).status).toBe('todo')
  })
  const page: Page = { id: '02', file: '02-x.html', title: '02 · 异步', xp: 0, sections: [], boss: '02-boss', ids: ['02-done-a', '02-boss-s1'], subs: [] }
  it('单页章：一个单元，Boss 指向页内锚点；无 Boss 返回 null', () => {
    expect(units(page)).toHaveLength(1)
    expect(bossTarget(page)).toMatchObject({ file: '02-x.html', hash: 'boss', ids: ['02-boss-s1'] })
    expect(bossTarget({ ...page, boss: null })).toBeNull()
  })
})

import { activityRows, importText } from './activity'

describe('最近活动导入汇总', () => {
  const ev = (at: string) => ({ at, course: 'alpha' as const, item_id: 'q', kind: 'xp', amt: 10, chapter_id: '01', page_id: '01-1' })
  it('文案：含 XP；XP 为 0 时省略', () => {
    expect(importText('课程甲', 3, 25)).toBe('导入了课程甲课程进度，新增 3 项，+25 XP')
    expect(importText('课程乙', 2, 0)).toBe('导入了课程乙课程进度，新增 2 项')
  })
  it('按 imported_at 与 recent 合并倒序', () => {
    const rows = activityRows([ev('2026-10-18T10:00:00Z'), ev('2026-10-18T08:00:00Z')], { imported_at: '2026-10-18T09:00:00Z', course: 'alpha', items_added: 3, xp_delta: 25 }, () => '课程甲')
    expect(rows.map((r) => r.type)).toEqual(['event', 'import', 'event'])
  })
  it('比导入早的事件排在导入记录下面', () => {
    const rows = activityRows([ev('2026-10-18T07:00:00Z')], { imported_at: '2026-10-18T09:00:00Z', course: 'alpha', items_added: 1, xp_delta: 0 }, String)
    expect(rows.map((r) => [r.type, r.at])).toEqual([['import', '2026-10-18T09:00:00Z'], ['event', '2026-10-18T07:00:00Z']])
  })
  it('两者都为空才为空列表', () => {
    expect(activityRows([], null, String)).toEqual([])
    expect(activityRows([], { imported_at: '2026-10-18T09:00:00Z', course: 'beta', items_added: 0, xp_delta: 0 }, String)).toHaveLength(1)
  })
})
