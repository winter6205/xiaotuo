import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { CatalogError, catalogLoaded, getCourses, loadCourses } from '../lib/courses'

type Phase = 'loading' | 'error' | 'empty' | 'ready'

const describe = (e: unknown) => {
  if (e instanceof CatalogError) {
    if (e.status === 0) return '无法连接到小驼服务，请确认 xiaotuo 仍在运行。'
    if (e.status === 503) return '课程目录暂不可用：课程清单校验失败或尚未生成，请查看启动日志。'
    return e.message
  }
  return '课程目录加载失败。'
}

/** 课程目录加载闸门：GET /api/courses 完成前不渲染路由。加载中 role=status，失败 role=alert（带重试），空目录给出提示 */
export function CatalogGate({ children }: { children: ReactNode }) {
  const initial: Phase = catalogLoaded() ? (getCourses().length ? 'ready' : 'empty') : 'loading'
  const [phase, setPhase] = useState<Phase>(initial)
  const [error, setError] = useState('')
  const focusRef = useRef<HTMLHeadingElement>(null)

  const run = useCallback((force: boolean) => loadCourses(force).then(
    (list) => setPhase(list.length ? 'ready' : 'empty'),
    (e) => { setError(describe(e)); setPhase('error') },
  ), [])
  /** 重试 / 重新检查：先回到加载中（role=status 播报），再请求 */
  const load = (force = false) => { setPhase('loading'); void run(force) }

  useEffect(() => { if (!catalogLoaded()) void run(false) }, [run])
  // 状态切换到错误 / 空时把焦点移到标题，读屏立即读到原因；重试按钮紧随其后
  useEffect(() => { if (phase === 'error' || phase === 'empty') focusRef.current?.focus() }, [phase])

  if (phase === 'ready') return <>{children}</>
  return (
    <main className="xt-main" data-catalog={phase}>
      {phase === 'loading' && (
        <div className="xt-notice" role="status" aria-live="polite">
          <span className="xt-spinner" aria-hidden="true" /><span>正在加载课程目录…</span>
        </div>
      )}
      {phase === 'error' && (
        <div className="xt-card xt-stack">
          <h1 className="xt-h2" tabIndex={-1} ref={focusRef}>课程目录加载失败</h1>
          <div className="xt-notice xt-notice--err" role="alert"><span className="xt-notice-ic" aria-hidden="true">⚠️</span><span>{error}</span></div>
          <div><button className="xt-btn" type="button" onClick={() => load()}>重试</button></div>
        </div>
      )}
      {phase === 'empty' && (
        <div className="xt-card xt-stack">
          <h1 className="xt-h2" tabIndex={-1} ref={focusRef}>还没有课程</h1>
          <div className="xt-notice" role="status"><span className="xt-notice-ic" aria-hidden="true">📚</span>
            <span>启动时指定的课程目录里没有发现任何课程。每门课应是该目录下一个含 <code>course.json</code> 的子目录；
              检查 <code>xiaotuo start --courses &lt;目录&gt;</code> 给出的路径后重启服务。不传 <code>--courses</code> 时使用自带的示例课程。</span></div>
          <div><button className="xt-btn xt-btn--ghost" type="button" onClick={() => load(true)}>重新检查</button></div>
        </div>
      )}
    </main>
  )
}
