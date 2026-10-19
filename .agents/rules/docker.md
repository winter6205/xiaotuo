# Docker 与本地运行

- 默认 compose 项目名为 `xiaotuo`，数据卷名由 `XT_PG_VOLUME` 决定（默认 `xiaotuo-pgdata`）。数据卷名是全局名称，`-p` 不会隔离它。
- 禁止对存有数据的项目执行 `docker compose down -v`；禁止操作与本项目无关的容器、镜像和数据卷。
- 另起测试环境时，同时设置不同的 `-p`、`XT_PG_VOLUME` 与 `XT_PORT`，启动前用 `docker compose -p <名称> config` 确认数据卷名不是现有数据卷；测试结束后只对该测试项目执行 `down -v`。
- `CONTENT_HOST_DIR` 默认 `./examples`（仓库自带示例课程）；加载真实课程时在 `.env` 中改为宿主上的课程根目录，不把课程内容提交进仓库。
- 修改 Dockerfile、compose 或构建脚本后，须在干净克隆上按上述隔离方式执行 `docker compose up -d --build` 验证。
