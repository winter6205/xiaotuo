import { Link, Navigate, useParams } from 'react-router-dom'
import { Crumb } from '../components/Dialog'
import { bossTarget, continueTarget, courseById, courseVars, progress, readerPath, units } from '../lib/courses'
import { parseState, totalXP } from '../lib/state'

const MARK = { done: '✓', part: '◐', todo: '' }

export function Toc() {
  const c = courseById(useParams().course)
  if (!c) return <Navigate to="/" replace />
  const s = parseState(localStorage.getItem(c.key))
  const xp = totalXP(s)
  const all = progress(s, c.pages.flatMap((p) => p.ids))
  const next = continueTarget(c, s)
  return (
    <main className="xt-main" data-course-root={c.id} style={courseVars(c)}>
      <div className="xt-crumbs"><Crumb><Link className="xt-link" to="/">选课</Link></Crumb> <Crumb>› {c.name}</Crumb> <Crumb>› 目录</Crumb></div>
      <section className="xt-hero">
        <div style={{ flex: 1, minWidth: 0 }}><span className="xt-kicker">{c.short} · {c.pages.length} 章</span><h1 className="xt-h1">{c.name}</h1>
          <div className="xt-grid xt-grid--3" style={{ marginTop: 12, gap: 12 }}>
            <div><div className="xt-row xt-between xt-muted"><span>本课 XP</span><b style={{ color: 'var(--ink)' }}>{xp} / {c.total}</b></div><div className="xt-bar xt-bar--xp"><span style={{ width: `${Math.min(100, (xp / c.total) * 100)}%` }} /></div></div>
            <div><div className="xt-row xt-between xt-muted"><span>完成项</span><b style={{ color: 'var(--ink)' }}>{all.done} / {all.total}</b></div><div className="xt-bar"><span style={{ width: `${all.total ? (all.done / all.total) * 100 : 0}%` }} /></div></div>
            <div className="xt-row"><Link className="xt-btn xt-continue" to={readerPath(c, next.unit.file)}>继续：{next.page.id} · {next.unit.title.replace(/（单页）$/, '')} →</Link></div>
          </div></div>
      </section>
      <div className="xt-row xt-between xt-section" style={{ marginTop: 22 }}><h2 className="xt-h2" style={{ margin: 0 }}>章节</h2><span className="xt-muted">✓ 已完成 ◐ 进行中</span></div>
      <div className="xt-stack" style={{ marginTop: 12 }}>
        {c.pages.map((p) => {
          const pr = progress(s, p.ids)
          const boss = bossTarget(p)
          const bossClear = !!(p.boss && s?.xp[`${p.boss}-clear`])
          return (
            <details key={p.id} className="xt-details" open={p.id === next.page.id}>
              <summary><div className="xt-chapter" style={{ border: 0, boxShadow: 'none', padding: 0, background: 'none' }}>
                <span className="xt-chapter-no">{p.id}</span>
                <div><b>{p.title.replace(/^\S+ · /, '')}</b><div className="xt-chapter-meta"><div className="xt-bar xt-bar--sm"><span style={{ width: `${pr.total ? (pr.done / pr.total) * 100 : 0}%` }} /></div><span className="xt-muted">{pr.done} / {pr.total} 项 · 满分 {p.xp} XP</span></div></div>
                {p.boss ? <span className={`xt-boss${bossClear ? ' xt-boss--clear' : ''}`}>👑 {bossClear ? '已通关' : 'Boss'}</span> : <span className="xt-muted">本章无 Boss</span>}
              </div></summary>
              <div className="xt-details-b">
                <ul className="xt-subs">
                  {units(p).map((u) => {
                    const up = progress(s, u.ids)
                    const cur = u.file === next.unit.file
                    return (
                      <li key={u.key}><Link className={`xt-sub xt-sub--${up.status}${cur ? ' xt-sub--cur' : ''}`} to={readerPath(c, u.file)} data-status={up.status}>
                        <span className="xt-sub-st">{MARK[up.status]}</span><span>{u.title}</span>
                        <span className="xt-sub-r">{up.total ? `${up.done}/${up.total}` : '—'}<span className="xt-lbl"> 项</span></span>
                      </Link></li>
                    )
                  })}
                </ul>
                {boss && (
                  <Link className="xt-boss-cta" to={readerPath(c, boss.file, boss.hash)} style={{ color: 'var(--ink)', textDecoration: 'none' }}>
                    <span className="xt-crown">👑</span><div style={{ flex: 1 }}><b>{boss.title.replace(/^👑\s*/, '')}</b><div className="xt-muted">{progress(s, boss.ids).done} / {boss.ids.length} 项{bossClear ? ' · 已通关' : ''}</div></div>
                    <span className="xt-btn xt-btn--sm">{bossClear ? '再挑战' : '挑战'}</span>
                  </Link>
                )}
              </div>
            </details>
          )
        })}
      </div>
    </main>
  )
}
