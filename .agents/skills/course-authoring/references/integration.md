# 接入小驼

本节说明一门课程如何被小驼发现、校验、在运行时加载和计分。内容以仓库代码的实际行为为准，已知限制列在文末。完整操作示例见 [walkthrough.md](./walkthrough.md)，写课方法见 [authoring-method.md](./authoring-method.md)，视觉约定见 [visual-spec.md](./visual-spec.md)。

## 1. 目录约定与课程根目录

```
<COURSE_DIR>/
  <subdir>/            # 建议与课程 id 同名；程序不强制
    course.json        # 课程清单；有此文件即注册为一门课
    00-xxx.html        # 章节页面，必须位于课程目录顶层
    01-xxx.html
    assets/            # 可选：course.js、course.css、图片等，运行时由后端从课程目录直接提供
```

发现规则（`backend/xiaotuo/catalog.py` 的 `discover()`；后端脚本、`xiaotuo start` 与容器启动共用）：

- 只遍历 `COURSE_DIR` 的直接子目录，不递归；没有 `course.json` 的子目录被忽略。
- 子目录按名称排序遍历；课程最终按 `order` 升序、`order` 相同时按 `id` 排序。
- 子目录可以是符号链接，但解析后必须位于课程根目录之内，否则拒绝。
- 后端脚本（`build_content.py`、`check_content.py`）一门课都没发现时校验失败；`xiaotuo start` 允许空目录，此时 `/api/courses` 返回空列表。

课程根目录的取值：

| 场景 | 取值 | 依据 |
|---|---|---|
| `xiaotuo start` | `--courses` 参数；未给时用随包示例课程（仓库内开发时为仓库根的 `examples/`） | `backend/xiaotuo/cli.py` `_resolve_courses()` |
| 后端脚本 | `--src` 参数；未给时取 `COURSE_DIR`，再未给时取仓库根同级的 `course-content` | `catalog.py` `course_root()` |
| 容器内 | `COURSE_DIR=/course`，宿主课程目录只读挂载到 `/course` | `Dockerfile`、`docker-compose.yml` |
| CI / e2e | 仓库根的 `examples/`（即 `examples/sample-course` 的父目录）；e2e 以 `xiaotuo start --courses` 启动临时后端 | `.github/workflows/ci.yml`、`frontend/e2e/backend.cjs` |

`CONTENT_HOST_DIR` 只在 docker compose 中使用，表示宿主机上的课程根目录（默认 `./examples`，即仓库自带示例课程），作为构建上下文和 `/course` 的挂载源。`xiaotuo start` 和后端脚本都不读取它。前端构建不读取任何课程目录。

课程内容存放在仓库之外，不提交进仓库。

## 2. course.json 字段

### 2.1 必填字段

| 字段 | 类型与约束 | 说明 |
|---|---|---|
| `schema` | 固定为 `1` | 清单格式版本 |
| `id` | 字符串，`^[a-z][a-z0-9_]{0,15}$`，全局唯一 | 用于 URL `/course/<id>/`、数据库 `course` 列和 API 路径参数 |
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
| `base_badges` | `[]` | 通用徽章，格式同 `badges`；只发放后端认得的条件徽章：`first`（完成任意一节）、`streak3` / `streak7`（连学 3 / 7 天）、`comeback`（累计 5 道题先错后对）。未声明的通用徽章不计入学习中心的徽章总数 |
| `grad_badge` | 无 | 毕业徽章 `[id, 图标, 名称, 说明]`，id 固定为 `grad`；参与毕业判定的各章完成后发放。未声明则不设毕业徽章 |
| `accent_light` | 由 `accent` 派生 | `#rrggbb`，覆盖 `--c-l` |
| `accent_dark` | 由 `accent` 派生 | `#rrggbb`，覆盖 `--c-d` |

Boss 一律由页面标记识别（第 4.2 节），清单中不需要 Boss 字段。

学习中心显示的徽章总数 = `base_badges` + 页面 Boss 引用的 `badges` + `grad_badge`，只计清单声明的徽章（`static` 引擎）。

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

漏写时完成标准的四步仍会通过，但运行时进度会写入错误的键并被静默丢弃，因此每页都要核对。纯阅读页不带脚本时也保留这三个属性，便于日后加练习。

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

## 5. 运行时课程目录（xiaotuo start 与 /api/courses）

前端不在构建时打包课程。课程目录与课程页面都在运行时由后端提供：

```bash
cd backend
uv run python -m xiaotuo.cli start --courses "$COURSE_DIR" --cache-dir <临时目录>/content \
  --database-url "sqlite:///<临时目录>/xt.db" --no-browser --port 0
```

已安装小驼时用 `xiaotuo start`，参数相同。启动顺序（`backend/xiaotuo/cli.py`）：

1. 确定课程根目录（第 1 节）与内容缓存目录 `--cache-dir`（默认 `<个人数据目录>/content`，个人数据目录可用 `XIAOTUO_DATA_DIR` 指定）。
2. 在进程内执行内容生成与双向校验，与第 6 节的两个脚本是同一实现（`backend/xiaotuo/content_build.py`）；先清理缓存目录中上次生成的 `items-*.json`、`courses.json`、`catalog.json`。`--no-build` 跳过这一步，直接使用已有缓存。
3. 迁移数据库（未给 `--database-url` 且未设 `DATABASE_URL` 时为个人数据目录下的 SQLite），监听端口；`--port 0` 取随机空闲端口。
4. 就绪后打印一行 `XIAOTUO_READY http://127.0.0.1:<端口>/`。打印时 `/api/courses` 已可用。

