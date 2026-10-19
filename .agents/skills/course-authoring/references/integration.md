# 接入小驼

本节说明一门课程如何被小驼发现、校验、导入和计分。内容以仓库代码的实际行为为准，已知限制列在文末。完整操作示例见 [walkthrough.md](./walkthrough.md)，写课方法见 [authoring-method.md](./authoring-method.md)，视觉约定见 [visual-spec.md](./visual-spec.md)。

## 1. 目录约定与课程根目录

```
<COURSE_DIR>/
  <subdir>/            # 建议与课程 id 同名；程序不强制
    course.json        # 课程清单；有此文件即注册为一门课
    00-xxx.html        # 章节页面，必须位于课程目录顶层
    01-xxx.html
    assets/            # 可选：course.js、course.css、图片等，导入时整体复制
```

发现规则（`frontend/scripts/import-course.mjs` 的 `discover()` 与 `backend/app/catalog.py` 的 `discover()` 实现同一规则）：

- 只遍历 `COURSE_DIR` 的直接子目录，不递归；没有 `course.json` 的子目录被忽略。
- 子目录按名称排序遍历；课程最终按 `order` 升序、`order` 相同时按 `id` 排序。
- 前端不跟随符号链接目录；后端拒绝解析后位于课程根目录之外的目录。
- 一门课都没发现也算校验失败。

课程根目录的取值：

| 场景 | 取值 | 依据 |
|---|---|---|
| 本地 `npm run import` / `npm run build` | 环境变量 `COURSE_DIR`，默认 `../course-content`（相对仓库根）；体验示例用 `COURSE_DIR=examples` | `import-course.mjs` 第 11 行 |
| 后端脚本 | `--src` 参数；未给时取 `COURSE_DIR`，再未给时取仓库根同级的 `course-content` | `catalog.py` `course_root()` |
| 容器内 | `COURSE_DIR=/course`，宿主课程目录只读挂载到 `/course` | `Dockerfile`、`docker-compose.yml` |
| CI / e2e | `COURSE_DIR=examples`（相对仓库根，即 `examples/sample-course` 的父目录） | `.github/workflows/ci.yml` |

`CONTENT_HOST_DIR` 只在 docker compose 中使用，表示宿主机上的课程根目录（默认 `./examples`，即仓库自带示例课程），作为构建上下文和 `/course` 的挂载源。前端脚本和后端脚本都不读取它。

课程内容存放在仓库之外，不提交进仓库。

## 2. course.json 字段

### 2.1 必填字段

| 字段 | 类型与约束 | 说明 |
|---|---|---|
| `schema` | 固定为 `1` | 清单格式版本 |
| `id` | 字符串，`^[a-z][a-z0-9_]{0,15}$`，全局唯一 | 用于 URL `/course/<id>/`、导入目录 `public/course/<id>/`、数据库 `course` 列和 API 路径参数 |
| `title` | 非空字符串 | 后端标题，学习中心徽章组标题也使用它 |
| `order` | 数字 | 首页排序，升序 |
| `accent` | `#rrggbb` | 课程主色，见第 3 节 |
| `state_version` | `1` 或 `2` | 本地进度快照格式：1 带 `course` 字段，2 不带 |
| `engine` | `"static"` 或 `"course-manifest-js"` | 章节与计分项来源，见下 |
| `chapters` | 非空数组，元素为 `{id, title, file}` | **仅 `engine=static` 时必填**；`file` 必须存在；`title` 必填、章 id 不重复、`file` 位于课程目录顶层仅后端校验 |

`engine` 取值：

- `static`：按 `chapters` 逐页静态解析 HTML 中的 `data-id`，不需要浏览器。新课程推荐使用。
- `course-manifest-js`：读取 `assets/course-manifest.js`（必须存在），逐项 XP 由无头浏览器调用页面的 `Course.inventory()` 得到，结果可缓存为 `.xiaotuo-inventory.json`（第 7 节）。

### 2.2 可选字段

| 字段 | 默认值 | 说明 |
|---|---|---|
| `storage_key` | `"<id>-v<state_version>"` | 本地进度的 localStorage 键；必须为非空字符串，全局唯一 |
| `name` | `title` | 前端显示名 |
| `short` | `name`，再缺省为 `title` | 前端短名 |
| `icon` | `📘` | 课程图标 |
| `course_id` | 课程 `id` | `state_version=1` 时快照中的 `course` 字段 |
| `graduation_chapters` | 除 `home_chapter` 外的全部章 | 参与毕业判定的章；必须为数组 |
| `home_chapter` | 无 | 目录首页章，不参与毕业判定（Boss 与徽章照常） |
| `xp` | `{"done":10,"default":10,"boss_stage":20,"boss_clear":50,"boss_perfect":30}` | `static` 引擎下各类型的默认 XP，页面元素的 `data-xp` 优先；可按组件类型加键（如 `"quiz": 10`）。示例引擎把 Boss 分值写死为 20/50/30，使用示例引擎时不要覆盖 `boss_*` |
| `badges` | 无 | Boss 徽章定义，格式为 `[[徽章 id, 图标, 名称, 说明], …]`；`static` 页面中 Boss 的 `data-badge` 必须在此定义 |
| `accent_light` | 由 `accent` 派生 | `#rrggbb`，覆盖 `--c-l` |
| `accent_dark` | 由 `accent` 派生 | `#rrggbb`，覆盖 `--c-d` |

