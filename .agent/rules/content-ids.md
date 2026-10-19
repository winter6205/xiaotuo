# 题目 id

- 题目 id 只增不删，已发布的 id 不得修改或复用，否则会破坏用户已有的学习进度。
- 新增题目后运行 `python3 scripts/check_ids.py --update`，在本地审阅基线 diff，确认只有新增项。
- 基线 `baseline/course-ids.json` 是本地文件，已被 `.gitignore` 忽略，首次运行自动生成，之后每次运行都与其对比。
