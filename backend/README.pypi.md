# 小驼（xiaotuo）

小驼是一个 Agent 学习平台：Agent 调用课程制作 skill 生成互动课程，小驼负责加载课程、呈现页面并记录学习进度（读完打卡、经验值、连续学习天数、徽章、个人学习中心）。本包包含后端、前端构建产物与一门示例课程，不含其他课程内容。

- 源码与完整说明：<https://github.com/winter6205/xiaotuo>
- 许可证：MIT（<https://github.com/winter6205/xiaotuo/blob/main/LICENSE>）

## 安装与启动

需要 Python 3.12 及以上。推荐用 [uv](https://docs.astral.sh/uv/) 或 [pipx](https://pipx.pypa.io/)：

```bash
uvx xiaotuo start                       # 使用随包示例课程
uvx xiaotuo start --courses ./my-courses
# 或
pipx install xiaotuo
xiaotuo start --courses ./my-courses
```

启动后在浏览器打开终端里显示的地址（默认 `http://127.0.0.1:13773`）。常用参数：

| 参数 | 说明 |
|---|---|
| `--courses <目录>` | 课程根目录：其中每个含 `course.json` 的直接子目录是一门课程；不传时使用随包示例课程 |
| `--port <端口>`、`--host <地址>` | 监听端口与地址，默认 `127.0.0.1:13773` |
| `--no-browser` | 启动后不自动打开浏览器 |

完整参数以 `xiaotuo start --help` 为准。修改课程内容后重启 `xiaotuo start` 生效。

## 数据存放

- 默认使用 SQLite，数据库文件位于用户数据目录下的 `xiaotuo.db`（Linux 为 `~/.local/share/xiaotuo/`，macOS 为 `~/Library/Application Support/xiaotuo/`，Windows 为 `%LOCALAPPDATA%\xiaotuo\`）。
- 设置环境变量 `DATABASE_URL` 可改用 PostgreSQL（13 及以上），例如 `postgresql://用户:密码@主机:5432/库名`。
- 多人共用或需要长期运行时，建议使用 Docker 方式：<https://github.com/winter6205/xiaotuo/blob/main/docs/local-run.md>

## 制作课程

- 课程格式与示例：<https://github.com/winter6205/xiaotuo/tree/main/examples/sample-course>
- 课程制作 skill（供 Claude Code、Cursor、Codex 等 Agent 使用）：<https://github.com/winter6205/xiaotuo/blob/main/.agents/skills/course-authoring/SKILL.md>
- 使用 `course-manifest-js` 引擎的课程需要预先生成 `.xiaotuo-inventory.json`，详见上面的 skill 说明。

## 问题反馈

- Issues：<https://github.com/winter6205/xiaotuo/issues>
- 安全问题：<https://github.com/winter6205/xiaotuo/blob/main/SECURITY.md>