Boss 一律由页面标记识别（第 4.2 节），清单中不需要 Boss 字段。

最小清单示例：

```json
{
  "schema": 1,
  "id": "intro",
  "title": "入门课程",
  "order": 20,
  "accent": "#12b886",
  "state_version": 1,
  "engine": "static",
  "chapters": [{ "id": "01", "title": "第一章", "file": "01-第一章.html" }]
}
```

## 3. 课程颜色

前端在课程卡片和课程根节点上设置 `--c: <accent>`（`frontend/src/lib/courses.ts` 的 `courseVars()`），其余两个变量由 `frontend/src/styles/xt.css` 第 95 行派生：

| 变量 | 默认派生 | 用途 |
|---|---|---|
| `--c` | `accent` 原值 | 仅用于色块与装饰 |
| `--c-l` | `color-mix(in srgb, var(--c) 18%, white)` | 浅色底，如课程图标底色 |
| `--c-d` | `color-mix(in srgb, var(--c) 60%, black)` | 文字色、按钮文字、白字的底色 |

清单给出 `accent_light` / `accent_dark` 时直接覆盖 `--c-l` / `--c-d`。`--c-d` 与白色的对比度应不低于 4.5:1，派生值不达标时用 `accent_dark` 指定。

## 4. 页面约定

### 4.1 计分项 id

- 计分元素写 `data-id="<章 id>-<类型或名称>"`，一门课内唯一；`static` 引擎下不以 `<章 id>-` 开头的 id 会报错。
- 类型由元素 class 决定，取值包括 `quiz`、`numeric`、`sort`、`bucket`、`match`、`scenario`、`fill`、`spot`、`codespot`、`experiment`、`pointpick`、`sim` 等；XP 取 `data-xp`，否则取清单 `xp` 中对应类型或 `default`。
- 小节完成：class 为 `done-check` 或 `xt-check`，登记为 `done` 类型。
- 跟踪项：`<input class="track" data-id="…">`，0 XP，登记为 `track`。

### 4.2 Boss

```html
<section id="boss">
  <h2>Boss 关</h2>
  <div class="boss" data-id="01-boss" data-badge="boss01">
    <div class="stage">…关内题目…</div>
    <div class="stage">…</div>
  </div>
</section>
```

- 每页最多一个 Boss，至少一个 `.stage`。
- 登记为 `<boss>-s1..sN`（每关 20 XP）、`<boss>-clear`（50）、`<boss>-perfect`（30），类型均为 `boss`。
- 关内题目（id 以 `<boss>-` 开头）不单独计分。
- `data-badge` 必须在清单 `badges` 中定义。

### 4.3 读完打卡 `.xt-check`

```html
<button class="xt-check" data-id="01-done-read">读完打卡</button>
```

- 放在页面末尾，登记为 `done` 类型，默认 10 XP，可用 `data-xp` 覆盖。
- 点击由外层 Reader 处理（`frontend/src/components/CourseFrame.tsx` 的 `bindReadChecks()`）：写入 iframe 的 localStorage（`done` 与 `xp`），外层监听 storage 事件后按差分规则上报；再次进入时按本地状态显示「✓ 已打卡」。页面带引擎时同步其内存状态 `window.Course.state()`。
- **课程自带的 `course.js` 不得为 `.xt-check` 绑定事件**，否则会重复计分。

### 4.4 是否携带 course.js

- 含测验、交互练习或 Boss 的页面需要引入 `assets/course.js`，由它处理答题、Boss 和跟踪项。
- 纯阅读页（只有正文和 `.xt-check`）可以不带脚本；此时跟踪项 `input.track` 也由外层 Reader 写入状态。
- 引入方式、位置与页面必需属性见 4.5。

### 4.5 页面骨架与必需属性

每个章节页面都必须带以下三个属性，示例引擎 `assets/course.js` 第 7–8 行从这里读取进度存储位置和页码：

