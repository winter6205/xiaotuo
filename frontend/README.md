# frontend

外层前端：React + Vite + TypeScript。课程页以同源 iframe 嵌入；课程列表、顺序、本地存储键、主题色等全部来自课程清单 `course.json`，代码里不写死课程。

| 命令 | 说明 |
|---|---|
| `npm run import` | 从课程根目录 `COURSE_DIR`（相对仓库根，默认 `../course-content`）自动发现课程（每个含 `course.json` 的直接子目录为一门课），校验清单（失败退出码 2），复制页面到 `public/course/<id>/`，生成 `src/data/courses.json`。`CONTENT_DIR` 下有 `items-<id>.json` 时做页面 id 对照；没有时告警跳过，`XT_REQUIRE_ITEMS=1` 时直接失败 |
| `npm run gen:api` | 从 `../api/openapi.yaml`（可用 `OPENAPI` 覆盖）生成 `src/lib/api-types.ts` |
| `npm test` | Vitest（合成数据，不依赖任何课程） |
| `npm run build` | 导入 + 类型检查 + 构建；`XT_BASE` 指定 base 路径 |
| `npm run e2e` | 冒烟，针对示例课程（`COURSE_DIR=examples`）；自起 vite preview 与后端 |
| `npm run e2e:content` | 只跑阅读页地址批量检查（不需要后端） |

要点：`src/lib/state.ts` 差分规则；`src/lib/sync.ts` 防抖、离线队列（30 天）、重试、回写；`src/components/CourseFrame.tsx` 嵌入样式注入、路由同步，以及 `engine=static` 课程页的「读完打卡」（`.xt-check[data-id]`）与无引擎页的跟踪项（`input.track`）。

主题色：课程卡与课程根节点设 `--c`（清单 `accent`，只用于色块与装饰）；`--c-l`、`--c-d` 未在清单给出（`accent_light`/`accent_dark`）时由 `xt.css` 用 `color-mix` 派生。按钮文字与白字色底用 `--c-d`。

## 本地联调
```bash
# 用示例课程跑通构建与 e2e（仓库根下的 examples/）
export COURSE_DIR=examples CONTENT_DIR=$PWD/e2e/out/content
(cd ../backend && uv run python scripts/build_content.py --src ../examples --out "$CONTENT_DIR")
npm run build && npm run e2e
```
- e2e：`XT_PORT ?? PORT`（默认 13773）上后端不可达时，自动在 `../backend` 用 `build_content.py` 从 `COURSE_DIR` 生成计分清单到 `CONTENT_DIR`（默认 `e2e/out/content`），执行 `alembic upgrade head`，再以 `uv run python -m app` 启动（`COOKIE_SECURE=false`、`RATELIMIT_MULTIPLIER=20`，`DATABASE_URL` 未设时用本机 xiaotuo_dev），结束后关闭；已有后端在运行则直接复用（须以同一课程目录启动）。
- 覆盖：登录注册与错误态、首次导入、嵌入样式、同步与重试、换设备回写、退出确认与离线队列、账号隔离、对话框焦点、手机抽屉；示例课程的跟踪项、读完打卡、作答、Boss、毕业、学习中心计分口径（`scored_*`、`tracks_done`），以及阅读页地址批量检查（`e2e/content-check.cjs`）。
- 截图与生成物写到 `e2e/out/`（已忽略）。
- `COOKIE_SECURE=false` 仅用于本地 http 调试，通过环境变量传入，不写入 `backend/.env`。
