# 小驼部署方案（草案 v0.3）

> 状态：草案。托管平台、数据库、邮件服务按选定方案（Render + Neon + Resend）撰写；托管平台与发信域名待维护者最终确认。标注「待验证」的条目须在预览环境实测后定稿。
> 价格均为 2026-10-18 按官网核实，以下单时控制台为准。

## 1. 部署形态

- 单个 Render Web Service（新加坡区域）同源托管三类内容：外层 SPA（`/`）、教材渲染页（`/course/<课程 id>/`）、API（`/api`）。cookie 不跨站。
- 数据库：Neon PostgreSQL（新加坡区域），生产库与开发库分开（开发库用 Neon 分支）。
- 邮件：Resend HTTP API（不走 SMTP；Render 免费实例封锁 465/587）。
- 单实例运行。限流与会话依赖进程内状态，扩到多实例前须迁至 PG 或 Redis（见方案风险一节）。

## 2. 环境

| 环境 | 托管 | 数据库 | 用途 |
|---|---|---|---|
| local | `docker compose up`（见 `local-run.md`），或 `uv run` + `npm run dev` | compose 内的 postgres:17 | 开发与 M5 验收 |
| ci | GitHub Actions | postgres:16 服务容器 | 迁移、测试、内容检查 |
| preview | Render 免费实例（会休眠） | Neon 开发分支 | 预演 |
| production | Render 常驻实例 | Neon 生产库 | 正式 |

## 3. 费用（首版）

| 项目 | 档位 | 费用 |
|---|---|---|
| Render Web Service | 0.5 CPU / 512 MB 常驻 | 7 美元/月 |
| Neon | Free（100 CU 小时/项目/月，1 GB，PITR 6 小时，空闲 5 分钟暂停） | 0 |
| Resend | Free（3,000 封/月，100 封/日） | 0 |
| 发信域名 | Cloudflare Registrar `.com` | 约 10.46 美元/年，续费同价 |
| 备选：Render PG | 最低档 256 MB，Hobby 档 PITR 3 天 | 6 美元/月（仅在 Neon 冷启动不可接受时启用） |

## 4. 环境变量与密钥

所有密钥只存放于 Render 环境变量与 GitHub Actions Secrets，不进仓库。

| 名称 | 位置 | 说明 |
|---|---|---|
| `DATABASE_URL` | Render、Actions | 可直接粘贴 Neon 控制台原始连接串；`config.py` 的 `normalize_database_url` 自动转换驱动前缀、`sslmode`→`ssl`、删除 `channel_binding`（真连 Neon 待预览环境验证） |
| `SESSION_SECRET` | Render | 会话与 CSRF 签名，随机 32 字节以上 |
| `RATELIMIT_MULTIPLIER` | Render | 限流阈值倍数，生产固定为 `1` |
| `EMAIL_ENABLED` | Render | 发信域名完成 SPF/DKIM 验证前为 `false` |
| `RESEND_API_KEY` | Render | 仅发送权限 |
| `EMAIL_FROM` | Render | 如 `noreply@<发信域名>` |
| `COURSE_REPO` | Actions 变量 | 课程仓库 `owner/name` |
| `COURSE_REF` | 仓库文件 `course.lock` | 固定的课程仓库提交号，CI 构建镜像时使用 |
| `COURSE_DIR` | 镜像 / Render | 课程根目录，运行时读取；镜像默认指向随包的示例课程，云端部署覆盖（见第 5 节） |
| `CONTENT_DIR` | 镜像内 | 生成内容（`courses.json`、`items-<课程 id>.json`、`catalog.json`）所在目录，容器启动时由入口脚本写入 |
| `COURSE_REPO_TOKEN` | Actions | 课程仓库为私有时使用；细粒度只读 token 或 Deploy Key，仅 contents:read |
| `BACKUP_DATABASE_URL` | Actions | 生产库只读角色连接串，供 `pg_dump` |
| `PURGE_DATABASE_URL` | Actions | 具删除权限的角色，供 `purge-events` |
| `BACKUP_AGE_RECIPIENT` / 对象存储凭证 | Actions | 备份加密公钥与 R2/S3 写入凭证 |