| 属性 | 取值 | 作用 |
|---|---|---|
| `<html data-key>` | 等于清单 `storage_key`（缺省 `"<id>-v<state_version>"`，如 `demo-v1`） | localStorage 键，进度写在这里 |
| `<html data-course>` | 等于清单 `course_id`（缺省为课程 `id`） | 快照中的 `course` 字段，`load()` 据此判断是否本课进度 |
| `<body data-page>` | 本页的章 id（如 `01`） | Boss 通关记录 `cleared.<章 id>` |

漏写时四步校验仍会返回 0，但运行时进度会写入错误的键并被静默丢弃，因此每页都要核对。纯阅读页不带脚本时也保留这三个属性，便于日后加练习。

最小页面骨架（含一道选择题、一个跟踪项、参考资料、读完打卡）：

```html
<!doctype html>
<html lang="zh-CN" data-key="intro-v1" data-course="intro">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>01 · 第一章</title><link rel="stylesheet" href="assets/course.css"></head>
<body data-page="01">
<main>
<h1>第一章</h1>
<section id="basics">
  <h2>小节标题</h2>
  <p>正文。</p>
  <label><input type="checkbox" class="track" data-id="01-rec-try"> 我已动手试过一次</label>
  <div class="quiz" data-id="01-quiz-1" data-answer="b">
    <p class="q">题干</p>
    <button type="button" data-opt="a">选项 A</button>
    <button type="button" data-opt="b">选项 B（正确）</button>
    <button type="button" data-opt="c">选项 C</button>
  </div>
</section>
<!-- 设 Boss 时放在这里：<section id="boss">…</section>，见 4.2 -->
<section id="refs"><h2>参考资料</h2><ul><li><a href="https://example.org">来源名称</a></li></ul></section>
<button class="xt-check" data-id="01-done-read">读完打卡</button>
</main>
<script src="assets/course.js"></script>
</body>
</html>
```

要点：
- 选择题：`button[data-opt]` 必须是 `.quiz` 的后代；`data-answer` 逐字等于正确选项的 `data-opt`。
- 页尾顺序固定为：Boss 节 → 参考资料节 → `.xt-check`。`.xt-check` 是 `<main>` 内最后一个元素。
- `<script src="assets/course.js"></script>` 放在 `</main>` 之后、`</body>` 之前；`course.js` 同步执行，放在 `<head>` 中会找不到页面元素。
- 参考资料等不计分的辅助节不受「每节至少一道小测」约束。

## 5. npm run import

```bash
cd frontend
export COURSE_DIR=<课程根目录>
npm run import
```

`npm run build` 会先执行它。脚本行为：

1. 发现并校验全部课程清单（第 1、2 节），问题汇总输出后以**退出码 2** 结束：
   ```
   课程清单校验失败（COURSE_DIR=…）：
     - <subdir>/course.json: accent 必须为 #rrggbb
   ```
2. 清空并重建 `frontend/public/course/`，把每门课顶层 `*.html` 和 `assets/` 复制到 `public/course/<id>/`。
3. 按引擎解析章节、计分项与 XP。
4. 与后端计分清单 `items-<id>.json` 交叉校验：目录为 `backend/<CONTENT_DIR>`，`CONTENT_DIR` 默认 `content`，可设为绝对路径。
   - 清单存在：页面 id 与清单的差异只能是跟踪项，否则抛出错误 `页面 id 与 items-<id>.json 不一致`（未捕获异常，进程退出码为 1，见第 10 节）。通过后各章 XP 以清单 `max_xp` 为准。
   - 清单不存在：输出 `WARN 未找到后端计分清单 …，已跳过 id 对照`，继续导入；若设置 `XT_REQUIRE_ITEMS=1`（CI 使用），改为**退出码 2**。
5. 写出 `frontend/src/data/courses.json`，输出 `imported <id>:<页数> pages, …`。

`public/course/` 与 `src/data/` 均为生成物，已加入 `.gitignore`；运行完成标准写入这两处不算修改仓库。

## 6. 后端生成与校验

后端脚本按文件路径和命令行参数调用。`<课程根目录>` 是包含各课子目录的那一层（即 `COURSE_DIR`），不是单门课的目录。按以下顺序执行，三条命令均须返回 0：

```bash
cd backend
export COURSE_DIR=<课程根目录绝对路径>
export CONTENT_DIR=/tmp/xt-content
uv run python scripts/build_content.py --src "$COURSE_DIR" --out "$CONTENT_DIR" --write-cache
uv run python scripts/build_content.py --src "$COURSE_DIR" --out "$CONTENT_DIR"
uv run python scripts/check_content.py --src "$COURSE_DIR" --content "$CONTENT_DIR"
```

