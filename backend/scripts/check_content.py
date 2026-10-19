"""id 双向检查：content/items-*.json ↔ 课程页面（静态解析 HTML，不依赖浏览器）。

1) 内容 → 页面：每个 item id 在页面上有对应 data-id；Boss 派生 id（<boss>-sN / -clear / -perfect）
   要求 <boss> 存在且 N ≤ 该 Boss 的 .stage 数。
2) 页面 → 内容：每个交互元素（class 含组件类型或 done-check）的 data-id 都在 items 里；
   Boss 内部的题目（id 以 <boss>- 开头）按 course.js 不单独计分，跳过。
课程由课程根目录（--src，默认 $COURSE_DIR 或 ../course-content）自动发现。
用法：uv run python scripts/check_content.py [--src <课程根目录>] [--content content]；有问题退出码 2。
实现在 xiaotuo/content_build.py；本脚本只是薄壳。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xiaotuo.content_build import check_content  # noqa: E402
from xiaotuo.stdio import utf8_stdio  # noqa: E402


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None)
    ap.add_argument("--content", default=str(Path(__file__).resolve().parent.parent / "content"))
    ap.add_argument("--allow-empty", action="store_true", help="课程根目录存在但没有课程时照样成功（写出空目录，GET /api/courses 返回 []）；默认视为错误")
    a = ap.parse_args()
    return check_content(a.src, a.content, allow_empty=a.allow_empty)


if __name__ == "__main__":
    sys.exit(main())
