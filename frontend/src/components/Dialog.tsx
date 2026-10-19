import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

interface Props {
  id?: string; labelledBy: string; icon: ReactNode; iconBg?: string; onClose: () => void; children: ReactNode
  /** 关闭后焦点返回的元素（打开时记下的触发按钮）；缺省为打开时的焦点元素 */
  returnFocus?: () => HTMLElement | null
}

const FOCUSABLE = 'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
const focusables = (box: HTMLElement) =>
  [...box.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((e) => !(e as HTMLButtonElement).disabled && e.offsetParent !== null)

const usable = (el: HTMLElement | null): el is HTMLElement =>
  !!el && el.isConnected && !(el as HTMLButtonElement).disabled && (el.getClientRects().length > 0 || el.offsetParent !== null)

/** 焦点返回：依次尝试 触发按钮 → 顶栏账号入口 #xt-account → 顶栏 logo #xt-home，取第一个确实获得焦点的 */
export function restoreFocus(trigger: HTMLElement | null) {
  for (const el of [trigger, document.getElementById('xt-account'), document.getElementById('xt-home')]) {
    if (!usable(el)) continue
    el.focus()
    if (document.activeElement === el) return
  }
}

/** 模态确认框：挂到 body，背景 #root 设 inert 并锁定滚动；Tab 在框内循环；Esc / 点遮罩关闭；关闭后焦点回到触发元素 */
export function Dialog({ id, labelledBy, icon, iconBg, onClose, children, returnFocus }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const close = useRef(onClose)
  const back = useRef(returnFocus)
  useEffect(() => { close.current = onClose; back.current = returnFocus })

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    const root = document.getElementById('root')
    const overflow = document.body.style.overflow
    root?.setAttribute('inert', '')
    document.body.style.overflow = 'hidden'
    if (box.current) focusables(box.current)[0]?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { close.current(); return }
      if (e.key !== 'Tab' || !box.current) return
      const list = focusables(box.current)
      if (!list.length) return e.preventDefault()
      const i = list.indexOf(document.activeElement as HTMLElement)
      const next = e.shiftKey ? (i <= 0 ? list.length - 1 : i - 1) : (i === list.length - 1 ? 0 : i + 1)
      e.preventDefault()
      list[next].focus()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      root?.removeAttribute('inert')
      document.body.style.overflow = overflow
      restoreFocus(back.current?.() ?? opener)
    }
  }, [])

  return createPortal(
    <div className="xt-scrim" onClick={onClose} style={{ display: 'grid', placeItems: 'center', zIndex: 70 }}>
      <div className="xt-dialog" role="alertdialog" aria-modal="true" aria-labelledby={labelledBy} id={id} ref={box} onClick={(e) => e.stopPropagation()}>
        <div className="xt-dialog-ic" aria-hidden="true" style={iconBg ? { background: iconBg } : undefined}>{icon}</div>
        {children}
      </div>
    </div>,
    document.body,
  )
}

export const Crumb = ({ children }: { children: ReactNode }) => <span style={{ whiteSpace: 'nowrap' }}>{children}</span>