1. 带 `--write-cache`：仅 `course-manifest-js` 课程需要 node 与 Chrome，`static` 课程不调用浏览器；对 `engine=course-manifest-js` 的课程用浏览器重新生成 `.xiaotuo-inventory.json`（第 7 节）。`static` 课程不生成缓存。
2. 不带开关：模拟容器内无浏览器的情况，只读缓存，用于确认缓存与当前内容一致。
3. `check_content.py`：items 与页面双向检查。输出中的 items 数包含由跟踪项和 Boss 派生的条目（`<boss>-s1..sN`、`-clear`、`-perfect`），因此可能多于页面交互 id 数。

参数取值：课程根目录按 `--src` → 环境变量 `COURSE_DIR` → 仓库根同级的 `../course-content`（`backend/app/catalog.py` 的 `DEFAULT_ROOT`）的顺序确定。`--out` 不要使用默认值，默认值 `backend/content` 位于仓库内。无 `uv` 时用 `backend/.venv/bin/python` 代替 `uv run python`。

- `build_content.py`：生成 `items-<id>.json` 和 `courses.json`；`--out` 默认 `backend/content`（仓库内，已忽略）。清单校验失败或内容问题（id 重复、id 不以章号开头、Boss 无 `.stage`、徽章未定义、计分项 XP 为 0 等）时退出码 2。
- `check_content.py`：有问题时退出码 2。
- 两者均不连接数据库。
- 容器启动（`docker/entrypoint.sh`）依次执行上述两步、`alembic upgrade head`、uvicorn；任一步失败容器即退出。因此课程清单错误或页面与计分项不一致时，容器以退出码 2 退出，可用 `docker compose logs app` 查看。课程更新后重启容器即重新生成。

## 7. 清单缓存 .xiaotuo-inventory.json

仅用于 `engine=course-manifest-js`。逐项 XP 需要无头浏览器（node + Chrome + puppeteer-core），而容器内没有浏览器，因此在课程目录中缓存结果：

```bash
cd backend
uv run python scripts/build_content.py --src "$COURSE_DIR" --out "$CONTENT_DIR" --write-cache
```

- `--write-cache` 是 `build_content.py` 的参数：强制用浏览器重新生成并写入 `<课程目录>/.xiaotuo-inventory.json`，内容为 `{source_digest, pages}`。
- `source_digest` 是课程目录顶层全部 `*.html` 加 `assets/course.js`、`assets/course-manifest.js` 的 SHA-256。不带 `--write-cache` 时，摘要一致才使用缓存；不一致或缺失则尝试调用浏览器，失败即报错退出码 2。
- 摘要覆盖全部 `*.html`、`assets/course.js`、`assets/course-manifest.js`，课程每次修改后都要重新执行 `--write-cache`。
- `static` 引擎不使用缓存，带 `--write-cache` 运行也不会生成该文件。

## 8. content_version

- 由 `build_content.py` 的 `_finish()` 计算：`<id>-<sha256 前 12 位>`，摘要输入为该课计分项列表（id、章、类型、max_xp）、各章元数据（小节、Boss、徽章、是否参与毕业）和 Boss 徽章定义，按键排序后序列化。
- 增删或改名计分项、调整 XP、改动 Boss 关数、徽章、`home_chapter` / `graduation_chapters` 都会改变它；只改正文文字、样式、标题不会改变。
- 后端在就绪检查接口 `GET /api/health/ready` 中返回各课 `content_version`，并随进度快照一起下发，可用于确认线上加载的计分口径。

## 9. 后端相关约定

- **未知课程**：错误码均为 `course_not_found`（HTTP 404），有三个出口：
  - 进度相关 API 中课程 id 不在已生成的 `courses.json` 中（`backend/app/routers/progress.py` 的 `course_or_404()`），消息「没有这门课」；
  - 框架级 404（如路由未匹配）经 `backend/app/errors.py` 的 `http_error_handler` 统一返回，消息「没有这门课」；
  - 托管前端时，`backend/app/static.py` 第 85 行对未匹配的 `/api/*` 兜底返回，消息「接口不存在」。
- **数据库 id 约束**：基线迁移 `0001_baseline` 中 `progress_items`、`badge_awards`、`activity_days` 三张表的 `course` 检查约束为 `course ~ '^[a-z][a-z0-9_]{0,15}$'`，与清单 `id` 规则一致；新课程无需新增迁移。
- **启动 exit 2 的情形**：课程根目录不存在；未发现任何课程；清单不是合法 JSON 或字段校验失败；`id` / `storage_key` 重复；章节文件缺失或不在课程目录顶层；`course-manifest-js` 课程缓存无效且无法运行浏览器；页面计分项问题；items 与页面双向检查不一致。

## 10. 已知限制

1. 页面 id 与 `items-<id>.json` 不一致时，`npm run import` 抛出未捕获异常，退出码为 1（不是 2），后续会修。
2. 章节标题（`chapters[].title`）和重复的章 id 只有后端（`build_content.py`）校验，`npm run import` 不检查。
