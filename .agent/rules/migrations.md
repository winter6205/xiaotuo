# 数据库迁移

- 使用 Alembic，迁移按 expand-contract 编写：先加新结构并兼容旧代码，再在后续版本移除旧结构。
- `downgrade` 仅在 CI 空库中验证，生产环境不执行。
- 容器启动时入口脚本会执行 `alembic upgrade head`，迁移必须可在已有数据上安全运行。
