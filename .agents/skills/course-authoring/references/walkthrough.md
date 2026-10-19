# 示例走查

本节以仓库内的 `examples/sample-course` 为模板，在仓库外新建一门课程并完成导入。字段与约定见 [integration.md](./integration.md)。以下命令和输出均为实际运行结果（课程根目录为 `/tmp/xt-walkthrough/courses`，计分清单输出到 `/tmp/xt-walkthrough/content`）。

## 1. 新建课程目录

课程内容放在仓库之外。复制示例课程，保留 `assets/`（最小引擎 `course.js` 与样式 `course.css`），删除示例页面：

```console
$ mkdir -p /tmp/xt-walkthrough/courses /tmp/xt-walkthrough/content
$ cp -r examples/sample-course /tmp/xt-walkthrough/courses/intro
$ cd /tmp/xt-walkthrough/courses/intro && rm 00-开始.html 01-基础.html && ls
assets
course.json
```

## 2. 填写 course.json

只填必填字段；`engine=static` 时 `chapters` 必填。`storage_key` 省略，默认为 `intro-v1`。

```json
{
  "schema": 1,
  "id": "intro",
  "title": "入门课程",
  "order": 20,
  "accent": "#12b886",
  "state_version": 1,
  "engine": "static",
  "chapters": [
    { "id": "01", "title": "第一章", "file": "01-第一章.html" }
  ]
}
```

## 3. 添加一页含读完打卡的页面

`01-第一章.html` 是纯阅读页，不引入 `course.js`；页面末尾的 `.xt-check` 由外层 Reader 处理。`data-key`、`data-course`、`data-page` 三个属性每页必写（见 [integration.md](./integration.md) 4.5），带练习的完整骨架也在该节。

```html
<!doctype html>
<html lang="zh-CN" data-key="intro-v1" data-course="intro"><head><meta charset="utf-8"><title>01 · 第一章</title>
<link rel="stylesheet" href="assets/course.css"></head>
<body data-page="01"><main>
<h1>第一章</h1>
<section id="overview"><h2>概述</h2><p>占位正文。</p></section>
<button class="xt-check" data-id="01-done-read">读完打卡</button>
</main></body></html>
```

## 4. 生成计分清单并校验

```console
$ cd backend
$ export COURSE_DIR=/tmp/xt-walkthrough/courses
$ export CONTENT_DIR=/tmp/xt-walkthrough/content
$ uv run python scripts/build_content.py --src "$COURSE_DIR" --out "$CONTENT_DIR" --write-cache
课程根目录：/tmp/xt-walkthrough/courses，发现 1 门课
intro: 1 项 / 10 XP / version intro-475ceab8a474
  01 第一章: 1 项 / 10 XP / Boss —
已写入 /tmp/xt-walkthrough/content
$ echo $?
0
$ uv run python scripts/build_content.py --src "$COURSE_DIR" --out "$CONTENT_DIR"
课程根目录：/tmp/xt-walkthrough/courses，发现 1 门课
intro: 1 项 / 10 XP / version intro-475ceab8a474
  01 第一章: 1 项 / 10 XP / Boss —
已写入 /tmp/xt-walkthrough/content
$ echo $?
0
$ uv run python scripts/check_content.py --src "$COURSE_DIR" --content "$CONTENT_DIR"
intro: items 1，页面交互 id 1，Boss 0（阶段 0）
✅ 双向一致
$ echo $?
0
```

顺序与 [integration.md](./integration.md) 第 6 节一致：先带 `--write-cache` 生成缓存（需要 node 与 Chrome），再不带开关模拟容器内无浏览器、只读缓存，最后双向校验。本课是 `static` 引擎，不生成 `.xiaotuo-inventory.json`（见第 7 步）。`--src` 是包含各课子目录的课程根目录；`--out` 指向仓库外目录，避免写入 `backend/content`。脚本都不连接数据库。

## 5. 导入前端

`CONTENT_DIR` 为绝对路径时，`import-course.mjs` 直接用它读取 `items-intro.json` 做交叉校验。

```console
$ cd ../frontend
$ npm run import --silent
imported intro:1 pages
$ echo $?
0
```

生成的 `src/data/courses.json` 中该课的关键字段：

```
id=intro  key=intro-v1  total=10  pages[0].ids=['01-done-read']
```

`npm run import` 会重写 `frontend/public/course/` 与 `frontend/src/data/courses.json`，两者都是已忽略的生成物。

## 6. 校验失败示例

### 6.1 缺少必填字段

从 `course.json` 删除 `accent` 后：

```console
$ npm run import --silent
课程清单校验失败（COURSE_DIR=/tmp/xt-walkthrough/courses）：
  - intro/course.json: accent 必须为 #rrggbb
$ echo $?
2
$ cd ../backend
$ uv run python scripts/build_content.py --src "$COURSE_DIR" --out "$CONTENT_DIR"
课程清单有问题：
- intro/course.json：缺少必填字段 accent
$ echo $?
2
```

容器启动时执行同一脚本，此类错误会使容器以退出码 2 退出。

### 6.2 要求计分清单但清单缺失

```console
$ CONTENT_DIR=/tmp/xt-none XT_REQUIRE_ITEMS=1 npm run import --silent
未找到后端计分清单 /tmp/xt-none/items-{intro}.json，已跳过 id 对照（先运行 backend/scripts/build_content.py 生成）
$ echo $?
2
```

不设 `XT_REQUIRE_ITEMS` 时只输出 `WARN` 并继续导入。

### 6.3 页面新增计分项但未重新生成清单

在页面中加入一道题 `<div class="quiz" data-id="01-quiz-1" …>`，直接导入：

```console
$ npm run import --silent
Error: intro: 页面 id 与 items-intro.json 不一致，多出 [01-quiz-1]，非跟踪项差异 []
$ echo $?
1
```

重新运行 `build_content.py` 后恢复正常，`content_version` 随计分项变化：

```console
$ uv run python scripts/build_content.py --src "$COURSE_DIR" --out "$CONTENT_DIR"
课程根目录：/tmp/xt-walkthrough/courses，发现 1 门课
intro: 2 项 / 20 XP / version intro-7c7c04704e68
  01 第一章: 2 项 / 20 XP / Boss —
已写入 /tmp/xt-walkthrough/content
$ npm run import --silent
imported intro:1 pages
$ echo $?
0
```

## 7. --write-cache

```console
$ uv run python scripts/build_content.py --src "$COURSE_DIR" --out "$CONTENT_DIR" --write-cache
课程根目录：/tmp/xt-walkthrough/courses，发现 1 门课
intro: 1 项 / 10 XP / version intro-475ceab8a474
  01 第一章: 1 项 / 10 XP / Boss —
已写入 /tmp/xt-walkthrough/content
$ echo $?
0
$ ls -a /tmp/xt-walkthrough/courses/intro
.  ..  01-第一章.html  assets  course.json
```

`static` 引擎不使用 `.xiaotuo-inventory.json`，因此不生成该文件；只有 `engine=course-manifest-js` 的课程会在课程目录写入缓存（需要 node 与 Chrome）。

## 8. 后续扩展

- 加练习：在页面中加入带 `data-id="<章>-<类型>-<名称>"` 的组件，并引入 `assets/course.js`。
- 加 Boss：按 [integration.md](./integration.md) 第 4.2 节添加 `<section id="boss">`，并在 `course.json` 的 `badges` 中定义 `data-badge` 对应的徽章。可对照 `examples/sample-course/01-基础.html`。
- 每次改动计分项后，依次重新执行第 4、5 步（`course-manifest-js` 课程必须重新执行 `--write-cache`）。