## 5. 构建

采用 Dockerfile 多阶段构建，镜像在 GitHub Actions 中构建并推送至 GHCR，Render 只拉取镜像，不在平台上构建。

课程内容在运行时从 `COURSE_DIR` 读取，前端构建产物不含课程数据：课程目录经 `GET /api/courses` 下发，教材页 `/course/**` 由后端直接读取 `COURSE_DIR`。

1. 公开镜像：阶段一 `node:22-slim`（满足 Vite 8 要求的 Node 20.19+/22.12+）执行 `npm ci && npm run build`，生成不含课程的 `dist/`；阶段二运行时镜像执行 `uv sync --frozen`，复制 `dist/` 与后端。镜像只带随包的示例课程，`COURSE_DIR` 默认指向它。
2. 课程目录：云端部署覆盖 `COURSE_DIR`，任选一种方式提供：
   - 挂载：将课程目录放在持久磁盘或卷上，`COURSE_DIR` 指向挂载点；
   - 打入镜像：CI 按 `course.lock`（`vars.COURSE_REF`）检出课程仓库，构建私有派生镜像（`FROM <公开镜像>`，`COPY` 课程目录到 `/course`，`ENV COURSE_DIR=/course`），只推送到私有 GHCR 仓库。`COURSE_REPO_TOKEN` 只在 CI 中使用，不进入镜像层。
3. 启动：容器入口脚本依次从 `COURSE_DIR` 生成计分清单与课程目录（`catalog.json`）、双向校验、执行 `alembic upgrade head`，再启动服务；任一步失败容器退出。`COURSE_DIR` 指向的目录中没有课程时课程列表为空（`GET /api/courses` 返回 200 与 `[]`），不视为错误。

> 不经 Docker、直接运行 `xiaotuo start` 时，未指定 `--courses` 默认使用随包的示例课程，见 `local-run.md` 附录 C。

4. 静态托管规则：先匹配真实静态文件；`/api/**` 交给路由；`/course/**` 与 `/assets/**` 未命中返回 404，不回退；其余路径回退 `index.html`（history 路由）。

`render.yaml` 草案（字段名待按 Render Blueprint 文档核对）：

```yaml
services:
  - type: web
    name: xiaotuo
    runtime: image
    image:
      url: ghcr.io/<owner>/<私有派生镜像>:<sha>   # 挂载课程目录时可直接用公开镜像
    region: singapore
    plan: starter
    # 不设 preDeployCommand / dockerCommand：内容生成与迁移由镜像入口脚本执行
    healthCheckPath: /api/health   # 仅进程存活，不查数据库
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: SESSION_SECRET
        generateValue: true
      - key: EMAIL_ENABLED
        value: "false"
      - key: RESEND_API_KEY
        sync: false
```

## 6. 发布与回滚

- 触发：`master` 合并且 CI 全绿后由 Render 自动部署。CI 作业：backend（PostgreSQL 与 SQLite 各跑一遍，含 `alembic check`）、backend-windows（SQLite）、cli-smoke（`xiaotuo start` 冒烟）、content-checks、frontend-test、frontend-build（build 后执行 `npm run e2e`）。测试与 e2e 使用示例课程（`COURSE_DIR=examples`）。镜像推送作业在工作流首次跑通后加入。
- 迁移：容器入口脚本执行 `alembic upgrade head`；失败则容器退出、健康检查不通过，本次部署不切换流量（待在预览环境实测）。
- 迁移规范：按 expand-contract 编写，仅做向前兼容改动；`downgrade` 只在 CI 空库验证，生产不执行。
- 回滚：Render 回滚到上一版构建（常驻实例保留最近 5 次）。因迁移向前兼容，回滚应用代码不需回滚数据库。
- 教材更新：打入镜像时修改 `course.lock` 提交号，走完整 CI 重建私有派生镜像后发布；挂载时更新卷内课程目录后重启服务。不在 Render 上直接拉取课程仓库最新提交。

