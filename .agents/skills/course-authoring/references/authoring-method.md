# 写课方法

本节说明一门课从分工到验收的做法。课程以若干自包含 HTML 页面交付，放在 `COURSE_DIR` 下的一个子目录中，由小驼的阅读器（Reader）以 iframe 嵌入。下文只描述仓库当前支持的写法；`course.json` 字段、id 规则细节、`npm run import` 与 `content_version` 见 [integration.md](integration.md)，完整示例见 [walkthrough.md](walkthrough.md)（`examples/sample-course`）。

## 1. 角色分工

建议按以下角色协作，同一人可兼任多个角色：

| 角色 | 职责 |
|---|---|
| 协调人 | 拆分章节、指定每人负责的文件与范围、跟进进度、独立验收。不写页面正文。 |
| 主题作者（1–3 人） | 各自负责若干章：查证资料、写正文、写练习与 Boss 关题目。 |
| 教学设计 | 写教学方案（每章学习目标、节结构、难度梯度），牵头基础章与课程导览。 |
| 视觉设计 | 公共样式与页面组件写法、视觉验收与截图审查。 |

约定：
- 所有成员共用一个讨论群和一个共享目录。
- 内容必须基于可查证的资料，每页末尾附参考链接；不编造数据、名称或链接。
- 示意图、示例指标在页面上标注「示意」或「示例数据」。
- 组件写法一旦确定，立即在群里公布可复制的 HTML 片段，作者照片段开工，不必等待额外通知。

## 2. 流程

1. **内容初稿**：协调人下发分工，作者按章写正文与参考资料。
2. **教学方案**：先设计后实现。方案写明每章、每节的学习目标，题目考点与所在小节，以及每章是否设 Boss 关。
3. **页面实现**：按第 3–6 小节的写法落地到 HTML。任何页面改动后都要重新运行 `npm run import` 做清单校验（见 [integration.md](integration.md)）。
4. **预演与验收**：按第 8 小节执行，问题修复后复测，直至全部通过。

## 3. 分页粒度

- **一章一页**：每章一个 HTML 文件，在 `course.json` 的 `chapters` 中登记（static 引擎）。示例：`examples/sample-course` 有 `00-开始.html`、`01-基础.html` 两章。
- **目录首页章**：可设一个 `home_chapter`（如示例中的 `00`），用于课程介绍与使用说明，不参与毕业判定。
- **章内小节**：用 `<section id="…">` 划分。每节建议结构为：问题引入 → 类比 / 图解 → 练习 → 小结。
- **读完打卡**（`.xt-check`，计 10 XP；区别于 0 XP 的跟踪项 `input.track`）：`<main>` 内最后一个元素放一个打卡按钮，其前依次为 Boss 节、参考资料节，作为该章的完成标记：

  ```html
  <button class="xt-check" data-id="01-done-read">读完打卡</button>
  ```

  打卡由外层 `CourseFrame` 统一处理（写入 `done` 与 XP、恢复已打卡样式、触发同步），课程页面和页面脚本**不要**自行绑定或重新实现。没有练习题的页面也应保留打卡。
- 页面 id 在一门课内全局唯一，采用 `<章>-<类型或名称>` 形式；**已发布的 id 只增不删**，否则会影响学员已有进度（修改已发布课程时，在仓库根目录运行 `scripts/check_ids.py` 对比基线；新课程首次制作无需运行）。

## 4. 练习

仓库示例引擎（`examples/sample-course/assets/course.js`）当前提供以下组件，均以 `data-id` 计分且同一 id 只计一次分，答错不扣分：

| 组件 | 写法 | 计分 |
|---|---|---|
| 选择题 | `<div class="quiz" data-id="01-quiz-1" data-answer="b">`，内含若干 `<button data-opt="…">`；`data-answer` 等于正确项的 `data-opt`，完整片段见 [integration.md](integration.md) 4.5 | 答对得分，默认 10 XP，可用 `data-xp` 覆盖 |
| 跟踪项 | `<input type="checkbox" class="track" data-id="00-rec-setup">` | 0 XP，只记录学习行为，不计入得分项 |
| 读完打卡 | `<button class="xt-check" data-id="<章>-done-read">` | 默认 10 XP（外层处理） |

选择题行为：答错时该选项标记为错误，可继续作答；答对后记分，并记录此前答错次数（用于 Boss 关的「无错」判定）。

出题要求：
- 同一节内的题目不重复考同一个知识点。
- 选项和卡片上不出现会泄露答案的序号或提示。
- 题干与选项中的 `<`、`>` 等字符须做 HTML 转义，避免被当作标签。

