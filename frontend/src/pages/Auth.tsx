import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, confirmPasswordReset, requestPasswordReset } from '../lib/api'
import { getCourses } from '../lib/courses'
import { readOwner } from '../lib/owner'
import { login, register, useSession } from '../lib/session'
import { parseState, totalXP } from '../lib/state'

const PW_MIN = 10
const PW_MAX = 128

/** 密码字段校验提示（服务端 400/422 时也按长度给出中文说明） */
const pwText = (pw: string, fallback: string) =>
  pw.length < PW_MIN ? `密码至少 ${PW_MIN} 位，当前 ${pw.length} 位。` : pw.length > PW_MAX ? `密码最多 ${PW_MAX} 位。` : fallback

/** 本机有未归属任何账号的课程进度（首次登录会并入） */
const hasAnonProgress = () => !readOwner() && getCourses().some((c) => { const s = parseState(localStorage.getItem(c.key)); return !!s && totalXP(s) + Object.keys(s.done).length > 0 })

function errText(e: unknown): string {
  if (!(e instanceof ApiError)) return '出错了，请稍后再试'
  if (e.status === 0) return '无法连接服务，请检查网络后重试'
  if (e.status === 429) return `尝试太频繁，请 ${e.retryAfter || 60} 秒后再试`
  return e.message
}

function Shell({ title, sub, children, foot, headingRef }: { title: string; sub: string; children: ReactNode; foot: ReactNode; headingRef?: React.Ref<HTMLHeadingElement> }) {
  return (
    <main className="xt-narrow">
      <div className="xt-card">
        <div className="xt-auth-h"><div className="xt-mascot" aria-hidden="true">🦙</div><h1 className="xt-h1" ref={headingRef} tabIndex={headingRef ? -1 : undefined}>{title}</h1><p className="xt-p" style={{ margin: 0 }}>{sub}</p></div>
        {children}
      </div>
      <p className="xt-auth-f">{foot}</p>
    </main>
  )
}

function Field({ id, label, err, hint, extra, ...input }: { id: string; label: string; err?: ReactNode; hint?: string; extra?: ReactNode } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="xt-field">
      <div className="xt-row xt-between"><label className="xt-label" htmlFor={id}>{label}</label>{extra}</div>
      <input className="xt-input" id={id} name={id} aria-invalid={err ? true : undefined} aria-describedby={[err && `${id}-e`, hint && `${id}-h`].filter(Boolean).join(' ') || undefined} {...input} />
      {err && <span className="xt-err" id={`${id}-e`}>{err}</span>}
      {hint && <span className="xt-hint" id={`${id}-h`}>{hint}</span>}
    </div>
  )
}

const useNext = () => {
  const n = useSearchParams()[0].get('next')
  return n && n.startsWith('/') && !n.startsWith('//') ? n : '/dashboard'
}

export function Login() {
  const me = useSession()
  const next = useNext()
  const nav = useNavigate()
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const h1 = useRef<HTMLHeadingElement>(null)
  // 进入登录页（含退出后重定向）时把焦点交给标题；用户已在页面内操作（焦点在表单等处）时不抢焦点
  useEffect(() => {
    const a = document.activeElement
    if (!a || a === document.body || a.closest('.xt-top')) h1.current?.focus()
  }, [])
  if (me?.user) return <Navigate to={next} replace />
  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    setBusy(true); setErr('')
    try { await login(String(f.get('em')), String(f.get('pw'))); nav(next, { replace: true }) } catch (x) { setErr(errText(x)) } finally { setBusy(false) }
  }
  const reset = me?.features.password_reset // false 时为 login-noemail 变体：隐藏「忘记密码」
  return (
    <Shell title="登录" headingRef={h1} sub="登录后进度保存到账号，换设备也能继续。" foot={<>还没有账号？<Link className="xt-link" to={`/register?next=${encodeURIComponent(next)}`}>注册</Link></>}>
      <form className="xt-form" onSubmit={onSubmit}>
        <Field id="em" label="邮箱" type="email" autoComplete="email" placeholder="name@example.com" required />
        <Field id="pw" label="密码" type="password" autoComplete="current-password" required err={err}
          extra={reset && <Link className="xt-link" to="/reset" style={{ fontSize: 13 }}>忘记密码？</Link>} />
        <button className="xt-btn xt-btn--block" type="submit" disabled={busy}>{busy ? '登录中…' : '登录'}</button>
        {hasAnonProgress() && <div className="xt-notice"><span className="xt-notice-ic">💡</span><span>本机已有未登录时的学习进度，首次登录会自动并入账号（完成项与徽章取并集）。</span></div>}
      </form>
    </Shell>
  )
}

