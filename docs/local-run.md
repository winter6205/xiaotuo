# 小驼本地运行说明（Docker）

云端部署见 `deploy.md`。

主线：用 Docker Compose 在 WSL 中运行应用与 PostgreSQL，浏览器在 Windows 侧访问 `http://localhost:13773`；这条路线 WSL 内不需要安装 Node、uv 或 PostgreSQL。个人单机使用不必用 Docker：命令行启动 `xiaotuo start` 即可，默认数据库是本机 SQLite，见附录 C；要在 WSL 内自装 PostgreSQL 运行见附录 B。安装与启动（`uvx` / `uv tool install` / `pipx`）见根目录 README 的「安装与运行」。

## 1. 前提

- Docker Desktop（启用 WSL 集成）或 WSL 内的 Docker Engine，Compose v2（`docker compose version` 核对）。
- 目录：仓库放在 WSL 文件系统内（不要放在 `/mnt/c`、`/mnt/e` 下，挂载与构建会明显变慢）。
- 课程目录：默认使用仓库自带的 `./examples`；加载自己的课程时，修改 `.env` 中的 `CONTENT_HOST_DIR` 为宿主上的课程根目录（相对路径按仓库根解析）。

## 2. 首次启动

```bash
cd xiaotuo                   # 仓库根目录
cp .env.example .env          # 修改 XT_DB_PASSWORD（仅字母数字）
docker compose up -d --build
```

首次构建需要下载镜像与依赖，耗时数分钟。启动顺序：`db` 健康检查通过后启动 `app`，`app` 依次执行 `build_content.py`（生成计分清单）、`check_content.py`（校验）、`alembic upgrade head`，再启动 FastAPI。

在 Windows 浏览器打开 `http://localhost:13773`。`http://localhost:13773/api/health/ready` 返回 200 即数据库已连通；`docker compose ps` 中 `app` 显示 `healthy` 表示同样的检查已通过。

## 3. `.env`（仓库根目录，compose 读取）

| 变量 | 默认 | 说明 |
|---|---|---|
| `XT_DB_PASSWORD` | 无，必填 | 数据库密码，仅容器之间使用 |
| `XT_PORT` | `13773` | 宿主访问端口，只绑定 `127.0.0.1` |
| `CONTENT_HOST_DIR` | `./examples` | 课程目录路径（其下每个带 manifest 的子目录注册为一门课程），运行时只读挂载到 `/course`，构建不读取 |
| `XT_RATELIMIT_MULTIPLIER` | `1` | 限流阈值倍数，反复跑 e2e 时设为 20 |
| `XT_PG_VOLUME` | `xiaotuo-pgdata` | PostgreSQL 数据卷名；同一台机器另起一套环境时必须设置不同的值 |

`EMAIL_ENABLED=false`、`COOKIE_SECURE=false`（本地为 http）、`CONTENT_DIR=content` 已写在 compose 与镜像中，无需配置。`.env` 含密码，已被 `.gitignore` 忽略，不要提交。`backend/.env` 只用于附录 B，Docker 方式不读取它。

## 4. 与其他项目隔离

- 独立的 compose 项目 `xiaotuo`：容器名为 `xiaotuo-db-1`、`xiaotuo-app-1`，不与 fin、iknow 的容器同名，也不复用它们的容器。
- 数据库不对宿主发布端口，只在项目内部网络中以主机名 `db` 访问，不会与宿主上已有的 PostgreSQL 争用 5432。
- 数据存放在独立数据卷，默认 `xiaotuo-pgdata`（`docker volume ls` 可见），可用 `XT_PG_VOLUME` 修改。数据卷名是固定的全局名称，`docker compose -p <其他项目名>` 不会隔离它：另起测试环境时必须同时设置不同的 `XT_PG_VOLUME`，否则会挂载并可能删除同一份数据。
- 应用端口只绑定 `127.0.0.1:13773`，局域网不可访问；端口被占用时修改 `XT_PORT`。

