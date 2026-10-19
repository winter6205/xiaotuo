# 视觉规范

本文规定课程配色、对比度、嵌入适配与窄屏要求。清单字段的格式与校验见 [integration.md](integration.md)；下文引用的 CSS 均以仓库 `frontend/src/styles/xt.css`、`frontend/src/styles/xt-embed.css` 原文为准。

## 1. 配色

清单中与配色相关的字段有三个（格式均为 `#rrggbb`）：

| 字段 | 必填 | 对应变量 | 用途 |
|---|---|---|---|
| `accent` | 是 | `--c` | 课程主色，仅用于色块与装饰 |
| `accent_light` | 否 | `--c-l` | 浅色底，例如首页课程卡图标底色（`.xt-course-ic`） |
| `accent_dark` | 否 | `--c-d` | 深色，用于文字、按钮文字与白字所在的色底，例如学习中心徽章组标题（`.xt-badge-group>.xt-h3`） |

外层在课程卡与课程根节点上设置 `--c`；清单给出 `accent_light`、`accent_dark` 时直接写入 `--c-l`、`--c-d`（`frontend/src/lib/courses.ts` 的 `courseVars`）。未给出时由 `xt.css` 第 95 行派生：

```css
.xt-course,.xt-badge-group,[data-course-root]{--c-l:color-mix(in srgb,var(--c,#888) 18%,white);--c-d:color-mix(in srgb,var(--c,#888) 60%,black)}
```

即：
- `--c-l` = 18% 主色 + 82% 白色（sRGB 空间混合）；
- `--c-d` = 60% 主色 + 40% 黑色，等价于每个 sRGB 分量乘以 0.6。

约定：`accent` 不直接用作正文或按钮文字颜色；需要文字色时使用 `--c-d`。

## 2. 对比度

要求：`--c-d`（或清单中的 `accent_dark`）作为文字色时，与白底（`#ffffff`）的对比度不低于 4.5:1。不达标时在清单中填写 `accent_dark` 覆盖派生值。仓库没有对此做自动检查，由视觉设计人工核对。

人工核对步骤：

1. **求 `--c-d` 色值**：若清单填了 `accent_dark`，直接取用；否则把 `accent` 的 R、G、B 分量（0–255）各乘以 0.6，四舍五入。
2. **求相对亮度 L**：对每个分量 c，令 c' = c / 255；若 c' ≤ 0.04045，则 c_lin = c' / 12.92，否则 c_lin = ((c' + 0.055) / 1.055)^2.4。然后 L = 0.2126·R_lin + 0.7152·G_lin + 0.0722·B_lin。
3. **求对比度**：白色 L = 1，对比度 = (1 + 0.05) / (L + 0.05)。结果 ≥ 4.5 即达标。
4. **浏览器复核**：在小驼中打开该课程，用浏览器开发者工具查看使用 `--c-d` 的元素（如徽章组标题），确认计算值与上一步一致；开发者工具的颜色面板若显示对比度，可作交叉参考。

示例（`examples/sample-course`，`accent` 为 `#4dabf7`）：`--c-d` = (46, 103, 148) ≈ `#2e6794`，与白底对比度约 6.0:1，达标；而 `accent` 本身与白底的对比度约 2.48:1，不能作为文字色，这正是约定「`accent` 仅用于色块与装饰」的原因。

## 3. 嵌入适配（`html.xt-embed`）

课程页面在小驼中以 iframe 嵌入。页面加载后，外层 `CourseFrame` 给页面的 `<html>` 加上 `xt-embed` 类，并注入 `xt-embed.css` 及一条 `html.xt-embed body{overflow:hidden}`（iframe 高度随内容自适应，由外层负责滚动）。全部规则挂在 `html.xt-embed` 下，用浏览器直接打开页面文件时不生效。

`xt-embed.css` 的实际规则：

| 类别 | 规则 |
|---|---|
| 隐藏页面自带导航与进度 | `nav.toc`、`.c-top`、`#page-progress`、`.data-tools`、`.local-note`、`#overall`，以及 `.badge-wall` 之后的同级 `p.meta` |
| 版式 | `.wrap` 改为单栏，`max-width:960px`，`padding:0`；`main` 去掉边框、圆角与阴影（外层 `.xt-frame-box` 已是卡片） |
| 表格与代码 | `main th` 不换行；`main td` 最小宽度 3.5em；`main pre`、`main table`、`main .tscroll` 使用细滚动条 |
| 窄屏（≤720px） | `main` 内边距收窄为 `18px 6px`；`.hero`、`section.primer` 收窄内边距；`.hero .lvl` 允许换行 |
| 读完打卡 | `.xt-check` 为可点击光标；已打卡态 `.xt-check--done` 为默认光标、透明度 0.85 |

对课程页面的要求：
- 不要为嵌入额外设置外框、阴影或外边距，避免与外层卡片叠加。
- 进度面板、本地数据导入导出等与外层重复的功能，使用上表中会被隐藏的类名或 id，或不在页面中提供。
- `.xt-check` 的已打卡样式由外层类名 `.xt-check--done` 控制，页面样式不要覆盖其状态。

## 4. 390px 宽度

要求：在 390px 视口下，通过小驼 Reader 打开每一页，页面不得出现横向滚动。

人工核对方法：
1. 浏览器开发者工具切换到 390px 宽度，逐页打开。
2. 在控制台执行 `document.documentElement.scrollWidth > innerWidth`，外层页面结果应为 `false`。
3. 滚动浏览整页，确认没有被截断或撑出卡片的内容；同时检查按钮可点、长代码与表格可读。

设计建议（非仓库强制规则）：
- 长代码块放在 `pre` 中，由 `pre` 自身横向滚动，不撑宽页面。
- 宽表格放在可横向滚动的容器中（例如 `.tscroll`），或在窄屏下改为卡片式排列。
- 行内长代码、长链接允许断行（如 `overflow-wrap:anywhere`）。
- 按钮与可点击区域尺寸不小于 36px。
