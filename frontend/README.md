# frontend

外层前端：React + Vite + TypeScript。课程页以同源 iframe 嵌入；课程列表、顺序、本地存储键、主题色等全部来自课程清单 `course.json`，代码里不写死课程。

课程目录在**运行时**由后端 `GET /api/courses` 提供（启动时从课程目录生成），教材页 `/course/<id>/**` 由后端直接从课程目录提供；前端构建不读取任何课程目录。`src/components/CatalogGate.tsx` 在目录加载完成前不渲染路由（加载中 / 失败重试 / 空目录）。

| 命令 | 说明 |
|---|---|
| `npm run gen:api` | 从 `../api/openapi.yaml`（可用 `OPENAPI` 覆盖）生成 `src/lib/api-types.ts` |
| `npm test` | Vitest（合成数据，不依赖任何课程） |
| `npm run build` | 类型检查 + 构建，不需要课程目录；`XT_BASE` 指定 base 路径 |
| `npm run dev` | `/api`、`/course` 代理到后端（`XT_API`，或 `http://127.0.0.1:${XT_PORT ?? PORT ?? 13773}`），后端须以 `COURSE_DIR` 启动 |
| `npm run e2e` | 冒烟，针对示例课程（`COURSE_DIR=examples`）；自起 vite preview 与临时后端（CLI + SQLite），课程目录取自 `GET /api/courses` |
| `npm run e2e:content` | 只跑阅读页地址批量检查；同样自起临时后端（或以 `XT_API` 复用已有后端） |

要点：`src/lib/state.ts` 差分规则；`src/lib/sync.ts` 防抖、离线队列（30 天）、重试、回写；`src/components/CourseFrame.tsx` 嵌入样式注入、路由同步，以及 `engine=static` 课程页的「读完打卡」（`.xt-check[data-id]`）与无引擎页的跟踪项（`input.track`）。

主题色：课程卡与课程根节点设 `--c`（清单 `accent`，只用于色块与装饰）；`--c-l`、`--c-d` 未在清单给出（`accent_light`/`accent_dark`）时由 `xt.css` 用 `color-mix` 派生。按钮文字与白字色底用 `--c-d`。

## 本地联调
```bash
# 用示例课程跑通构建与 e2e（仓库根下的 examples/）；后端用 CLI + 临时 SQLite，不需要 PostgreSQL
(cd ../backend && uv sync --frozen)
npm run build && npm run e2e && npm run e2e:content
```
- e2e（`e2e/backend.cjs`）：在 `../backend` 下以 `uv run --frozen python -m xiaotuo.cli start --courses <COURSE_DIR，默认 examples> --cache-dir <临时目录> --host 127.0.0.1 --port <空闲端口或 XT_PORT> --no-browser` 起临时后端（`DATABASE_URL=sqlite:///<临时目录>/e2e.db`、`XIAOTUO_DATA_DIR=<临时目录>/data`、`RATELIMIT_MULTIPLIER=20`；内容生成、迁移和本机 `COOKIE_SECURE=false` 由 CLI 处理），`/api/courses` 返回 200 即就绪；跑完按进程组 PID 停止并删除临时目录。设置 `XT_API` 时复用已有后端（计分清单目录取 `CONTENT_DIR`）。教材页 `/course/**` 经 vite preview（127.0.0.1）代理到后端。
- 覆盖：登录注册与错误态、首次导入、嵌入样式、同步与重试、换设备回写、退出确认与离线队列、账号隔离、对话框焦点、手机抽屉；示例课程的跟踪项、读完打卡、作答、Boss、毕业、学习中心计分口径（`scored_*`、`tracks_done`），以及阅读页地址批量检查（`e2e/content-check.cjs`）。
- 截图与生成物写到 `e2e/out/`（已忽略）。
- `COOKIE_SECURE=false` 仅用于本地 http 调试，由 CLI 对回环地址自动设置，不写入 `backend/.env`。