## 5. 日常操作

| 操作 | 命令 |
|---|---|
| 查看状态 | `docker compose ps` |
| 查看日志 | `docker compose logs -f app`（数据库：`logs -f db`） |
| 停止（保留数据） | `docker compose down` 或 `docker compose stop` |
| 再次启动 | `docker compose up -d` |
| 拉取新代码后更新 | `git pull && docker compose up -d --build`（迁移在启动时自动执行） |
| 进入数据库 | `docker compose exec db psql -U xiaotuo xiaotuo` |

教材页（`/course/**`）运行时直接读取只读挂载的课程仓库，修改教材 HTML 后刷新浏览器即可生效。`COURSE_DIR=/course` 下每个含 `course.json` 的直接子目录注册为一门课程，字段说明见 README 与 `examples/sample-course`。容器每次启动时先从课程目录生成计分清单与课程目录数据（`GET /api/courses`）并做双向校验，再执行迁移；镜像构建不读取课程目录。因此新增课程、调整页面结构或 `course.json` 变化时，执行 `docker compose restart app` 即可，不需要重新构建。清单无效、`id` 或 `storage_key` 重复、需浏览器解析的课程缺少有效的 `.xiaotuo-inventory.json` 时，启动以退出码 2 失败并列出问题（`docker compose logs app` 查看）。默认即使用示例课程 `CONTENT_HOST_DIR=./examples`。

## 6. 备份、恢复与清空

备份（输出到宿主当前目录）：

```bash
docker compose exec -T db pg_dump -U xiaotuo -Fc xiaotuo > xiaotuo-$(date +%F).dump
```

恢复：

```bash
docker compose exec -T db pg_restore -U xiaotuo -d xiaotuo --clean --if-exists < xiaotuo-<日期>.dump
```

清空全部数据：`docker compose down -v`。**该命令删除当前 `XT_PG_VOLUME` 指向的数据卷（默认 `xiaotuo-pgdata`），所有账号与学习进度不可恢复，执行前先备份；不要对存有数据的项目执行。** 不带 `-v` 的 `down` 不删除数据。

迁移只有一份基线 `0001_baseline`，新库启动时自动执行。数据库来自开源前的内部版本时，表结构已与基线一致，只需改写版本记录（不改数据，执行前仍建议备份）：`docker compose exec app alembic stamp --purge 0001_baseline`。

## 7. 常见问题

- 启动报找不到课程目录：`CONTENT_HOST_DIR` 路径不存在，或未在仓库根执行 compose。
- 镜像内的版本号：构建时用 `XT_VERSION=<版本> docker compose build` 传入，未传时为 `0.0.0+docker`（`/api/health/ready` 的 `version` 字段）。
- `app` 反复重启：compose 的重启策略为 `unless-stopped`，启动失败会持续重启，不影响数据。用 `docker compose logs app` 查看原因：日志含「没有有效的 .xiaotuo-inventory.json」时，在装有 node 与 Chrome 的环境对该课程运行 `build_content.py --write-cache` 后再启动；清单无效或 id 重复时按日志修正 `course.json`；其余多为迁移失败；修改过 `XT_DB_PASSWORD` 而数据卷是旧密码初始化的，也会认证失败（数据库密码只在数据卷首次创建时生效），改回原密码，或备份后 `down -v` 重建。
- 端口占用（`bind: address already in use`）：修改 `.env` 中的 `XT_PORT` 后 `docker compose up -d`。
- 登录后立即掉线：浏览器经 https 代理或非 localhost 访问时 cookie 行为不同，本地请直接用 `http://localhost:<端口>`。
- 注册或登录返回 429：一小时内请求过多（失败也计数），`docker compose restart app` 清零；反复跑 e2e 时把 `XT_RATELIMIT_MULTIPLIER` 设为 20。

## 8. 改为云端时需要修改的配置

