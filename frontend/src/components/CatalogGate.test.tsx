// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { resetCourses, type Course } from '../lib/courses'
import { CatalogGate } from './CatalogGate'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const mk = (id: string): Course => ({
  id, dir: id, key: `${id}-v1`, title: id, name: id, short: id, icon: '📘', order: 1, accent: '#336699', accentLight: null, accentDark: null,
  stateVersion: 1, courseId: null, engine: 'static', homeChapter: null, graduation: null, generated: null, total: 0, anchors: {}, pages: [],
})
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const flush = () => act(async () => { for (let i = 0; i < 5; i++) await Promise.resolve() })

let host: HTMLDivElement, root: Root, fetchMock: ReturnType<typeof vi.fn>
beforeEach(() => {
  resetCourses(); fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock)
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals() })

const render = () => act(() => { root.render(<CatalogGate><p id="routes">路由</p></CatalogGate>) })

describe('课程目录加载闸门', () => {
  it('加载中显示 role=status，成功后才渲染子树', async () => {
    let resolve!: (r: Response) => void
    fetchMock.mockReturnValueOnce(new Promise<Response>((r) => { resolve = r }))
    render()
    expect(host.querySelector('[role=status]')?.textContent).toContain('正在加载')
    expect(host.querySelector('#routes')).toBeNull()
    resolve(json(200, { version: 'v', courses: [mk('alpha')] }))
    await flush()
    expect(host.querySelector('#routes')).not.toBeNull()
    expect(host.querySelector('[data-catalog]')).toBeNull()
  })
  it('失败显示 role=alert 与重试按钮，焦点移到标题；重试成功后放行', async () => {
    fetchMock.mockResolvedValueOnce(json(503, { code: 'catalog_unavailable', message: 'x' }))
    fetchMock.mockResolvedValueOnce(json(200, { version: 'v', courses: [mk('alpha')] }))
    render(); await flush()
    expect(host.querySelector('[role=alert]')?.textContent).toContain('课程目录暂不可用')
    expect(document.activeElement?.textContent).toBe('课程目录加载失败')
    expect(host.querySelector('#routes')).toBeNull()
    const btn = [...host.querySelectorAll('button')].find((b) => b.textContent === '重试')!
    await act(async () => { btn.click() })
    await flush()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(host.querySelector('#routes')).not.toBeNull()
  })
  it('空列表显示空状态，不渲染路由；重新检查会重新请求', async () => {
    fetchMock.mockResolvedValueOnce(json(200, { version: 'e', courses: [] }))
    fetchMock.mockResolvedValueOnce(json(200, { version: 'f', courses: [mk('alpha')] }))
    render(); await flush()
    expect(host.querySelector('[data-catalog=empty]')).not.toBeNull()
    expect(document.activeElement?.textContent).toBe('还没有课程')
    expect(host.querySelector('[data-catalog=empty] [role=status]')?.textContent).toContain('指定的课程目录里没有发现任何课程')
    expect(host.querySelector('#routes')).toBeNull()
    const btn = [...host.querySelectorAll('button')].find((b) => b.textContent === '重新检查')!
    await act(async () => { btn.click() })
    await flush()
    expect(host.querySelector('#routes')).not.toBeNull()
  })
})
