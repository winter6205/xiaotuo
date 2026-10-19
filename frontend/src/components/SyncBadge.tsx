import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { flush, pendingCount, subscribe, type SyncStatus } from '../lib/sync'

// 冷启动「正在唤醒服务」留到 M7；内部状态 → 样式稿 .xt-sync-- 修饰类与文案
const VIEW: Record<SyncStatus, [string, string]> = {
  idle: ['synced', '已同步'], pending: ['syncing', '待同步'], syncing: ['syncing', '同步中'],
  offline: ['offline', '离线'], error: ['failed', '同步失败，自动重试中'], 'gave-up': ['failed', '重试达到上限'],
  expired: ['expired', '登录已过期'],
}
const SYNCING_DELAY = 1000 // 同步中持续不足 1 秒不显示

export function SyncBadge() {
  const [s, setS] = useState<SyncStatus>('idle')
  const [shown, setShown] = useState<SyncStatus>('idle')
  const [expired, setExpired] = useState(0)
  useEffect(() => subscribe((st, ex) => { setS(st); setExpired(ex) }), [])
  useEffect(() => {
    if (s !== 'syncing') { setShown(s); return }
    const t = setTimeout(() => setShown('syncing'), SYNCING_DELAY)
    return () => clearTimeout(t)
  }, [s])
  const [cls, label] = VIEW[shown]
  return (
    <span className={`xt-sync xt-sync--${cls}`} role="status" title="同步状态">
      <span className="xt-sync-dot" />
      <span className="xt-lbl">{label}{shown === 'offline' && ` · ${pendingCount()} 条待同步`}{expired > 0 && ' · 已合并较早的离线进度'}</span>
      {shown === 'gave-up' && <button className="xt-btn xt-btn--sm" type="button" onClick={() => void flush()}>手动重试</button>}
      {shown === 'expired' && <Link className="xt-link" to="/login">重新登录</Link>}
    </span>
  )
}