| 项 | 本地 | 云端 |
|---|---|---|
| 运行方式 | `docker compose up`（端口 13773），FastAPI 托管 `dist/` 与 `/api` | Docker 镜像（同样由 FastAPI 托管），Render 运行 |
| 教材页 | 运行时读只读挂载的课程仓库（`COURSE_DIR=/course`） | 构建时打入镜像（`dist/course`），不设 `COURSE_DIR` |
| 迁移 | 容器启动时执行 | Render `preDeployCommand` |
| `DATABASE_URL` | compose 内的 `db` 容器 | Neon 控制台原始连接串（自动转换） |
| `COOKIE_SECURE` | `false` | `true` |
| `RATELIMIT_MULTIPLIER` | `1`（跑 e2e 时 `20`） | `1`，不得调大 |
| `SESSION_SECRET` | 不设置或任意值 | Render 生成的独立随机值 |
| `EMAIL_ENABLED` | `false` | 发信域名 SPF/DKIM 验证通过后改为 `true` |
| `RESEND_API_KEY` / `EMAIL_FROM` | 不设置 | 必填 |
| `CONTENT_DIR` | 镜像内 `content` | 镜像内 `content` |
| 数据迁移 | 本地数据不迁移；如需保留，按第 6 节 `pg_dump` 导出后 `pg_restore` 到 Neon | — |

其余步骤（账号开通、`render.yaml`、备份、域名）见 `deploy.md`。

## 附录 B：不使用 Docker（WSL 内自装 PostgreSQL）

需要自行安装并运行 PostgreSQL（13 及以上），应用经 `scripts/run-local.sh` 启动，读取 `backend/.env`。

### B.1 依赖（WSL 内一次性安装）

| 依赖 | 版本 | 安装方式（WSL 终端） |
|---|---|---|
| Git | 任意 | `sudo apt install -y git` |
| Node.js | 22.12 及以上（Vite 8 要求） | `curl -fsSL https://deb.nodesource.com/setup_22.x \| sudo -E bash - && sudo apt install -y nodejs` |
| uv（含 Python 3.12） | 最新 | `curl -LsSf https://astral.sh/uv/install.sh \| sh`，重开终端后 `uv python install 3.12` |
| PostgreSQL | 已安装版本，13 及以上 | `psql --version` 核对 |

确认：`which node` 应为 `/usr/bin/node`，不能是 `/mnt/c/...`（Windows 的 Node，脚本会拒绝）。

后端未使用 PostgreSQL 17 独有特性（JSONB、INET、部分索引、advisory lock 在 13 及以上均可用）。

### B.2 目录

仓库与课程目录均位于 WSL 文件系统内。脚本与前端构建默认从仓库同级的 `course-content` 读取课程内容，体验示例课程时设 `COURSE_DIR=examples`；位置不同时设置 `COURSE_DIR`（相对路径按仓库根解析）。不要放在 `/mnt/c`、`/mnt/e` 下运行：跨文件系统读写慢，且 Vite 无法可靠监听文件变化。

### B.3 首次初始化

#### B.3.1 PostgreSQL

```bash
sudo service postgresql start          # systemd 已启用时用 sudo systemctl start postgresql
sudo -u postgres psql -c "CREATE USER xiaotuo WITH PASSWORD '<自设密码>';"
sudo -u postgres psql -c "CREATE DATABASE xiaotuo OWNER xiaotuo;"
```

WSL 重启后服务不会自动运行，每次使用前先执行第一条命令（或启用 systemd 后 `sudo systemctl enable postgresql`）。应用与数据库同在 WSL 内，经 `localhost` TCP 连接，无需修改 `listen_addresses`；Ubuntu 默认 `pg_hba.conf` 对 `127.0.0.1` 已使用密码认证。

#### B.3.2 后端

```bash
cd xiaotuo/backend
cp .env.example .env      # 按B.4 节修改
```

迁移与前端构建由 `run-local.sh` 自动执行。

