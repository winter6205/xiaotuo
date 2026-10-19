import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useSession } from '../lib/session'

/** 未登录跳转登录页，登录后回到原地址（next） */
export function RequireAuth({ children }: { children: ReactNode }) {
  const me = useSession()
  const loc = useLocation()
  if (me === undefined) return <div className="xt-boot"><span className="xt-spinner" /> 正在连接服务…</div>
  if (!me?.user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search + loc.hash)}`} replace />
  return children
}
