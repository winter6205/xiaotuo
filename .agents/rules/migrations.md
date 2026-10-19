# 数据库迁移

- 使用 Alembic，迁移链从基线 `0001_baseline` 开始（`backend/xiaotuo/migrations/versions/0001_baseline.py`），新迁移以它为祖先，用 `uv run alembic revision --autogenerate` 生成并人工审阅，`uv run alembic check` 应无差异。
- 迁移按 expand-contract 编写：先加新结构并兼容旧代码，再在后续版本移除旧结构。
- 课程 id 由课程清单决定，数据库只约束 id 格式；新增课程不需要新迁移，迁移中不得写入具体课程 id。
- 开源前内部版本的数据库（旧 revision `0003`）表结构与基线一致，只改版本记录对齐：先 `pg_dump` 备份，再执行 `alembic stamp --purge 0001_baseline`（Docker 下为 `docker compose exec app alembic stamp --purge 0001_baseline`，须在新镜像中执行）。不得用 `down -v` 重建来代替。
- `downgrade` 仅在 CI 空库中验证，生产环境不执行。
- 容器启动时入口脚本会执行 `alembic upgrade head`，迁移必须可在已有数据上安全运行。