### B.4 本地 `.env`（`backend/.env`）

```
DATABASE_URL=postgresql://xiaotuo:<自设密码>@localhost:5432/xiaotuo
EMAIL_ENABLED=false
CONTENT_DIR=content                  # 真实内容（M1 产出）；跑 fixture 测试时用 tests/fixtures/content
COOKIE_SECURE=false                  # 本地为 http，必须 false；云端必须 true
RATELIMIT_MULTIPLIER=1               # 限流阈值倍数；本地反复跑 e2e 时设为 20
```

`.env` 含密码，已被 `.gitignore` 忽略，不要提交。

### B.5 一条命令启动

```bash
cd xiaotuo
scripts/run-local.sh
```

脚本依次执行：检查依赖、Node 版本与 `backend/.env`，确认 PostgreSQL 已运行，`uv sync`，从 `COURSE_DIR` 生成计分清单（`build_content.py`）并校验（`check_content.py`），`alembic upgrade head`，构建前端（`npm ci` 与 `npm run build`，结果写入 `frontend/dist`），启动 FastAPI。FastAPI 同源提供前端页面、课程页与 `/api`。

在 Windows 浏览器打开 `http://localhost:13773`；`http://localhost:13773/api/health/ready` 返回 200 即数据库已连通。按 `Ctrl+C` 停止。端口默认 13773，可用 `--port <端口>` 或环境变量 `XT_PORT` 修改；开发时 Vite 代理目标用 `XT_API` 同步修改。教材和前端未改动时可加 `--skip-build` 跳过构建。

### B.6 常见问题

- `ready` 返回 503 或迁移报连接失败：
  1. 服务是否在运行：`sudo service postgresql status`。
  2. 能否连上：`psql -h localhost -U xiaotuo xiaotuo`。不能连时检查用户、密码与 `pg_hba.conf` 中 `127.0.0.1/32` 一行是否为 `scram-sha-256` 或 `md5`。
- Windows 浏览器打不开 `localhost:13773`，而 WSL 内 `curl localhost:13773/api/health` 正常：WSL 的 localhost 转发失效。先 `wsl --shutdown` 后重开；仍不行时用 WSL 的 IP（`hostname -I`）访问，并以 `HOST=0.0.0.0 scripts/run-local.sh` 启动。
- 登录后立即掉线：`COOKIE_SECURE` 未设为 `false`。
- 注册或登录返回 429：同一后端进程一小时内请求过多（失败也计数）。重启后端即可清零；反复跑 e2e 时把 `RATELIMIT_MULTIPLIER` 设为 20。
- 本地跑后端测试（`uv run pytest`）：默认用临时 SQLite 文件库，不需要 PostgreSQL。`XT_TEST_DB=postgres uv run pytest` 时每次新建临时库 `xiaotuo_test_<pid>`，需要建库权限。执行 `sudo -u postgres psql -c "ALTER USER xiaotuo CREATEDB;"`；或先建好专用库并设置 `TEST_DATABASE_URL` 指向它。日常使用应用不需要这一步。
- 拉取新代码后：后端 `uv sync` 与 `uv run alembic upgrade head`，前端 `npm ci`。
- 迁移前先备份（开源前内部版本的库对齐方式：`uv run alembic stamp --purge 0001_baseline`，见 `backend/xiaotuo/migrations/versions/0001_baseline.py`）。备份：`pg_dump -h localhost -U xiaotuo -Fc xiaotuo > xiaotuo-$(date +%F).dump`，恢复用 `pg_restore -h localhost -U xiaotuo -d xiaotuo --clean xiaotuo-<日期>.dump`。
- 清空本地数据：`sudo -u postgres psql -c "DROP DATABASE xiaotuo;"`，再执行B.3.1 节建库命令，然后重跑脚本。

## 附录 A：仓库在 Windows 侧（PowerShell）

仅在仓库位于 Windows 盘时使用；数据库仍在 WSL。

