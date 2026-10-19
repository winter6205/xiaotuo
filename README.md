# 小驼

![小驼](docs/images/banner.png)

<sub>横幅中的 🦙 来自 [Noto Color Emoji](https://github.com/googlefonts/noto-emoji)（SIL Open Font License 1.1）。</sub>

小驼是一个 Agent 学习平台。Agent 调用课程制作 skill，在学习空间里生成互动课程，帮助使用者学习任何主题。仓库只包含平台代码，不含课程内容。

## 平台是什么

学习空间负责加载课程、呈现页面并记录学习过程：

- 账号：注册、登录、退出，会话基于 Cookie 与 CSRF 防护，带接口限流。
- 课程阅读：课程目录、上一页 / 下一页导航，移动端目录抽屉。
- 学习进度：读完打卡、经验值（XP）、连续学习天数与徽章；离线时操作先写入本地队列，联网后同步。
- 个人学习中心：总进度、最近学习记录、本地进度导入，以及需二次确认的进度重置。

| 部分 | 技术 |
|---|---|
| 后端 | FastAPI、SQLAlchemy（async）、Alembic、PostgreSQL 13 及以上，uv 管理依赖 |
| 前端 | React、Vite、TypeScript，构建产物由后端同源托管 |
| 接口契约 | OpenAPI v0.2.2，见 `api/openapi.yaml` |
| 测试 | 后端 pytest（每次运行使用独立临时库）；前端单元测试与端到端测试 |

目录：`backend/` 后端服务与迁移，`frontend/` 前端与端到端测试，`api/` 接口契约，`scripts/` 课程内容检查与启停脚本，`docs/` 本地运行与部署文档，`examples/` 示例课程。

## 工作方式

1. **生成课程**：Agent 按课程制作 skill 设计教学方案，写出自包含的 HTML 课程页面和清单 `course.json`，放在仓库外的课程目录 `COURSE_DIR` 中，每门课一个子目录。
2. **校验内容**：Agent 运行 skill 规定的构建与校验命令，全部返回 0 才算完成。清单无效、id 重复或清单缓存失效时，构建与启动均以退出码 2 失败并列出原因。
3. **加载学习**：学习空间启动时注册课程目录下的全部课程，以 `/course/<id>/` 提供阅读；使用者答题、打卡、挑战 Boss 关，进度与 XP 写入数据库并跨设备同步。

## 课程制作

制作或修改课程见 [课程制作 skill](.agents/skills/course-authoring/SKILL.md)，其中包括写课方法、视觉规范、清单字段与接入命令，以及基于 [`examples/sample-course`](examples/sample-course) 的完整走查。测试与 CI 使用示例课程：`COURSE_DIR=examples`。

## 本地运行

推荐用 Docker Compose 运行（Compose v2.17 及以上），应用和自带的 PostgreSQL 容器一起启动，本机不需要安装 Node、uv 或 PostgreSQL。默认加载仓库自带的示例课程 `examples/`：

```bash
git clone https://github.com/winter6205/xiaotuo.git && cd xiaotuo
cp .env.example .env          # 修改 XT_DB_PASSWORD（仅字母数字）
docker compose up -d --build
```

浏览器打开 `http://localhost:13773`。加载自己的课程时，把 `.env` 中的 `CONTENT_HOST_DIR` 改为宿主上的课程根目录。完整步骤见 [`docs/local-run.md`](docs/local-run.md)。

> **数据安全**：`docker compose down -v` 会删除数据卷及全部账号与学习进度，不要对存有数据的项目执行。数据卷名由 `XT_PG_VOLUME` 决定（默认 `xiaotuo-pgdata`），`-p` 不会隔离它；同一台机器另起一套环境时，先设置不同的 `XT_PG_VOLUME`。

不使用 Docker 时，课程目录由 `COURSE_DIR` 指定（默认仓库同级的 `../course-content`，体验示例可设 `COURSE_DIR=examples`）。

不使用 Docker 时需自行安装 PostgreSQL 13 及以上（见 `docs/local-run.md` 附录 B），简要命令：

```bash
cd frontend && npm ci && npm run build
cd ../backend && uv sync && uv run alembic upgrade head
uv run python -m app        # http://127.0.0.1:13773
```

快捷启停：

```bash
echo "alias xiaotuo='<仓库路径>/scripts/xiaotuo.sh'" >> ~/.bashrc && source ~/.bashrc
xiaotuo start    # 启动并打开浏览器
xiaotuo stop     # 停止（保留数据）
xiaotuo restart  # 重启容器
xiaotuo status   # 查看容器状态
xiaotuo logs     # 查看应用日志
```

云端部署方案见 [`docs/deploy.md`](docs/deploy.md)。参与开发见 [CONTRIBUTING.md](CONTRIBUTING.md)，安全问题见 [SECURITY.md](SECURITY.md)。Windows 上克隆时建议 `git clone -c core.symlinks=true`，以保留 `.claude/skills` 软链接。

## 许可证

[MIT](LICENSE)
