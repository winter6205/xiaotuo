---
name: course-authoring
description: 制作或修改可接入小驼的课程时使用。输入一个主题或一份资料，输出仓库外 <COURSE_DIR>/<id>/ 下的课程目录（course.json、章节页面、assets），通过后端校验，并能在小驼运行时课程目录（`GET /api/courses`）中加载。
---

# 课程制作

## 输入与输出

- 输入：一个主题，或一份资料（文档、讲义、笔记）。
- 输出：`<COURSE_DIR>/<id>/` 课程目录，包含 `course.json`、`NN-<章名>.html` 章节页面和 `assets/`。

## 硬规则

- 课程内容只放在仓库外的 `COURSE_DIR` 中，不提交进仓库，也不写入 `examples/`。
- 不修改仓库内任何被跟踪的文件；后端脚本的输出目录（`--out` / `--content`）和 `xiaotuo start` 的 `--cache-dir`、数据库、`XIAOTUO_DATA_DIR` 都指向仓库外的临时目录。`uv` 生成的 `backend/.venv` 是已忽略的生成物，不算修改仓库；要保持工作区干净，可设 `UV_PROJECT_ENVIRONMENT=/tmp/xt-venv` 与 `PYTHONDONTWRITEBYTECODE=1`。
- 已发布课程的计分项 `data-id` 不删除、不改名。

## 步骤

1. **拆章节**：按 [references/authoring-method.md](references/authoring-method.md) 把主题或资料拆成章与页，确定章 id（`00`、`01`…）和每页的小节。
2. **建目录**：`mkdir -p <COURSE_DIR>/<id>`（子目录名建议与课程 id 相同）；需要练习、小测或 Boss 时，复制 `examples/sample-course/assets/` 到课程目录作为引擎。
3. **写页面**：每章一个顶层 `NN-<章名>.html`，从 [references/integration.md](references/integration.md) 4.5 的最小骨架开始。每页必须带 `<html data-key="<storage_key>" data-course="<course_id>">` 和 `<body data-page="<章 id>">`（缺省分别为 `<id>-v<state_version>`、`<id>`），漏写时校验仍通过但进度会静默丢失。`<main>` 末尾依次为 Boss 节、参考资料节、读完打卡 `.xt-check`；`<script src="assets/course.js">` 放在 `</main>` 之后。视觉按 [references/visual-spec.md](references/visual-spec.md)。
4. **加练习、小测、Boss**：计分项 id、Boss 标记、何时引入 `course.js` 见 [references/integration.md](references/integration.md) 第 4 节。
5. **生成 course.json**：字段见 [references/integration.md](references/integration.md) 第 2 节；`engine` 用 `static`，列全 `chapters`，Boss 徽章写入 `badges`。
6. **校验**：执行下方完成标准中的命令，逐条修正报错。完整示例见 [references/walkthrough.md](references/walkthrough.md)。

## 完成标准

以下四步按顺序执行，退出码全部为 0、且第 4 步列出新课程时才算完成。`<课程根目录>` 是包含各课子目录的那一层（`COURSE_DIR`）。命令在 `backend/` 下执行。

```bash
export COURSE_DIR=<课程根目录绝对路径>
export CONTENT_DIR=/tmp/xt-content

cd backend
uv run python scripts/build_content.py --src "$COURSE_DIR" --out "$CONTENT_DIR" --write-cache
uv run python scripts/build_content.py --src "$COURSE_DIR" --out "$CONTENT_DIR"
uv run python scripts/check_content.py --src "$COURSE_DIR" --content "$CONTENT_DIR"
```

第 4 步：用临时数据目录启动小驼，确认新课程出现在运行时课程目录中，然后停止进程。

```bash
XT_TMP=$(mktemp -d)
export XIAOTUO_DATA_DIR="$XT_TMP/data"
uv run python -m xiaotuo.cli start --courses "$COURSE_DIR" --cache-dir "$XT_TMP/content" \
  --database-url "sqlite:///$XT_TMP/xt.db" --no-browser --port 0 > "$XT_TMP/start.log" 2>&1 &
XT_PID=$!
url=""
for _ in $(seq 120); do
  url=$(sed -n 's/^XIAOTUO_READY //p' "$XT_TMP/start.log")
  [ -n "$url" ] && break
  kill -0 "$XT_PID" 2>/dev/null || break
  sleep 0.5
done
echo "READY: ${url:-<未就绪>}"
curl -s "${url}api/courses" | python3 -c 'import json,sys; [print(c["id"], len(c["pages"]), "pages", c["total"], "XP") for c in json.load(sys.stdin)["courses"]]'
kill -INT "$XT_PID"; wait "$XT_PID"; echo "start exit=$?"
rm -rf "$XT_TMP"
```

1. `--write-cache`：仅 `course-manifest-js` 课程需要 node 与 Chrome（`static` 课程不调用浏览器）；`engine=course-manifest-js` 课程在课程目录生成 `.xiaotuo-inventory.json`，`static` 课程不生成缓存。缓存摘要覆盖全部 `*.html`、`assets/course.js`、`assets/course-manifest.js`，课程每次修改后都要重新生成。
2. 不带开关的 `build_content.py`：模拟容器内无浏览器，只读缓存，确认缓存有效。
3. `check_content.py`：计分清单与页面双向校验；第 2、3 步与容器启动时执行的步骤相同。
4. `xiaotuo start`：启动时在进程内重新执行内容生成与双向校验，写出运行时课程目录 `catalog.json`，再迁移数据库并打印 `XIAOTUO_READY <地址>`。用 `GET <地址>api/courses` 确认新课程的 `id` 出现在列表中，`pages` 数等于章数（`engine=static` 时即 `chapters` 的条数），`total` 与第 2 步输出的 XP 一致。停止只按记录的 PID 发送 `SIGINT`，`start exit=0` 表示正常退出；随后删除临时目录。清单或内容有问题时进程以退出码 2 提前结束，`READY` 显示为未就绪，原因写在 `$XT_TMP/start.log`（排查完再删除）。已安装小驼（`uvx xiaotuo` 或 `pipx install xiaotuo`）时，可用 `xiaotuo start` 代替 `uv run python -m xiaotuo.cli start`，参数相同。

`--out` 不要使用默认值（会写入仓库内的 `backend/content`）。无 `uv` 时用 `backend/.venv/bin/python` 代替 `uv run python`。`--database-url` 显式指向临时 SQLite，避免环境变量 `DATABASE_URL` 指向的数据库被迁移或写入。

退出码 2 为清单或内容校验失败，处理方法见 [references/integration.md](references/integration.md) 第 5–7 节。
