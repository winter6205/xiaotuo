# 小驼学习 后端

FastAPI + SQLAlchemy async/asyncpg + Alembic。接口以 `../api/openapi.yaml`（v0.4.0）为准。

```bash
uv sync
uv run alembic upgrade head
uv run python scripts/build_content.py --src ../examples   # 生成 content/（示例课程）
uv run uvicorn xiaotuo.main:app --reload
# 测试用 XT_TEST_DB 选库：默认 sqlite（临时文件库，结束后删除，不需要 PostgreSQL）；
# XT_TEST_DB=postgres 需要本机 PostgreSQL（postgres 用户可建库）：每次运行新建临时库 xiaotuo_test_<pid>，结束后自动删除；
# 两种都可设 TEST_DATABASE_URL 改用指定库。会先对空库跑 upgrade → downgrade base → upgrade
uv run pytest -q
XT_TEST_DB=postgres uv run pytest -q
```

- 内容数据：`CONTENT_DIR/courses.json`（每门课含 `dir`、`order`、`state_version` 等字段）+ `items-<课程 id>.json`，格式见 `xiaotuo/content.py` 文档串；测试用 `tests/fixtures/content/`。
  生成：`uv run python scripts/build_content.py --src <课程根目录>`，输出到 `content/`；随后 `uv run python scripts/check_content.py --src <课程根目录>` 做 items ↔ 课程页 id 双向检查。清单无效、id 或 storage_key 重复、校验不一致时退出码 2。
  需要无头浏览器解析计分项的课程引擎读取课程目录中的 `.xiaotuo-inventory.json` 缓存；缓存缺失或与内容不一致时，在装有 node 与 Chrome 的环境运行 `build_content.py --write-cache` 重新生成（仅此参数会写入课程目录）。`static` 引擎不需要缓存。
- 未知课程的进度接口返回 404 `course_not_found`。
- 迁移只有一份基线 `0001_baseline`：三张进度表的课程 id 只约束格式。开源前内部版本的库用 `uv run alembic stamp --purge 0001_baseline` 对齐，不改数据。
- 限流：进程内滑动窗口（`xiaotuo/ratelimit.py`），单实例有效；客户端 IP 取 `request.client.host`，Render 后面需 `uvicorn --proxy-headers --forwarded-allow-ips='*'`。
- 弱密码表：`xiaotuo/data/common-passwords.txt`，取自 SecLists（MIT）10k + xato 100k 中长度 10–128 的条目，小写比较。
- 找回密码：`EMAIL_ENABLED=false` 时两接口返回 503；为 true 时 token 流程已实现，发信（Resend）留到 M5，当前 `send_reset_email` 只记日志。

## 已定规则

以下规则已写入 `api/openapi.yaml`：

1. 限流补充：重置密码确认 10 次/IP/小时；导入 30 次/用户/分钟；账号级清空 10 次/用户/小时。
2. 事件接口请求体上限 1 MB（413）。
3. 事件 `course` 与路径不一致：单条 `rejected/course_mismatch`，不整批 400。
4. 导入 `version` 错误返回 422（与 course 不符相同）。
5. `GET /api/dashboard?tz=Asia/Hong_Kong`：按 IANA 时区算「今天」，缺省 UTC，无效 400。依赖 `tzdata`，Windows 上 zoneinfo 也可用。
6. 邮箱不用 citext：trim + 小写后存 text，唯一索引。
7. 会话固定 30 天过期，不滑动续期。
8. `EMAIL_ENABLED` 默认 false；生产环境显式设 true。

## 同源托管前端与教材页（本地运行）

前端产物（`XT_FRONTEND_DIST` 或 `FRONTEND_DIST` 指定；否则随包的 `xiaotuo/web/`，仓库内开发为 `../frontend/dist`）由 FastAPI 直接托管（`xiaotuo/static.py`），规则同 `docs/deploy.md` 第 4 条：

- 先匹配真实文件（目录取其 `index.html`）；课程页在 `dist/course/<课程 id>/`，由前端构建从 `public/course` 复制；设置 `COURSE_DIR` 时 `/course/<课程 id>/` 直接读课程目录。
- `/api/**` 不回退：未知接口返回 JSON 404（problem+json）。
- `/course/**`、`/assets/**` 未命中返回 404，不回退。
- 其余 GET/HEAD 回退 `index.html`（SPA 路由）。
- `index.html` 和教材页 `Cache-Control: no-cache`；`/assets/` 带哈希文件 `max-age=31536000, immutable`。
- dist 不存在时照常启动，只提供 API，并记一条 warning。

```bash
cd ../frontend && COURSE_DIR=/path/to/course-content npm run build
cd ../backend && uv run python -m xiaotuo   # 默认 127.0.0.1:13773，可用 PORT、HOST 覆盖；打开 http://localhost:13773/
```

注意：Cookie 带 `Secure`，浏览器只在 https 或 `localhost` 下发送；用局域网 IP 的 http 访问时需设 `COOKIE_SECURE=false`。
