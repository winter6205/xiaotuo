# Docker 与本地运行

- compose 项目名为 `xiaotuo`，数据保存在数据卷 `xiaotuo-pgdata`。
- 禁止执行 `docker compose down -v`；禁止操作其他 compose 项目的容器、镜像和数据卷。
- 修改 Dockerfile、compose 或构建脚本后，须在干净克隆上执行 `docker compose up -d --build` 验证。
