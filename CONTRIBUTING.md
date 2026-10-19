# 贡献指南

感谢参与小驼。本仓库是 Agent 学习平台的代码；课程内容不进仓库，示例课程位于 `examples/`。

## 提交问题

- 缺陷与功能建议：使用 GitHub Issues 中的模板。
- 安全漏洞：不要公开提交，按 [SECURITY.md](SECURITY.md) 私下报告。

## 开发环境

| 依赖 | 版本 |
|---|---|
| Python | 3.12（由 [uv](https://docs.astral.sh/uv/) 管理） |
| Node.js | 22.12 及以上 |
| PostgreSQL | 13 及以上（后端测试需要可建库的账号） |
| Docker Compose | v2.17 及以上（仅 Docker 方式运行时需要） |

```bash
git clone https://github.com/winter6205/xiaotuo.git && cd xiaotuo
# Docker 方式运行（默认加载 examples/ 示例课程）
cp .env.example .env && docker compose up -d --build
```

Windows 上克隆时建议加 `-c core.symlinks=true`，以保留 `.claude/skills` 软链接。不使用 Docker 的运行方式见 `docs/local-run.md` 附录 B。

## 测试

提交 PR 前在本地通过以下检查（与 CI 一致）：

```bash
# 后端：每次运行新建临时库；数据库地址用 TEST_DATABASE_BASE 或 TEST_DATABASE_URL 指定
cd backend && uv sync && uv run pytest -q

# 前端
cd frontend && npm ci
COURSE_DIR=examples npm run import && npm test
COURSE_DIR=examples npm run build

# 内容检查
COURSE_DIR=examples python3 scripts/check_ids.py
COURSE_DIR=examples python3 scripts/check_links.py
```

改动课程制作 skill 或示例课程时，另按 `.agents/skills/course-authoring/SKILL.md` 的完成标准对 `examples` 跑一遍四步校验。

## 约定

- **密钥**：只放在环境变量中。根目录 `.env`（Docker）与 `backend/.env`（本机运行）均已被忽略，不要提交。
- **题目 id**：已发布的 `data-id` 只增不删，不改名、不复用。
- **数据库迁移**：按 expand-contract 编写，只做向前兼容的改动；`downgrade` 只在 CI 空库中验证。新迁移用 `uv run alembic revision --autogenerate` 生成并人工审阅，`uv run alembic check` 应无差异。
- **数据安全**：不要对存有数据的 compose 项目执行 `docker compose down -v`；另起测试环境时同时设置不同的 `-p` 与 `XT_PG_VOLUME`。
- **Agent 协作**：coding agent 的规则见 `AGENTS.md`，人类贡献者同样适用。

## PR 流程

1. Fork 仓库，从 `main` 建分支。
2. 保持改动聚焦，一个 PR 解决一件事；涉及行为变化时同步更新文档与 `api/openapi.yaml`。
3. 本地通过上文测试后提交 PR，按模板填写说明。
4. CI 全部通过并经维护者审阅后合并。

## 许可证

提交贡献即表示你同意按本仓库的 [MIT 许可证](LICENSE) 授权你的贡献。
