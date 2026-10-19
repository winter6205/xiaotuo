import { createContext, useContext, useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { TopBar } from './TopBar'

// 顶栏常驻于布局层（路由切换、登出重定向时不重建）；Reader 通过 context 启用目录抽屉按钮
interface Drawer { open: boolean; setOpen: (v: boolean | ((o: boolean) => boolean)) => void; setEnabled: (v: boolean) => void }
const DrawerCtx = createContext<Drawer | null>(null)
export const useDrawer = () => useContext(DrawerCtx)!

export function Layout() {
  const [enabled, setEnabled] = useState(false)
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  useEffect(() => setOpen(false), [pathname]) // 路由变化（含浏览器后退）关闭目录抽屉
  return (
    <DrawerCtx.Provider value={{ open, setOpen, setEnabled }}>
      <TopBar menu={enabled ? { open, toggle: () => setOpen((v) => !v) } : undefined} />
      <Outlet />
    </DrawerCtx.Provider>
  )
}
