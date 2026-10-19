import { useEffect, useState } from 'react'
import { Link, Navigate, useLocation, useParams } from 'react-router-dom'
import { CourseFrame } from '../components/CourseFrame'
import { Crumb } from '../components/Dialog'
import { useDrawer } from '../components/Layout'
import { bossTarget, continueTarget, courseById, courseVars, locate, progress, readerPath, resolveAnchor, units } from '../lib/courses'
import { parseState } from '../lib/state'
import { writeBack } from '../lib/sync'

export function Reader() {
  const { course, file = '' } = useParams()
  const { hash } = useLocation()
  const c = courseById(course)
  const { open, setOpen, setEnabled } = useDrawer()
  const close = () => { setOpen(false); document.getElementById('xt-menu')?.focus() }
  useEffect(() => { setEnabled(true); return () => { setEnabled(false); setOpen(false) } }, [setEnabled, setOpen])
  const [synced, setSynced] = useState<string | null>(null) // 已完成回写的课程

  // 进入课程时先把服务端快照写回本机，再加载 iframe；失败（离线等）时沿用本机进度
  useEffect(() => {
    if (!c) return
    let alive = true
    writeBack(c.id).catch((e) => console.warn('[writeBack]', e)).finally(() => { if (alive) setSynced(c.id) })
    return () => { alive = false }
  }, [c])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  if (!c) return <Navigate to="/" replace />
  const r = resolveAnchor(c, file, decodeURIComponent(hash.slice(1)))
  if (r.file !== file) return <Navigate to={`/${c.id}/${encodeURIComponent(r.file)}#${r.hash}`} replace />
  const { page, sub } = locate(c, file)
  const s = synced === c.id ? parseState(localStorage.getItem(c.key)) : null
  const next = continueTarget(c, s)
  const tick = (ids: string[]) => s && progress(s, ids).status === 'done' && <span className="xt-tick">✓</span>

  return (
    <>
      <div className="xt-reader" data-course-root={c.id} style={courseVars(c)}>
        <div className="xt-scrim" hidden={!open} onClick={close} />
        <nav className="xt-toc" id="xt-toc" aria-label="课程目录" data-open={open || undefined}>
          <span className="xt-toc-h">{page?.title ?? c.name}</span>
          <Link className="xt-toc-a" to={`/${c.id}`} onClick={close}>📚 课程目录</Link>
          {next.unit.file !== file && <Link className="xt-toc-a xt-continue" to={readerPath(c, next.unit.file)} onClick={close}>▶ 继续学习：{next.page.id} · {next.unit.title.replace(/（单页）$/, '')}</Link>}
          {page && (
            <div className="xt-toc-sub">
              {units(page).map((u) => (
                <Link key={u.key} className="xt-toc-a" to={readerPath(c, u.file)} aria-current={u.file === file ? 'page' : undefined} onClick={close}>{u.title}{tick(u.ids)}</Link>
              ))}
              {(() => { const b = bossTarget(page); return b && <Link className="xt-toc-a" to={readerPath(c, b.file, b.hash)} aria-current={b.file === file && sub?.boss ? 'page' : undefined} onClick={close}>{b.title.startsWith('👑') ? b.title : `👑 ${b.title}`}{s?.xp[`${page.boss}-clear`] && <span className="xt-tick">✓</span>}</Link> })()}
              {!page.boss && <span className="xt-muted" style={{ display: 'block', padding: '4px 10px', fontSize: 13 }}>本章无 Boss</span>}
            </div>
          )}
          <hr />
          {c.pages.filter((p) => p !== page).map((p) => (
            <Link key={p.id} className="xt-toc-a" to={readerPath(c, p.file)} onClick={close}>{p.title}{tick(p.ids)}</Link>
          ))}
        </nav>
        <div style={{ minWidth: 0 }}>
          <div className="xt-crumbs"><Crumb><Link className="xt-link" to={`/${c.id}`}>{c.name}</Link></Crumb> <Crumb>› {page?.title ?? file}</Crumb>{sub && <> <Crumb>› {sub.title}</Crumb></>}</div>
          <div className="xt-frame-box">
            {synced === c.id ? <CourseFrame course={c} file={file} hash={r.hash} /> : <div className="xt-frame-loading">正在同步进度…</div>}
          </div>
        </div>
      </div>
    </>
  )
}
