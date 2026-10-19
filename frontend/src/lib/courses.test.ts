import { describe, expect, it } from 'vitest'
import { continueTarget, courseVars, progress, units, type Course } from './courses'
import type { CourseState } from './state'

const blank = (): CourseState => ({ version: 1, course: 'x', xp: {}, done: {}, rec: {}, solved: {}, fix: {}, streak: { cur: 0, best: 0, last: null }, days: {}, badges: {}, quiet: false, data: {}, sections: {} })
// 合成课程（与任何真实课程无关）：a 章拆为两节 + Boss 节，b 章单页无计分项，c 章单页
const course: Course = {
  id: 'alpha', dir: 'alpha', key: 'alpha-v1', title: '合成课程', name: '合成课程', short: '合成', icon: '📘',
  order: 1, accent: '#336699', accentLight: null, accentDark: null, stateVersion: 1, courseId: null, engine: 'static',
  homeChapter: null, graduation: null, generated: null, total: 60, anchors: {},
  pages: [
    { id: 'a', file: 'a.html', title: 'a · 第一章', xp: 40, sections: [], boss: 'a-boss', ids: ['a-quiz-1', 'a-done-x', 'a-quiz-2', 'a-boss-s1'], subs: [
      { key: 'a-1', file: 'a-1.html', title: '一', ids: ['a-quiz-1', 'a-done-x'], boss: null },
      { key: 'a-2', file: 'a-2.html', title: '二', ids: ['a-quiz-2'], boss: null },
      { key: 'a-b', file: 'a-b.html', title: 'Boss', ids: ['a-boss-s1'], boss: 'a-boss' },
    ] },
    { id: 'b', file: 'b.html', title: 'b · 只读', xp: 0, sections: [], boss: null, ids: [], subs: [] },
    { id: 'c', file: 'c.html', title: 'c · 第三章', xp: 20, sections: [], boss: null, ids: ['c-quiz-1', 'c-done-read'], subs: [] },
  ],
}
const fill = (s: CourseState, ids: string[]) => { for (const id of ids) id.includes('-done-') ? (s.done[id] = 1) : (s.xp[id] = 1); return s }

describe('目录与继续学习（合成课程）', () => {
  it('单元：拆分页取非 Boss 小节，单页章为整页', () => {
    expect(units(course.pages[0]).map((u) => u.key)).toEqual(['a-1', 'a-2'])
    expect(units(course.pages[2])[0].key).toBe('c')
  })
  it('跟踪项（rec）不在 ids 中，不挡「继续学习」', () => {
    const s = fill(blank(), ['a-quiz-1', 'a-done-x']); s.rec['a-rec-setup'] = 1
    expect(progress(s, units(course.pages[0])[0].ids).status).toBe('done')
    expect(continueTarget(course, s).unit.key).toBe('a-2')
  })
  it('跳过无计分项的章节', () => {
    const s = fill(blank(), ['a-quiz-1', 'a-done-x', 'a-quiz-2'])
    expect(continueTarget(course, s).unit.key).toBe('c')
  })
  it('全部完成回到第一章', () => {
    const s = fill(blank(), course.pages.flatMap((p) => p.ids))
    expect(continueTarget(course, s).unit.key).toBe('a-1')
  })
})

describe('主题色变量', () => {
  it('只给 accent 时只设 --c（--c-l/--c-d 由 CSS 派生）', () => {
    expect(courseVars(course)).toEqual({ '--c': '#336699' })
  })
  it('清单给出 accent_light/accent_dark 时直接使用', () => {
    expect(courseVars({ accent: '#112233', accentLight: '#eeeeee', accentDark: '#001122' })).toEqual({ '--c': '#112233', '--c-l': '#eeeeee', '--c-d': '#001122' })
  })
})

describe('「继续学习」跳过 home_chapter', () => {
  const home: Course = { ...course, homeChapter: 'h', pages: [{ id: 'h', file: 'h.html', title: 'h · 首页', xp: 10, sections: [], boss: null, ids: ['h-done-read'], subs: [] }, ...course.pages] }
  it('首页章未完成时也不指向首页章', () => {
    expect(continueTarget(home, blank()).page.id).toBe('a')
  })
  it('全部完成时回到第一个非首页章', () => {
    expect(continueTarget(home, fill(blank(), home.pages.flatMap((p) => p.ids))).page.id).toBe('a')
  })
  it('只有首页章时仍返回它', () => {
    expect(continueTarget({ ...home, pages: home.pages.slice(0, 1) }, blank()).page.id).toBe('h')
  })
})
