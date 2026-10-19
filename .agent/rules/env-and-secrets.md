# 环境变量与密钥

- Docker 运行读取根目录 `.env`（模板 `.env.example`）；本机运行后端读取 `backend/.env`（模板 `backend/.env.example`）。
- 新增配置项时，同步更新对应的 `.env.example`，示例值不得为真实密钥。
- 日志、测试快照和文档中不得出现真实密钥或密码。