任一步失败时打印问题列表并以**退出码 2** 结束，例如：

```
课程清单有问题：
- <subdir>/course.json：缺少必填字段 accent
错误：课程内容生成失败（见上方问题）。…
```

`GET /api/courses` 返回 `{version, courses}`，不需要登录，带 `ETag`（未变化时返回 304）。`courses` 按 `order`、`id` 排序，每门课的主要字段：

| 字段 | 说明 |
|---|---|
| `id`、`key` | 课程 id 与 localStorage 键（`storage_key`） |
| `title`、`name`、`short`、`icon`、`accent*` | 显示信息 |
| `engine`、`stateVersion`、`courseId`、`homeChapter`、`graduation` | 清单字段 |
| `total` | 课程总 XP，以计分清单 `max_xp` 为准 |
| `pages[]` | 每章一项：`id`、`file`、`title`、`xp`、`sections`、`boss`、`ids`（计分项）、`subs`（小节页） |

字段契约见 `api/openapi.yaml` 的 `CatalogResponse` / `CourseMeta`。课程页面 `/course/<id>/<章节页面>` 与 `/course/<id>/assets/**` 由后端直接读取课程目录提供（只提供顶层 `*.html` 与 `assets/`）。

课程内容修改后需要重启 `xiaotuo start` 才会重新生成目录；页面文件本身改动后立即生效，但计分项变化必须重启。

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

参数取值：课程根目录按 `--src` → 环境变量 `COURSE_DIR` → 仓库根同级的 `../course-content`（`backend/xiaotuo/catalog.py` 的 `DEFAULT_ROOT`）的顺序确定。`--out` 不要使用默认值，默认值 `backend/content` 位于仓库内。无 `uv` 时用 `backend/.venv/bin/python` 代替 `uv run python`。

- `build_content.py`：生成 `items-<id>.json`、`courses.json`（后端计分元数据）和 `catalog.json`（`/api/courses` 的内容）；`--out` 默认 `backend/content`（仓库内，已忽略）。清单校验失败或内容问题（id 重复、id 不以章号开头、Boss 无 `.stage`、徽章未定义、计分项 XP 为 0 等）时退出码 2。
- `check_content.py`：有问题时退出码 2。
- 两者均不连接数据库。实现在 `backend/xiaotuo/content_build.py`，`scripts/` 下的两个文件是命令行薄壳。
- 容器启动（`docker/entrypoint.sh`）依次执行上述两步、数据库迁移、uvicorn；任一步失败容器即退出。因此课程清单错误或页面与计分项不一致时，容器以退出码 2 退出，可用 `docker compose logs app` 查看。课程更新后重启容器即重新生成。

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

- 由 `backend/xiaotuo/content_build.py` 的 `_finish()` 计算：`<id>-<sha256 前 12 位>`，摘要输入为该课计分项列表（id、章、类型、max_xp）、各章元数据（小节、Boss、徽章、是否参与毕业）和 Boss 徽章定义，按键排序后序列化。
- 增删或改名计分项、调整 XP、改动 Boss 关数、徽章、`home_chapter` / `graduation_chapters` 都会改变它；只改正文文字、样式、标题不会改变。
- 后端在就绪检查接口 `GET /api/health/ready` 中返回各课 `content_version`，并随进度快照一起下发，可用于确认线上加载的计分口径。

## 9. 后端相关约定

- **未知课程**：错误码均为 `course_not_found`（HTTP 404），有三个出口：
  - 进度相关 API 中课程 id 不在已生成的 `courses.json` 中（`backend/xiaotuo/routers/progress.py` 的 `course_or_404()`），消息「没有这门课」；
  - 框架级 404（如路由未匹配）经 `backend/xiaotuo/errors.py` 的 `http_error_handler` 统一返回，消息「没有这门课」；
  - 托管前端时，`backend/xiaotuo/static.py` 第 85 行对未匹配的 `/api/*` 兜底返回，消息「接口不存在」。
- **数据库 id 约束**：基线迁移 `0001_baseline` 中 `progress_items`、`badge_awards`、`activity_days` 三张表的 `course` 检查约束为 `course ~ '^[a-z][a-z0-9_]{0,15}$'`，与清单 `id` 规则一致；新课程无需新增迁移。
- **启动 exit 2 的情形**：课程根目录不存在；未发现任何课程；清单不是合法 JSON 或字段校验失败；`id` / `storage_key` 重复；章节文件缺失或不在课程目录顶层；`course-manifest-js` 课程缓存无效且无法运行浏览器；页面计分项问题；items 与页面双向检查不一致。

## 10. 已知限制

1. 运行时课程目录只在 `xiaotuo start` 启动时生成；课程计分项、章节或清单变化后须重启进程，`/api/courses` 才会更新。
2. `engine=course-manifest-js` 课程在没有浏览器的环境中启动时，必须带与当前内容一致的 `.xiaotuo-inventory.json`（第 7 节），否则启动以退出码 2 失败。