1. Windows 侧安装依赖：`winget install Git.Git`、`winget install OpenJS.NodeJS.LTS`、`winget install astral-sh.uv`，之后 `uv python install 3.12`。
2. `copy backend\.env.example backend\.env`，内容同 B.4 节。
3. 启动：`powershell -ExecutionPolicy Bypass -File scripts\run-local.ps1`（参数 `-Port`、`-SkipBuild`）。
4. 连接 WSL 数据库失败时按顺序排查：
   1. Windows 侧端口是否可达：`Test-NetConnection localhost -Port 5432`。
   2. NAT 模式（默认）：`postgresql.conf` 设 `listen_addresses = '*'`，`pg_hba.conf` 加 `host xiaotuo xiaotuo 0.0.0.0/0 scram-sha-256`，重启服务。WSL 默认 `peer` 认证仅适用于 Unix socket。
   3. localhost 转发失效：`DATABASE_URL` 中改用 WSL 的 IP（`hostname -I`，重启后可能变化），`pg_hba.conf` 放行该网段（如 `172.16.0.0/12`）。
   4. 仍不通：`%UserProfile%\.wslconfig` 的 `[wsl2]` 下设 `networkingMode=mirrored`（Windows 11 22H2 及以上），`wsl --shutdown` 后重开，`pg_hba.conf` 放行 `127.0.0.1/32`。

## 附录 C：命令行启动（SQLite，不装数据库）

个人单机使用：数据存在本机 SQLite 文件里，不需要 Docker 或 PostgreSQL。仓库内（`backend/` 下，已 `uv sync`）：

```bash
uv run python -m xiaotuo.cli start                      # 默认示例课程，打开浏览器
uv run python -m xiaotuo.cli start --courses ~/my-courses --port 13773
```

启动时依次：生成课程内容（计分清单与课程目录 `catalog.json`）并校验 → 迁移数据库 → 监听端口 → 输出 `XIAOTUO_READY http://127.0.0.1:<端口>/` 并打开浏览器。端口能连上时 `/api/courses` 已可用。

| 参数 | 默认 | 说明 |
|---|---|---|
| `--courses <目录>` | 随包示例课程（仓库内为 `examples/`） | 课程根目录，每门课一个含 `course.json` 的子目录；为空时课程列表为 `[]` |
| `--cache-dir <目录>` | `<个人数据目录>/content` | 生成内容的存放目录 |
| `--build` / `--no-build` | `--build` | `--no-build` 直接使用已生成的内容 |
| `--host` | `127.0.0.1` | 回环地址时自动 `COOKIE_SECURE=false`；其他地址保留 Secure Cookie 并警告（需 HTTPS 反代） |
| `--port` | `13773` | `0` 为随机空闲端口（实际地址见就绪行） |
| `--no-browser` | — | 就绪后不打开浏览器 |
| `--database-url <URL>` | 环境变量 `DATABASE_URL`，再否则 `<个人数据目录>/xiaotuo.db` | 接受 `sqlite:///路径` 与 `postgresql://…` |
| `--env-file <文件>` | 不读 | 默认**不读**当前目录的 `.env`，需要时显式指定 |

个人数据目录：Linux `~/.local/share/xiaotuo`，macOS `~/Library/Application Support/xiaotuo`，Windows `%LOCALAPPDATA%\xiaotuo`；环境变量 `XIAOTUO_DATA_DIR` 可改。同时给出 `--database-url`（或 `DATABASE_URL`）与 `--cache-dir` 时不会在个人数据目录里创建任何文件。

`engine=course-manifest-js` 的课程须自带与当前内容一致的 `.xiaotuo-inventory.json`（在课程仓库里用 `build_content.py --write-cache` 生成并提交），否则启动报错退出。

清理旧的进度事件日志（逐题进度不受影响）：`uv run python -m xiaotuo.cli purge-events --older-than-days 180 [--dry-run]`。