## 7. 数据库备份、清理与恢复

工作流 `.github/workflows/backup.yml`，每日一次（UTC 19:00，即 HKT 03:00）：

1. `pg_dump --format=custom` 生产库（只读角色）。
2. 使用 `age` 以公钥加密，上传至平台外对象存储（Cloudflare R2 或 S3），保留 30 天（对象存储生命周期规则）。
3. 第 1、2 步成功后执行 `python -m xiaotuo.cli purge-events --older-than-days 180`，日志记录 `deleted=<n>`；任一步失败则不清理并告警。

恢复演练（每月一次，写入 M6 验收）：在 Neon 临时分支上 `pg_restore` 最近一份备份，运行 `alembic current` 与冒烟查询（用户数、逐题进度行数），记录耗时，演练后删除分支。

Neon 免费档 PITR 仅 6 小时，每日独立备份为必需项。备份含密码哈希与会话，必须加密，私钥离线保存。

## 8. 邮件与域名

1. 在 Cloudflare Registrar 注册发信域名，DNS 托管于 Cloudflare。
2. 在 Resend 添加域名，按其给出的记录配置 SPF、DKIM，并添加 DMARC（初期 `p=none`，观察后收紧）。
3. 验证通过后设置 `EMAIL_ENABLED=true`，用找回密码流程实测送达与垃圾箱判定。
4. 应用首版使用 Render 默认域名；绑定自定义域名时由 Render 自动签发 TLS。服务器位于新加坡，无需 ICP 备案。

## 9. 监控

- Render 健康检查用 `/api/health`（仅进程存活），避免 Neon 冷启动时误判重启。
- 数据库可用性用 `/api/health/ready`（`SELECT 1`，超时 2 秒，失败 503）：外部监控定时探测，发布后冒烟测试必查，失败通知发至维护者邮箱。
- uvicorn 须带 `--proxy-headers`，否则限流取到的是 Render 代理 IP；`--forwarded-allow-ips='*'` 仅在 Render 内网入口下成立，预览环境核对 `X-Forwarded-For` 取值。
- Neon 免费档无消费通知；每月查看 CU 小时用量，接近 100 时评估升级或迁移。
- Resend 每日 100 封上限：找回密码接口按用户与 IP 限流，确保不会触顶。

## 10. 上线前检查清单（M5）

- [ ] CI 全部作业全绿（含受门控作业）；`course.lock` 指向 M0 定稿提交
- [ ] 预览环境：`/course/<课程 id>/` 下页面返回教材 HTML 而非外层页面；子路径深链接、旧锚点、切换页面与课程、模拟终端判题
- [ ] 入口脚本迁移失败时不切流量（实测）
- [ ] 生产环境变量齐全；`SESSION_SECRET` 为生产独立值
- [ ] cookie 为 `Secure; HttpOnly; SameSite=Lax`
- [ ] 首次备份成功并完成一次恢复演练
- [ ] SPF/DKIM 验证通过后才开启 `EMAIL_ENABLED`
- [ ] 发布后 `/api/health/ready` 返回 200，`content_version` 与 `course.lock` 一致
- [ ] 限流按真实客户端 IP 生效（预览环境实测）
- [ ] 回滚演练一次

## 11. 待决事项

1. 维护者确认托管平台（Render）与发信域名购买。账号创建与付款须由维护者本人完成。
2. 课程仓库上线 GitHub 的时间与可见性（决定是否需要 `COURSE_REPO_TOKEN`）。
3. 第 4 节 asyncpg SSL 参数、第 6 节入口脚本迁移失败时的部署行为，在预览环境实测后定稿。
