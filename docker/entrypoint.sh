#!/bin/sh
# 启动顺序：从课程目录（COURSE_DIR，只读挂载）生成计分清单 → 双向校验 → 迁移 → 启动。
# 任一步失败容器直接退出（docker compose logs app 查看原因）。课程更新后重启容器即可生效。
set -e
python scripts/build_content.py --src "$COURSE_DIR" --out "$CONTENT_DIR"
python scripts/check_content.py --src "$COURSE_DIR" --content "$CONTENT_DIR"
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 13773 --proxy-headers --forwarded-allow-ips='*'
