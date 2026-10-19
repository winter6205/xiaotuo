import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, getDashboard, getSnapshot, importState, resetProgress, type Dashboard as Data } from '../lib/api'
import { Dialog } from '../components/Dialog'
import { activityRows } from '../lib/activity'
import { courseById, courses, courseVars } from '../lib/courses'
import { levelPct } from '../lib/level'
import type { CourseCode, CourseState } from '../lib/state'
import { dropQueued } from '../lib/sync'

const icon = (code: string) => courseById(code)?.icon ?? ''
const n = (v: number) => v.toLocaleString('zh-CN')
const pct = (a: number, b: number) => `${b ? Math.min(100, (a / b) * 100) : 0}%`
const fmt = (iso: string) => new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(iso))

export function Dashboard() {
  const [d, setD] = useState<Data | null>(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [confirm, setConfirm] = useState<CourseCode | 'all' | null>(null)
  const trigger = useRef<HTMLButtonElement | null>(null) // 打开清空对话框的按钮，关闭后焦点返回
  const load = useCallback(() => getDashboard().then(setD, (e) => setErr(e instanceof ApiError ? e.message : '加载失败')), [])
  useEffect(() => { void load() }, [load])

  const exportCourse = async (code: CourseCode) => {
    const s = await getSnapshot(code)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([JSON.stringify(s, null, 2)], { type: 'application/json' }))
    a.download = `${courseById(code)?.key ?? code}.json`
    a.click()
    URL.revokeObjectURL(a.href)
  }
  const importFile = async (code: CourseCode, file?: File) => {
    if (!file) return
    try {
      const r = await importState(code, JSON.parse(await file.text()) as CourseState, crypto.randomUUID(), 'export_file')
      setMsg(`已导入：新增 ${r.items_added} 项，XP ${r.xp_before} → ${r.xp_after}${r.unknown_ids.length ? `，忽略 ${r.unknown_ids.length} 个未知题目` : ''}`)
      void load()
    } catch (e) { setMsg(e instanceof ApiError ? e.message : '文件不是有效的进度 JSON') }
  }

  if (err) return <main className="xt-main"><div className="xt-notice xt-notice--err"><span className="xt-notice-ic">⚠️</span><span>{err}</span></div></main>
  if (!d) return <main className="xt-main"><div className="xt-boot"><span className="xt-spinner" /> 正在载入学习中心…</div></main>
  const s = d.summary
  // 计分项口径（v0.3.1）：项数只算 max_xp > 0 的 scored_*，0 XP 跟踪项以 tracks_done 另显示
  const recNote = (k: { tracks_done: number }) => (k.tracks_done ? ` · 已勾选 ${k.tracks_done} 项记录` : '')
  const title = (code: string) => d.courses.find((c) => c.course === code)?.title ?? code
  const rows = activityRows(d.recent, d.last_import, title)
  return (
    <main className="xt-main">
      <div className="xt-sec-h"><div><h1 className="xt-h1">个人学习中心</h1><div className="xt-muted">{d.user.email} · {d.user.created_at.slice(0, 10)} 注册</div></div></div>
      <div className="xt-grid xt-grid--3">
        <div className="xt-stat xt-stat--xp"><div className="xt-stat-l">⭐ 全部课程总 XP</div><div className="xt-stat-v">{n(s.xp_total)} <small>/ {n(d.courses.reduce((a, c) => a + c.xp_max, 0))}</small></div></div>
        <div className="xt-stat xt-stat--fire"><div className="xt-stat-l">🔥 连学（各课合并计算）</div><div className="xt-stat-v">{s.streak_cur} <small>天</small></div><div className="xt-stat-s">最长 {s.streak_best} 天 · 共学习 {s.days_total} 天</div></div>
        <div className="xt-stat xt-stat--bd"><div className="xt-stat-l">🏅 徽章（各课合计）</div><div className="xt-stat-v">{s.badges_count} <small>/ {s.badges_total}</small></div></div>
      </div>

      <section className="xt-section"><div className="xt-sec-h"><h2 className="xt-h2">课程进度</h2></div>
        <div className="xt-grid xt-grid--2">
          {d.courses.map((c) => (
            <div className="xt-card" key={c.course}>
              <div className="xt-row xt-between"><h3 className="xt-h3">{icon(c.course)} {c.title} <span className="xt-muted xt-mono">{c.course}</span></h3><Link className="xt-btn xt-btn--sm" to={`/${c.course}`}>目录</Link></div>
              <div className="xt-lvrow"><span className="xt-pill xt-pill--lv">🎖️ Lv{c.level.level} · {c.level.level_name}</span>
                {c.level.next_level_xp !== null && <span className="xt-muted">{n(c.xp)} / {n(c.level.next_level_xp)} XP 升至 {c.level.next_level_name}</span>}</div>
              <div className="xt-bar xt-bar--xp xt-bar--sm xt-lvbar"><span style={{ width: levelPct(c.xp, c.level) }} /></div>
              <div className="xt-kv"><span>XP</span><b>{n(c.xp)} / {n(c.xp_max)}</b><span>完成项</span><b>{c.scored_done} / {c.scored_total}{recNote(c)}</b><span>连学</span><b>{c.streak_cur} 天 · 最长 {c.streak_best} · 共 {c.days_total} 天</b><span>徽章</span><b>{c.badges_count} / {c.badges_total}</b></div>
              <div className="xt-chapters" style={{ marginTop: 14 }}>
                {c.chapters.map((ch) => { const [dn, tt] = [ch.scored_done, ch.scored_total]; return (
                  <div key={ch.chapter_id} className={`xt-chapter${dn === tt ? ' xt-chapter--done' : ''}`}>
                    <span className="xt-chapter-no">{ch.chapter_id}</span>
                    <div><b>{ch.title}</b><div className="xt-chapter-meta"><div className="xt-bar xt-bar--sm"><span style={{ width: pct(dn, tt) }} /></div><span className="xt-muted">{dn}/{tt} 项 · {ch.xp}/{ch.xp_max} XP{recNote(ch)}</span></div></div>
                    {!ch.has_boss
                      ? <span className="xt-muted">本章无 Boss</span>
                      : <span className={`xt-boss${ch.boss_cleared ? ' xt-boss--clear' : ''}`}>👑 {ch.boss_cleared ? 'Boss 已通关' : 'Boss 未通关'}</span>}
                  </div>
                )})}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="xt-section"><div className="xt-sec-h"><h2 className="xt-h2">徽章</h2><span className="xt-muted">已获得 {d.badges.length} 枚</span></div>
        {/* 按课程分组（各课有「第一步」等同名徽章） */}
        {courses.filter((cc) => d.badges.some((b) => b.course === cc.id)).map((course) => { const cc = course.id; return (
          <div className="xt-badge-group" key={cc} data-course={cc} style={courseVars(course)}>
            <h3 className="xt-h3" style={{ margin: '4px 0 10px' }}>{course.title}</h3>
            <div className="xt-badges" style={{ marginBottom: 14 }}>
              {d.badges.filter((b) => b.course === cc).map((b) => <div className="xt-badge" key={b.course + b.badge_id} title={b.desc}><i>{b.icon}</i>{b.name}<small>{b.awarded_at}</small></div>)}
            </div>
          </div>
        )})}
        {s.badges_total > s.badges_count && <div className="xt-badges"><div className="xt-badge xt-badge--lock"><i>🔒</i>还有 {s.badges_total - s.badges_count} 枚<small>通关 Boss 等条件获得</small></div></div>}
      </section>

      <div className="xt-grid xt-grid--21 xt-section">
        <section><div className="xt-sec-h"><h2 className="xt-h2">最近活动</h2><span className="xt-muted">最近 20 条</span></div>
          <div className="xt-table-wrap"><table className="xt-table xt-table--act">
            <thead><tr><th>时间</th><th>课程</th><th>章 · 小页</th><th>题目</th><th>类型</th><th className="xt-num">XP</th></tr></thead>
            <tbody>{rows.length === 0 && <tr className="xt-empty"><td colSpan={6} className="xt-muted">暂无活动记录，去课程里做一道题吧。</td></tr>}{rows.map((r, i) => r.type === 'import' ? (
              <tr key={i} className="xt-act-import"><td className="xt-mono xt-act-at">{fmt(r.at)}</td><td className="xt-act-course">{r.course}</td><td className="xt-mono xt-act-page">—</td>
                <td className="xt-act-item" colSpan={2}>⬆️ {r.text}</td><td className="xt-num xt-act-amt">{r.xp ? `+${r.xp}` : '—'}</td></tr>
            ) : (
              <tr key={i}><td className="xt-mono xt-act-at">{fmt(r.at)}</td><td className="xt-act-course">{r.course}</td><td className="xt-mono xt-act-page">{r.chapter_id} · {r.page_id}</td>
                <td className="xt-mono xt-act-item">{r.item_id}</td><td className="xt-act-kind"><span className={`xt-kind xt-kind--${r.kind === 'done' || r.kind === 'rec' ? r.kind : 'xp'}`}>{r.kind}</span></td>
                <td className="xt-num xt-act-amt">{r.amt == null ? '—' : `+${r.amt}`}</td></tr>
            ))}</tbody>
          </table></div>
        </section>
        <section><div className="xt-sec-h"><h2 className="xt-h2">进度数据</h2></div>
          <div className="xt-card xt-stack">
            <p className="xt-p" style={{ margin: 0 }}>导出文件与教材页「导出进度」格式一致；导入时完成项与徽章取并集。</p>
            {d.courses.map((c) => (
              <div className="xt-datarow" key={c.course}><b>{icon(c.course)} {c.title}</b><div className="xt-row">
                <button className="xt-btn xt-btn--sm xt-btn--ghost" type="button" onClick={() => void exportCourse(c.course)}>⬇️ 导出进度</button>
                <label className="xt-btn xt-btn--sm xt-btn--ghost">⬆️ 导入进度<input type="file" accept=".json,application/json" hidden onChange={(e) => void importFile(c.course, e.target.files?.[0])} /></label>
              </div></div>
            ))}
            {msg && <div className="xt-notice xt-notice--ok" role="status"><span className="xt-notice-ic">✅</span><span>{msg}</span></div>}
            {d.last_import && <div className="xt-muted">上次导入：{fmt(d.last_import.imported_at)} · {d.last_import.course} · 新增 {d.last_import.items_added} 项 · XP +{d.last_import.xp_delta}</div>}
            <div className="xt-danger-zone">
              <div><b>危险操作</b><div className="xt-muted">清空后无法恢复，建议先导出。</div></div>
              <div className="xt-row">
                {d.courses.map((c) => <button key={c.course} className="xt-btn xt-btn--sm xt-btn--danger-ghost" type="button" onClick={(e) => { trigger.current = e.currentTarget; setConfirm(c.course) }}>清空 {c.title}</button>)}
                <button className="xt-btn xt-btn--sm xt-btn--danger" type="button" onClick={(e) => { trigger.current = e.currentTarget; setConfirm('all') }}>清空全部进度</button>
              </div>
            </div>
          </div>
        </section>
      </div>
      {confirm && <ResetDialog scope={confirm} returnFocus={() => trigger.current} onClose={(done) => { setConfirm(null); if (done) void load() }} />}
    </main>
  )
}

function ResetDialog({ scope, onClose, returnFocus }: { scope: CourseCode | 'all'; onClose: (done: boolean) => void; returnFocus: () => HTMLElement | null }) {
  const [v, setV] = useState('')
  const [err, setErr] = useState('')
  const phrase = `RESET ${scope}`
  const run = async () => {
    try {
      await resetProgress(scope)
      // 服务端清空后同步清除本机缓存，避免回写时把旧进度当作本地独有进度上报
      const codes = scope === 'all' ? courses.map((c) => c.id) : [scope]
      dropQueued(codes)
      for (const c of codes) { const k = courseById(c)?.key; if (k) localStorage.removeItem(k) }
      onClose(true)
    } catch (e) { setErr(e instanceof ApiError ? e.message : '清空失败') }
  }
  return (
    <Dialog id="xt-reset-dlg" labelledBy="dlg-h" icon="🗑️" onClose={() => onClose(false)} returnFocus={returnFocus}>
        <h3 className="xt-h3" id="dlg-h">{scope === 'all' ? '清空全部课程的进度？' : `清空 ${courseById(scope)?.name ?? scope} 的进度？`}</h3>
        <p className="xt-p">将删除账号中的完成记录、XP 与徽章，并清除本机缓存，无法恢复。</p>
        <div className="xt-field"><label className="xt-label" htmlFor="cf">输入 <span className="xt-mono">{phrase}</span> 以确认</label>
          <input className="xt-input" id="cf" value={v} onChange={(e) => setV(e.target.value)} autoComplete="off" aria-invalid={err ? true : undefined} />
          {err && <span className="xt-err">{err}</span>}</div>
        <div className="xt-row" style={{ justifyContent: 'flex-end', marginTop: 14 }}>
          <button className="xt-btn xt-btn--ghost xt-btn--sm" type="button" onClick={() => onClose(false)}>取消</button>
          <button className="xt-btn xt-btn--danger xt-btn--sm" type="button" disabled={v !== phrase} onClick={() => void run()}>确认清空</button>
        </div>
    </Dialog>
  )
}
