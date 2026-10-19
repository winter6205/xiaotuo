// 真实接口（OpenAPI v0.2.0，api/openapi.yaml）：同源 + Cookie 会话；写请求带 X-CSRF-Token
import type { components } from './api-types'
import type { CourseCode, CourseState, ProgressEvent } from './state'

type S = components['schemas']
export type Me = S['Me']
export type Dashboard = S['Dashboard']
export type ErrorCode = S['Error']['code']

/** 错误分类：status 决定处理方式（401 跳登录、409/400 表单提示、413 拆批、429 按 retryAfter、503 冷启动/功能关闭） */
export class ApiError extends Error {
  status: number
  code: ErrorCode | 'network'
  retryAfter: number
  details?: Record<string, unknown>
  constructor(status: number, code: ErrorCode | 'network', message: string, retryAfter = 0, details?: Record<string, unknown>) {
    super(message)
    this.status = status; this.code = code; this.retryAfter = retryAfter; this.details = details
  }
  /** 重试无意义的错误（队列应丢弃或改走其它路径），其余（网络/429/5xx）交给重试 */
  /** 字段校验错误（400 或 422，均按 details.fields 处理）：返回 字段名 → 提示 */
  get fields(): Record<string, string> | null {
    if (this.status !== 400 && this.status !== 422) return null
    const list = (this.details?.fields ?? []) as { loc: (string | number)[]; msg: string }[]
    return list.length ? Object.fromEntries(list.map((f) => [String(f.loc.at(-1)), f.msg])) : null
  }
  get permanent() { return [400, 404, 413, 422].includes(this.status) }
}

const BASE = `${import.meta.env.BASE_URL}api`
let csrf = ''
let me: Me | null = null
const onUnauthorized = new Set<() => void>()
export const subscribeUnauthorized = (f: () => void) => { onUnauthorized.add(f); return () => { onUnauthorized.delete(f) } }

async function request<T>(method: string, path: string, body?: unknown, headers: Record<string, string> = {}, retried = false): Promise<T> {
  if (method !== 'GET' && !csrf) await getMe()
  let res: Response
  try {
    res = await fetch(BASE + path, {
      method, credentials: 'include',
      headers: { ...(body !== undefined && { 'Content-Type': 'application/json' }), ...(method !== 'GET' && { 'X-CSRF-Token': csrf }), ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'network', '网络不可用')
  }
  if (res.ok) return (res.status === 204 ? undefined : await res.json()) as T
  const err = await res.json().catch(() => ({ code: 'internal_error', message: '服务器出错了，请稍后再试' }))
  // CSRF 失效：按契约重新 GET /api/me 后重试一次
  if (res.status === 403 && err.code === 'csrf_failed' && !retried) { await getMe(); return request(method, path, body, headers, true) }
  if (res.status === 401) { me = me && { ...me, user: null }; onUnauthorized.forEach((f) => f()) }
  throw new ApiError(res.status, err.code, err.message, Number(res.headers.get('Retry-After')) || 0, err.details)
}

export async function getMe(): Promise<Me> {
  me = await request<Me>('GET', '/me')
  csrf = me.csrf_token
  return me
}
export const cachedMe = () => me

async function auth(path: string, email: string, password: string): Promise<Me> {
  me = await request<Me>('POST', path, { email, password })
  csrf = me.csrf_token // 登录/注册会轮换会话与 CSRF
  return me
}
export const register = (email: string, password: string) => auth('/auth/register', email, password)
export const login = (email: string, password: string) => auth('/auth/login', email, password)

export type LogoutOutcome = 'done' | 'csrf' | 'keep'
/** 注销响应分类：204/401 视为会话已作废；403 需取 CSRF 后重试；网络错误(0)/5xx/其他保留待补发 */
export const classifyLogout = (status: number): LogoutOutcome =>
  status === 204 || status === 401 ? 'done' : status === 403 ? 'csrf' : 'keep'

/** 注销服务端会话（补发用）。只用原始请求：取 CSRF 时不更新登录态缓存，避免自动恢复登录。返回是否已作废。 */
export async function revokeSession(): Promise<boolean> {
  const post = () => fetch(`${BASE}/auth/logout`, { method: 'POST', credentials: 'include', headers: { 'X-CSRF-Token': csrf } }).then((r) => r.status, () => 0)
  let out = classifyLogout(await post())
  if (out === 'csrf') {
    const token = await fetch(`${BASE}/me`, { credentials: 'include' }).then((r) => (r.ok ? r.json() : null), () => null)
    if (!token?.csrf_token) return false
    csrf = token.csrf_token
    out = classifyLogout(await post())
  }
  if (out === 'done') { csrf = ''; me = null }
  return out === 'done'
}
export const requestPasswordReset = (email: string) => request<S['Message']>('POST', '/auth/password-reset/request', { email })
export const confirmPasswordReset = (token: string, new_password: string) => request<void>('POST', '/auth/password-reset/confirm', { token, new_password })

export async function postEvents(course: CourseCode, events: ProgressEvent[]): Promise<S['EventsResult']> {
  return request('POST', `/progress/${course}/events`, { events })
}

/** GET /api/progress/{course}：返回与 blank() 同构的 state */
export async function getSnapshot(course: CourseCode): Promise<CourseState | null> {
  const r = await request<S['ProgressSnapshot']>('GET', `/progress/${course}`)
  return r.state as unknown as CourseState
}

/** POST /api/progress/{course}/import：并集合并；Idempotency-Key 相同的重复请求返回首次结果 */
export function importState(course: CourseCode, state: CourseState, idempotencyKey: string, source: 'local_first_login' | 'export_file' = 'local_first_login') {
  return request<S['ImportResult']>('POST', `/progress/${course}/import`, { source, state }, { 'Idempotency-Key': idempotencyKey })
}

/** 学习中心；tz 为学员浏览器 IANA 时区（v0.2.1，非法时区返回 400） */
export function getDashboard(): Promise<Dashboard> {
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
  return request('GET', `/dashboard?tz=${encodeURIComponent(tz)}`)
}

export const resetProgress = (scope: CourseCode | 'all') => request<unknown>('POST', `/progress/${scope}/reset`, { confirm: `RESET ${scope}` })
