# 环境变量与密钥

- Docker 运行读取根目录 `.env`（模板 `.env.example`）；本机运行后端读取 `backend/.env`（模板 `backend/.env.example`）。
- 新增配置项时，同步更新对应的 `.env.example`，示例值不得为真实密钥。
- 日志、测试快照和文档中不得出现真实密钥或密码。
- 本地课程路径、个人路径和邮箱只写在被忽略的 `.env` 中，不写入仓库文件；`.env.example` 使用仓库内的相对路径（如 `CONTENT_HOST_DIR=./examples`）。
