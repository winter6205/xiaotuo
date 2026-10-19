import { useEffect, type ReactNode } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { CatalogGate } from './components/CatalogGate'
import { RequireAuth } from './components/RequireAuth'
import { Layout } from './components/Layout'
import { loadSession } from './lib/session'
import { startSync } from './lib/sync'
import { Login, Register, Reset } from './pages/Auth'
import { Dashboard } from './pages/Dashboard'
import { Home } from './pages/Home'
import { Reader } from './pages/Reader'
import { Toc } from './pages/Toc'

const Private = ({ children }: { children: ReactNode }) => <RequireAuth>{children}</RequireAuth>

/** 课程目录加载闸门放行后才渲染路由；同步与会话随之启动（sync/owner 依赖已载入的目录） */
export default function App() {
  return <CatalogGate><Routed /></CatalogGate>
}

function Routed() {
  useEffect(() => { void loadSession(); return startSync() }, [])
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/reset" element={<Reset />} />
          <Route path="/" element={<Home />} />
          <Route path="/dashboard" element={<Private><Dashboard /></Private>} />
          <Route path="/:course" element={<Private><Toc /></Private>} />
          <Route path="/:course/:file" element={<Private><Reader /></Private>} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
