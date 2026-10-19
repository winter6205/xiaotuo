import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { pageUrl, type Course } from '../lib/courses'
import { blankState, markRead, parseState, type CourseState } from '../lib/state'
import embedCss from '../styles/xt-embed.css?raw'

// 视觉稿 xt-embed.css（规则挂在 html.xt-embed 下）+ 外层负责滚动，iframe 内不出滚动条
const EMBED_CSS = embedCss + '\nhtml.xt-embed body{overflow:hidden}'

interface Props { course: Course; file: string; hash: string }

/** 同源 iframe 加载渲染好的教材页：注入嵌入样式、高度自适应、把 iframe 内导航同步回外层路由 */
export function CourseFrame({ course, file, hash }: Props) {
  const ref = useRef<HTMLIFrameElement>(null)
  const [ready, setReady] = useState(false)
  const navigate = useNavigate()
  const base = `${import.meta.env.BASE_URL}course/${course.id}/`

  // 外层路由变化 → iframe 地址；iframe 已在目标页时不重载，只滚动到锚点
  useEffect(() => {
    const win = ref.current?.contentWindow
    const target = pageUrl(course, file, hash)
    if (win && decodeURIComponent(win.location.pathname).endsWith('/' + file)) {
      if (hash && win.location.hash !== '#' + hash) win.location.hash = hash
      return
    }
    setReady(false)
    ref.current?.setAttribute('src', target)
  }, [course, file, hash])

  useEffect(() => {
    const frame = ref.current
    if (!frame) return
    let ro: ResizeObserver | undefined
    let cleanupWin = () => {}

    const syncRoute = (win: Window) => {
      const path = decodeURIComponent(win.location.pathname)
      if (!path.startsWith(base)) return
      const f = path.slice(base.length)
      const h = win.location.hash.slice(1)
      navigate(`/${course.id}/${encodeURIComponent(f)}${h ? '#' + h : ''}`, { replace: true })
    }

    const onLoad = () => {
      const win = frame.contentWindow
      const doc = frame.contentDocument
      if (!win || !doc) return
      doc.documentElement.classList.add('xt-embed')
      const style = doc.createElement('style')
      style.textContent = EMBED_CSS
      doc.head.appendChild(style)
      ro?.disconnect()
      ro = new ResizeObserver(() => { frame.style.height = doc.documentElement.scrollHeight + 'px' })
      ro.observe(doc.body)
      const onHash = () => syncRoute(win)
      win.addEventListener('hashchange', onHash)
      cleanupWin = () => win.removeEventListener('hashchange', onHash)
      syncRoute(win)
      if (course.engine === 'static') bindReadChecks(doc, win, course)
      setReady(true)
    }
    frame.addEventListener('load', onLoad)
    return () => { frame.removeEventListener('load', onLoad); ro?.disconnect(); cleanupWin() }
  }, [base, course, navigate])

  return (
    <iframe
      ref={ref}
      title="教材正文"
      className="xt-frame"
      style={{ visibility: ready ? 'visible' : 'hidden' }}
    />
  )
}

/** static 引擎页面不带引擎脚本，「读完打卡」与跟踪项由外层处理：
 *  点击 .xt-check[data-id] → 经 iframe 的 localStorage 写入课程状态（done + xp），
 *  外层收到 storage 事件后按现有差分规则上报 done 事件；再次进入时按本地状态恢复已打卡样式。 */
function bindReadChecks(doc: Document, win: Window, course: Course) {
  const read = () => parseState(win.localStorage.getItem(course.key))
  const paint = (btn: HTMLButtonElement, done: boolean) => {
    btn.classList.toggle('xt-check--done', done)
    btn.setAttribute('aria-pressed', String(done))
    btn.disabled = done
    if (done && !btn.dataset.label) { btn.dataset.label = btn.textContent ?? ''; btn.textContent = '✓ 已打卡' }
  }
  for (const btn of doc.querySelectorAll<HTMLButtonElement>('.xt-check[data-id]')) {
    const id = btn.dataset.id!
    paint(btn, !!read()?.done[id])
    btn.addEventListener('click', () => {
      const s = read() ?? blankState(course.stateVersion, course.courseId ?? course.id)
      const xp = Number(btn.dataset.xp) || undefined
      const next = markRead(s, id, xp)
      // 页面自带引擎时同步其内存状态，避免引擎下次保存时覆盖掉打卡
      const live = engineState(win)
      if (live) { live.done[id] = 1; live.xp[id] = next.xp[id]; Object.assign(live.days, next.days) }
      win.localStorage.setItem(course.key, JSON.stringify(next))
      paint(btn, true)
    })
  }
  // 跟踪项 input.track（0 XP，记入 rec）：页面无引擎脚本时由外层写状态；有引擎时由引擎处理
  if (engineState(win)) return
  for (const box of doc.querySelectorAll<HTMLInputElement>('input.track[data-id]')) {
    const id = box.dataset.id!
    box.checked = !!read()?.rec[id]
    box.addEventListener('change', () => {
      const s = read() ?? blankState(course.stateVersion, course.courseId ?? course.id)
      const rec = { ...s.rec }
      if (box.checked) rec[id] = 1
      else delete rec[id]
      win.localStorage.setItem(course.key, JSON.stringify({ ...s, rec }))
    })
  }
}

/** 页面引擎（若有）暴露的内存状态：window.Course.state() */
function engineState(win: Window): CourseState | null {
  const c = (win as Window & { Course?: { state?: () => CourseState } }).Course
  return typeof c?.state === 'function' ? c.state() : null
}