export function Register() {
  const me = useSession()
  const next = useNext()
  const nav = useNavigate()
  const [errs, setErrs] = useState<{ em?: ReactNode; pw?: string; pw2?: string; form?: string }>({})
  const [busy, setBusy] = useState(false)
  if (me?.user) return <Navigate to={next} replace />
  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const em = String(f.get('em')), pw = String(f.get('pw')), pw2 = String(f.get('pw2'))
    const em0 = em.trim() ? undefined : '请输入邮箱。' // 格式由服务端校验并映射到字段
    if (em0 || pw.length < PW_MIN) return setErrs({ em: em0, pw: pw.length < PW_MIN ? (pw ? `密码至少 ${PW_MIN} 位，当前 ${pw.length} 位。` : '请输入密码。') : undefined })
    if (pw !== pw2) return setErrs({ pw2: '两次输入的密码不一致。' })
    setBusy(true); setErrs({})
    try {
      await register(em, pw)
      nav(next, { replace: true })
    } catch (x) {
      const code = x instanceof ApiError ? x.code : ''
      if (code === 'email_taken') setErrs({ em: <>该邮箱已注册。<Link className="xt-link" to="/login">直接登录</Link>{me?.features.password_reset && <> 或 <Link className="xt-link" to="/reset">找回密码</Link></>}</> })
      else if (code === 'weak_password') setErrs({ pw: '该密码过于常见，容易被猜中，请换一个。' })
      else if (x instanceof ApiError && x.fields) setErrs({ em: x.fields.email && '邮箱格式不正确。', pw: x.fields.password && pwText(pw, x.fields.password), form: x.fields.email || x.fields.password ? undefined : x.message })
      else setErrs({ form: errText(x) })
    } finally { setBusy(false) }
  }
  return (
    <Shell title="注册" sub="注册后即可使用，无需邮箱验证。" foot={<>已有账号？<Link className="xt-link" to="/login">登录</Link></>}>
      <form className="xt-form" onSubmit={onSubmit} noValidate>
        <Field id="em" label="邮箱" type="email" autoComplete="email" placeholder="name@example.com" required err={errs.em} />
        <Field id="pw" label="密码" type="password" autoComplete="new-password" maxLength={PW_MAX} err={errs.pw} hint="10–128 位，不要求字母、数字、符号组合；常见弱密码会被拒绝。" />
        <Field id="pw2" label="确认密码" type="password" autoComplete="new-password" maxLength={PW_MAX} err={errs.pw2} />
        {errs.form && <div className="xt-notice xt-notice--err" role="alert"><span className="xt-notice-ic">⚠️</span><span>{errs.form}</span></div>}
        <button className="xt-btn xt-btn--block" type="submit" disabled={busy}>{busy ? '注册中…' : '注册并开始学习'}</button>
      </form>
    </Shell>
  )
}

/** 找回密码：无 token 时申请邮件，有 ?token= 时设置新密码。功能关闭（features 或 503）时显示说明。 */
export function Reset() {
  const me = useSession()
  const token = useSearchParams()[0].get('token')
  const [state, setState] = useState<'form' | 'sent' | 'done' | 'disabled'>(me && !me.features.password_reset ? 'disabled' : 'form')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const foot = <Link className="xt-link" to="/login">返回登录</Link>
  if (state === 'disabled' || (me && !me.features.password_reset))
    return (
      <Shell title="找回密码" sub="当前未开放邮件找回。" foot={foot}>
        <div className="xt-notice xt-notice--warn"><span className="xt-notice-ic">⚙️</span><span>找回密码暂未开放，请联系管理员重置。</span></div>
      </Shell>
    )
  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    setBusy(true); setErr('')
    try {
      if (token) {
        const pw = String(f.get('pw'))
        if (pw.length < PW_MIN) { setErr(`密码至少 ${PW_MIN} 位，当前 ${pw.length} 位。`); return }
        await confirmPasswordReset(token, pw); setState('done')
      } else { await requestPasswordReset(String(f.get('em'))); setState('sent') }
    } catch (x) {
      if (x instanceof ApiError && x.status === 503) setState('disabled')
      else if (x instanceof ApiError && x.code === 'weak_password') setErr('该密码过于常见，容易被猜中，请换一个。')
      else if (x instanceof ApiError && x.fields) setErr(token ? pwText(String(f.get('pw')), x.message) : '邮箱格式不正确。')
      else setErr(errText(x))
    } finally { setBusy(false) }
  }
  if (state === 'sent' || state === 'done')
    return (
      <Shell title="找回密码" sub={state === 'sent' ? '请查收邮件。' : '新密码已生效。'} foot={foot}>
        <div className="xt-notice xt-notice--ok"><span className="xt-notice-ic">📮</span><span>{state === 'sent'
          ? '如果该邮箱已注册，重置邮件将在几分钟内送达。链接仅可使用一次，并会在一段时间后失效；没收到请检查垃圾邮件箱。'
          : '密码已重置，该账号在所有设备上的登录已失效，请用新密码登录。'}</span></div>
      </Shell>
    )
  return (
    <Shell title={token ? '设置新密码' : '找回密码'} sub={token ? '设置后需重新登录。' : '输入注册邮箱，我们会发送一封重置邮件。'} foot={foot}>
      <form className="xt-form" onSubmit={onSubmit} noValidate>
        {token
          ? <Field id="pw" label="新密码" type="password" autoComplete="new-password" maxLength={PW_MAX} err={err} hint="10–128 位，常见弱密码会被拒绝。" />
          : <Field id="em" label="邮箱" type="email" autoComplete="email" placeholder="name@example.com" required err={err} />}
        <button className="xt-btn xt-btn--block" type="submit" disabled={busy}>{token ? '确认修改' : '发送重置邮件'}</button>
      </form>
    </Shell>
  )
}
