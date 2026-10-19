/* 示例课程的最小引擎：选择题、跟踪项、Boss 关。
   进度写入 localStorage[<html data-key>]，格式同 state_version 1 的 blank()；外层页面监听 storage 事件上报。
   「读完打卡」（button.xt-check）由外层阅读器处理，本脚本不绑定。 */
(function () {
  'use strict'
  var D = document, root = D.documentElement
  var KEY = root.getAttribute('data-key'), COURSE = root.getAttribute('data-course')
  var page = (D.body && D.body.getAttribute('data-page')) || ''
  function $$(s, r) { return Array.prototype.slice.call((r || D).querySelectorAll(s)) }
  function today() { var d = new Date(); return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2) }
  function blank() { return { version: 1, course: COURSE, xp: {}, done: {}, rec: {}, solved: {}, fix: {}, streak: { cur: 0, best: 0, last: null }, days: {}, badges: {}, quiet: false, data: {}, sections: {} } }
  function load() {
    try { var s = JSON.parse(localStorage.getItem(KEY)); if (s && s.version === 1 && s.course === COURSE) { var b = blank(); for (var k in b) if (s[k] == null) s[k] = b[k]; return s } } catch (e) {}
    return blank()
  }
  var state = load()
  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)) } catch (e) {} }
  function touchDay() {
    var t = today(), s = state.streak; if (s.last === t) return
    var y = new Date(); y.setDate(y.getDate() - 1)
    var yd = y.getFullYear() + '-' + ('0' + (y.getMonth() + 1)).slice(-2) + '-' + ('0' + y.getDate()).slice(-2)
    s.cur = s.last === yd ? s.cur + 1 : 1; s.best = Math.max(s.best, s.cur); s.last = t; state.days[t] = 1
  }
  function award(id, amt) { if (state.xp[id] != null) return; state.xp[id] = amt; if (amt > 0) touchDay(); if (!state.badges.first && amt > 0) state.badges.first = today() }
  function num(el, name, d) { var v = parseInt(el.getAttribute(name), 10); return isNaN(v) ? d : v }

  // 选择题：答对记 XP；Boss 内的题只记 solved，由 Boss 结算关卡分
  function quiz(el, onSolved) {
    var id = el.getAttribute('data-id'), ans = el.getAttribute('data-answer'), wrong = 0
    var c = { id: id, solved: !!state.solved[id], wrong: state.solved[id] ? state.solved[id].wrong : 0 }
    if (c.solved) el.classList.add('ok')
    $$('button[data-opt]', el).forEach(function (b) {
      b.addEventListener('click', function () {
        if (c.solved) return
        if (b.getAttribute('data-opt') !== ans) { wrong += 1; c.wrong = wrong; b.classList.add('wrong'); return }
        c.solved = true; el.classList.add('ok')
        state.solved[id] = { rev: false, wrong: wrong }; if (wrong > 0) state.fix[id] = 1
        if (onSolved) onSolved(c); else award(id, num(el, 'data-xp', 10))
        save()
      })
    })
    return c
  }

  function boss(el) {
    var id = el.getAttribute('data-id'), stages = $$(':scope>.stage', el), comps = []
    function stageDone(i) { return state.xp[id + '-s' + (i + 1)] != null }
    function check() {
      stages.forEach(function (s, i) {
        var cs = comps.filter(function (c) { return c.stage === i })
        if (!stageDone(i) && (i === 0 || stageDone(i - 1)) && cs.length && cs.every(function (c) { return c.solved })) award(id + '-s' + (i + 1), 20)
      })
      if (stages.every(function (s, i) { return stageDone(i) }) && state.xp[id + '-clear'] == null) {
        award(id + '-clear', 50)
        if (comps.every(function (c) { return !c.wrong })) award(id + '-perfect', 30)
        var b = el.getAttribute('data-badge'); if (b && !state.badges[b]) state.badges[b] = today()
        state.data['cleared.' + page] = 1
      }
      el.classList.toggle('cleared', state.xp[id + '-clear'] != null)
    }
    stages.forEach(function (s, i) { $$('.quiz', s).forEach(function (q) { var c = quiz(q, function () { check() }); c.stage = i; comps.push(c) }) })
    check()
  }

  $$('.boss').forEach(boss)
  $$('.quiz').forEach(function (q) { if (!q.closest('.boss')) quiz(q) })
  $$('input.track[data-id]').forEach(function (inp) {
    var id = inp.getAttribute('data-id'); inp.checked = !!state.rec[id]
    inp.addEventListener('change', function () { if (inp.checked) state.rec[id] = 1; else delete state.rec[id]; save() })
  })

  // 与现有课程引擎一致的清单接口（只读）
  window.Course = {
    state: function () { return state },
    inventory: function () {
      var items = $$('.quiz').filter(function (q) { return !q.closest('.boss') }).map(function (q) { return { id: q.getAttribute('data-id'), type: 'quiz', xp: num(q, 'data-xp', 10) } })
      $$('.boss').forEach(function (b) {
        var id = b.getAttribute('data-id')
        $$(':scope>.stage', b).forEach(function (s, i) { items.push({ id: id + '-s' + (i + 1), type: 'boss-stage', xp: 20 }) })
        items.push({ id: id + '-clear', type: 'boss-clear', xp: 50 }, { id: id + '-perfect', type: 'boss-perfect', xp: 30 })
      })
      return { page: page, subpage: '', items: items }
    }
  }
})()