如需选择题以外的互动形式，课程可自带页面引擎（`window.Course`，需提供 `state()` 与 `inventory()`），但在接入前必须确认其得分项能通过 `npm run import` 的清单校验；本文档不将其列为现成组件。

## 5. 小测

小测即节末的一到两道选择题，用来确认本节目标是否达成。放在该节 `<section>` 内的末尾，紧接小结之前，写法同第 4 小节的选择题。每节至少一道小测，题目对应该节学习目标；参考资料等不计分的辅助节除外。

## 6. Boss 关

每章可在页尾设一个 Boss 综合挑战，结构如下（取自 `examples/sample-course/01-基础.html`）：

```html
<section id="boss">
  <h2>👑 Boss 关</h2>
  <div class="boss" data-id="01-boss" data-badge="boss01">
    <div class="stage">
      <div class="quiz" data-id="01-boss-q1" data-answer="a">…</div>
    </div>
    <!-- 更多 .stage -->
  </div>
</section>
```

规则（以示例引擎与 `import-course.mjs` 为准）：
- Boss 节必须是 `<section id="boss">`，节内不嵌套 `section`；关卡容器为 `div.boss`，`data-id` 取 `<章>-boss`。
- 每个 `.stage` 是一关，关内全部题目答对即过关；关卡按顺序结算，前一关通过后才记后一关的分；后一关先完成时分数暂缓，前一关通过后自动补记。
- 计分：每关 20 XP（`boss_stage`），全部通关加 50 XP（`boss_clear`，id 后缀 `-clear`），全程无错再加 30 XP（`boss_perfect`，后缀 `-perfect`）；读完打卡与其他题型默认分别取 `done`、`default`，均为 10 XP。关内题目本身不单独计分。示例引擎把 Boss 分值写死为 20/50/30，使用示例引擎时不要在 `course.json` 的 `xp` 中覆盖 `boss_*`，否则前后端分值不一致。
- `data-badge` 指定通关徽章，徽章需在 `course.json` 的 `badges` 中登记（字段见 [integration.md](integration.md)）。
- 设了 Boss 的章，毕业判定要求该 Boss 已通关；不设 Boss 的章在目录中显示「本章无 Boss」。

## 7. 视觉要求

配色、对比度、嵌入适配与窄屏要求见 [visual-spec.md](visual-spec.md)。

## 8. 预演与验收

1. **清单校验**：每次改动后按顺序执行以下四步，均须返回 0：① `build_content.py` 带 `--write-cache`，为 `course-manifest-js` 引擎的课程生成 `.xiaotuo-inventory.json`（仅此类课程要求本机有 node 与 Chrome；static 课程不调用浏览器、不生成该文件，只要求返回 0）；② 不带该开关再跑一次 `build_content.py`，模拟容器内无浏览器、只读缓存的启动；③ 运行 `check_content.py`；④ 运行 `npm run import` 做前端清单校验。`--src` 指向课程根目录（各门课子目录的上一层），输出目录用临时目录。课程 HTML 或 `assets/course*.js` 任何改动都会使缓存失效，需从第①步重来。同时确认 id 无重复、未删除已有 id。具体命令见 [integration.md](integration.md)。
2. **人工走查**：在 1280 与 390 两种宽度下，通过小驼 Reader 逐页操作：每道题先答错再答对，完成全部打卡，打通 Boss；核对 XP 与预期一致、刷新后进度保留、浏览器控制台无报错。
3. **交叉通读**：作者互换章节，以初学者视角阅读，记录看不懂处、难度跳跃、重复题与泄露答案的问题，写入验收记录。
4. **截图审查**：视觉设计检查两种宽度下的横向溢出、长代码换行、触控尺寸与 HTML 转义问题。
5. **协调人验收**：修复复测全部通过后，协调人独立复走一遍再交付。

验收清单：
- [ ] 每节有练习，每节末有小测；需要的章设有 Boss 关
- [ ] 每页末尾有读完打卡，页面未自行处理 `.xt-check`
- [ ] 四步（带 `--write-cache` 的 build、不带开关的 build、check、`npm run import`）均返回 0，id 无重复、无删除
- [ ] `course-manifest-js` 课程已生成有效的 `.xiaotuo-inventory.json`（static 课程不适用）
- [ ] XP 实得与预期一致，刷新后保留，控制台无报错
- [ ] 1280 / 390 无横向溢出，按钮可点
- [ ] `--c-d`（或 `accent_dark`）与白底对比度 ≥ 4.5:1
- [ ] 无重复题，选项无泄露序号
- [ ] 参考链接真实可访问，示例数据已标注
