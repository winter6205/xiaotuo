// 登录态：GET /api/me 结果的全局订阅；登录成功后触发首次导入与同步
import { useSyncExternalStore } from 'react'
import { getMe, login as apiLogin, register as apiRegister, revokeSession, subscribeUnauthorized, type Me } from './api'
import { clearCourseLocal, markOwner, ownerDecision, readOwner } from './owner'
import { drain, importLocalOnce, pendingCount, setOwner } from './sync'

const PENDING_LOGOUT = 'xt-pending-logout' // 离线退出后待补发的注销；存在期间绝不自动恢复登录

let me: Me | null = null
let loaded = false
const subs = new Set<() => void>()
const set = (m: Me | null) => { me = m; loaded = true; setOwner(m?.user?.id ?? null); subs.forEach((f) => f()) }
const signedOut = () => set(me ? { ...me, user: null } : null)

export const useSession = () => useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f) } }, () => (loaded ? me : undefined))

/** 补发注销：成功（204/401）清标记返回 true；失败保留标记 */
async function settlePendingLogout(): Promise<boolean> {
  if (!localStorage.getItem(PENDING_LOGOUT)) return true
  if (!(await revokeSession())) return false
  localStorage.removeItem(PENDING_LOGOUT)
  return true
}

/** 启动/联网时调用：先补发注销，再 GET /api/me */
export async function loadSession() {
  if (!(await settlePendingLogout())) return signedOut()
  try {
    const m = await getMe()
    if (m.user) await claimLocal(m.user.id)
    set(m)
  } catch { set(null) } // 后端不可达时按未登录处理，进度仍写本机
}
subscribeUnauthorized(() => { if (me?.user) signedOut() })
window.addEventListener('online', () => { if (localStorage.getItem(PENDING_LOGOUT)) void loadSession() })

/** 本机课程进度归属：匿名进度首次导入；其他账号的进度直接清掉（随后由快照回写）；最后标记为当前账号 */
async function claimLocal(uid: number) {
  const d = ownerDecision(readOwner(), uid)
  if (d === 'other') clearCourseLocal()
  else if (d === 'anon') await importLocalOnce(uid).catch((e) => console.warn('[import] 首次导入失败，下次登录重试', e))
  markOwner(uid)
}

async function enter(m: Me) {
  localStorage.removeItem(PENDING_LOGOUT) // 登录会轮换会话，旧会话随之作废
  if (m.user) await claimLocal(m.user.id)
  set(m)
}
async function auth(fn: typeof apiLogin, email: string, pw: string) {
  await settlePendingLogout()
  return enter(await fn(email, pw))
}
export const login = (email: string, pw: string) => auth(apiLogin, email, pw)
export const register = (email: string, pw: string) => auth(apiRegister, email, pw)

/** 退出：先上报当前账号队列；仍有残留且未 force 时返回条数交由界面确认（不丢弃，队列保留在本机）。
 *  队列已同步完才清本机课程进度；注销请求失败（离线等）记标记，下次启动/联网补发，界面立即进入未登录。 */
export async function logout(force = false): Promise<number> {
  if (!force) { const left = await drain(); if (left) return left }
  const synced = pendingCount() === 0
  if (!(await revokeSession())) localStorage.setItem(PENDING_LOGOUT, '1')
  if (synced) clearCourseLocal()
  signedOut()
  return 0
}
