import { Link } from 'react-router-dom'
import { courses, courseVars } from '../lib/courses'
import { parseState, totalXP } from '../lib/state'

export function Home() {
  return (
    <main className="xt-main">
      <section className="xt-hero">
        <div className="xt-mascot" aria-hidden="true">🦙</div>
        <div><span className="xt-kicker">在线学习</span><h1 className="xt-h1">选一门课，继续学习</h1>
          <p className="xt-p">多门课并列，进度分别记录；XP、连学天数与徽章汇总到同一个账号。</p></div>
      </section>
      <div className="xt-grid xt-grid--2 xt-section">
        {courses.map((c, i) => {
          const xp = totalXP(parseState(localStorage.getItem(c.key)))
          return (
            <article key={c.id} className="xt-course" data-course={c.id} style={courseVars(c)}>
              {i === 0 && <span className="xt-badge-default">默认入口</span>}
              <div className="xt-course-h"><div className="xt-course-ic" aria-hidden="true">{c.icon}</div>
                <div><h2 className="xt-h2" style={{ margin: 0 }}>{c.name}</h2><div className="xt-muted">{c.pages.length} 章 · 课程总分 {c.total} XP</div></div></div>
              <div><div className="xt-row xt-between xt-muted"><span>本课进度</span><b style={{ color: 'var(--ink)' }}>{xp} / {c.total} XP</b></div>
                <div className="xt-bar xt-bar--xp"><span style={{ width: `${Math.min(100, (xp / c.total) * 100)}%` }} /></div></div>
              <div className="xt-course-f"><span /><Link className={`xt-btn${i ? ' xt-btn--ghost' : ''}`} to={`/${c.id}`}>进入课程 →</Link></div>
            </article>
          )
        })}
      </div>
    </main>
  )
}
