# AGENTS.md

小驼是一个 Agent 学习平台：Agent 调用课程制作 skill，在学习空间里生成互动课程，帮助使用者学习任何主题。

本文件供 coding agent 读取。人类贡献者请先阅读 `CONTRIBUTING.md`，本文件的规则与其一致。

## 项目结构

- `backend/`：FastAPI 后端，Alembic 迁移，pytest 测试。
- `frontend/`：前端，构建时由 `scripts/import-course.mjs` 导入课程内容。
- `scripts/`：校验与本地启停脚本。
- `docs/`：本地运行与部署文档。

## 必须遵守

- 详细规则见 `.agents/rules/`（content-ids、docker、env-and-secrets、migrations），修改相关代码前先读对应文件。
- 不提交任何 `.env` 文件或密钥。
- 不删除、不修改已有题目 id。
- 不编写生产环境依赖 `downgrade` 的迁移。
- 不对存有数据的 compose 项目执行 `docker compose down -v`；另起测试环境时同时设置不同的 `-p` 与 `XT_PG_VOLUME`。不操作与本项目无关的容器和数据卷。
- 制作或修改课程时，按 `.agents/skills/course-authoring/SKILL.md` 执行（Codex、Cursor 从 `.agents/skills` 自动发现，Claude Code 经 `.claude/skills` 软链接发现）；课程内容只放在仓库外的 `COURSE_DIR`，不提交进仓库。

## 提交前检查

- 后端：在 `backend/` 中运行 `uv run pytest -q`（需要可建库的 PostgreSQL）。
- 前端：在 `frontend/` 中运行 `npm test` 与 `npm run build`（`COURSE_DIR=examples`）。
- 涉及构建或 Docker 的改动，须在干净克隆上验证。
