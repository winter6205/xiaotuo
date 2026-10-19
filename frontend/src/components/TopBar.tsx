import { useRef, useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { logout, useSession } from '../lib/session'
import { Dialog } from './Dialog'
import { SyncBadge } from './SyncBadge'

interface Props { menu?: { open: boolean; toggle: () => void } }

export function TopBar({ menu }: Props) {
  const me = useSession()
  const [left, setLeft] = useState(0)
  const logoutBtn = useRef<HTMLButtonElement>(null) // 对话框关闭后焦点返回处（不依赖 activeElement）
  const [busy, setBusy] = useState(false)
  const loggedOut = useRef(false) // 已退出：「退出」按钮随登录态切换被卸载，不能再作为焦点返回目标
  const doLogout = async (force = false) => {
    setBusy(true)
    try {
      const n = await logout(force)
      loggedOut.current = n === 0
      setLeft(n)
    } finally { setBusy(false) }
  }
  return (
    <header className="xt-top">
      {menu && (
        <button className="xt-pill xt-menu" id="xt-menu" type="button" aria-label="打开目录" aria-controls="xt-toc" aria-expanded={menu.open} onClick={menu.toggle}>☰</button>
      )}
      <Link className="xt-logo" to="/" id="xt-home"><i>🦙</i><span>小驼</span></Link>
      <nav className="xt-nav" aria-label="主导航">
        <NavLink to="/" end>选课</NavLink>
        <NavLink to="/dashboard" id="xt-account">学习中心</NavLink>
      </nav>
      <span className="xt-top-sp" />
      {me === undefined ? (
        // 会话未知（冷启动等 /api/me）：等宽隐形占位，避免已登录用户看到「登录/注册」闪烁及布局跳动
        <span className="xt-row" aria-hidden="true" style={{ visibility: 'hidden' }} id="xt-auth-ph">
          <span className="xt-btn xt-btn--ghost xt-btn--sm">登录</span><span className="xt-btn xt-btn--sm">注册</span>
        </span>
      ) : me?.user ? (
        <>
          <SyncBadge />
          <button className="xt-btn xt-btn--ghost xt-btn--sm" type="button" onClick={() => { loggedOut.current = false; void doLogout() }} disabled={busy} id="xt-logout" ref={logoutBtn}>退出</button>
        </>
      ) : (
        <>
          <Link className="xt-btn xt-btn--ghost xt-btn--sm" to="/login">登录</Link>
          <Link className="xt-btn xt-btn--sm" to="/register">注册</Link>
        </>
      )}
      {left > 0 && (
        <Dialog id="xt-logout-dlg" labelledBy="lo-h" icon="⚠️" iconBg="var(--yellow-l)" onClose={() => setLeft(0)} returnFocus={() => (loggedOut.current ? null : logoutBtn.current)}>
          <h3 className="xt-h3" id="lo-h">还有 {left} 条进度未同步</h3>
          <p className="xt-p">可以重试上报；也可以仍然退出，这些进度会保留在本机，下次登录该账号时继续同步。</p>
          <div className="xt-row" style={{ justifyContent: 'flex-end', marginTop: 14 }}>
            <button className="xt-btn xt-btn--ghost xt-btn--sm" type="button" onClick={() => setLeft(0)}>取消</button>
            <button className="xt-btn xt-btn--ghost xt-btn--sm" type="button" disabled={busy} onClick={() => void doLogout()}>重试</button>
            <button className="xt-btn xt-btn--danger xt-btn--sm" type="button" disabled={busy} onClick={() => void doLogout(true)}>仍然退出</button>
          </div>
        </Dialog>
      )}
    </header>
  )
}
