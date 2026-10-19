import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CatalogError, catalogVersion, courseById, courseByKey, courses, getCourses, loadCourses, resetCourses, type Course } from './courses'

// 合成课程（与任何真实课程无关）
const mk = (id: string, order: number): Course => ({
  id, dir: id, key: `${id}-v1`, title: id, name: id, short: id, icon: '📘', order, accent: '#336699', accentLight: null, accentDark: null,
  stateVersion: 1, courseId: null, engine: 'static', homeChapter: null, graduation: null, generated: null, total: 0, anchors: {}, pages: [],
})
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

let fetchMock: ReturnType<typeof vi.fn>
beforeEach(() => { resetCourses(); fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock) })
afterEach(() => { vi.unstubAllGlobals() })

describe('GET /api/courses 运行时目录', () => {
  it('加载成功：按 order、id 排序，同步 getter 与活绑定可用，版本号记录', async () => {
    fetchMock.mockResolvedValueOnce(json(200, { version: 'v1', courses: [mk('beta', 2), mk('alpha', 1), mk('aaa', 2)] }))
    expect(getCourses()).toEqual([])
    const list = await loadCourses()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/courses$/)
    expect(list.map((c) => c.id)).toEqual(['alpha', 'aaa', 'beta'])
    expect(courses.map((c) => c.id)).toEqual(['alpha', 'aaa', 'beta'])
    expect(courseById('beta')?.order).toBe(2)
    expect(courseByKey('alpha-v1')?.id).toBe('alpha')
    expect(catalogVersion()).toBe('v1')
  })
  it('模块级缓存：并发与重复调用只请求一次', async () => {
    fetchMock.mockResolvedValue(json(200, { version: 'v1', courses: [mk('alpha', 1)] }))
    await Promise.all([loadCourses(), loadCourses()])
    await loadCourses()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
  it('失败后重试：503 抛 CatalogError，再次调用重新请求并成功', async () => {
    fetchMock.mockResolvedValueOnce(json(503, { code: 'catalog_unavailable', message: '课程目录不可用' }))
    fetchMock.mockResolvedValueOnce(json(200, { version: 'v2', courses: [mk('alpha', 1)] }))
    const err = await loadCourses().catch((e) => e)
    expect(err).toBeInstanceOf(CatalogError)
    expect(err.status).toBe(503)
    expect(err.code).toBe('catalog_unavailable')
    expect(getCourses()).toEqual([])
    expect((await loadCourses()).map((c) => c.id)).toEqual(['alpha'])
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
  it('网络错误为 status 0', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('fetch failed'))
    const err = await loadCourses().catch((e) => e)
    expect(err).toBeInstanceOf(CatalogError)
    expect(err.status).toBe(0)
  })
  it('响应格式不对时报错，不写入缓存', async () => {
    fetchMock.mockResolvedValueOnce(json(200, { nope: true }))
    await expect(loadCourses()).rejects.toMatchObject({ code: 'bad_response' })
    expect(getCourses()).toEqual([])
  })
  it('空列表：加载成功、courses 为空；force 重新请求', async () => {
    fetchMock.mockResolvedValueOnce(json(200, { version: 'e', courses: [] }))
    fetchMock.mockResolvedValueOnce(json(200, { version: 'f', courses: [mk('alpha', 1)] }))
    expect(await loadCourses()).toEqual([])
    expect(await loadCourses()).toEqual([])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect((await loadCourses(true)).map((c) => c.id)).toEqual(['alpha'])
  })
})
