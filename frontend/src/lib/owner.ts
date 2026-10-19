// 课程本地进度（各课清单的 storage_key，iframe 与外壳同源共享）的账号归属，记在 xt-owner
import { getCourses } from './courses'

const OWNER = 'xt-owner'
export type OwnerDecision = 'anon' | 'same' | 'other'

/** 无归属 → anon（可首次导入）；同账号 → same；其他账号 → other（不上报、不导入，清掉后从快照回写） */
export const ownerDecision = (mark: string | null, uid: number): OwnerDecision =>
  mark == null || mark === '' ? 'anon' : mark === String(uid) ? 'same' : 'other'

export const readOwner = () => localStorage.getItem(OWNER)
export const markOwner = (uid: number) => localStorage.setItem(OWNER, String(uid))

/** 清除本机课程进度与归属标记 */
export function clearCourseLocal() {
  // 惰性读取：目录由加载闸门在渲染前载入，这里不在模块顶层拷贝
  for (const c of getCourses()) localStorage.removeItem(c.key)
  localStorage.removeItem(OWNER)
}
