"""内容导入：从课程根目录（COURSE_DIR）自动发现课程，生成 courses.json + items-<id>.json + catalog.json。

用法（在 backend/ 下）：
    uv run python scripts/build_content.py [--src <课程根目录>] [--out content] [--write-cache]
--src 默认取环境变量 COURSE_DIR，再默认仓库同级的 ../course-content。
实现在 xiaotuo/content_build.py（随包分发，xiaotuo start 进程内调用）；本脚本只是 Docker / CI / 本地用的薄壳。
任一不一致即失败（退出码 2）。
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from xiaotuo.content_build import INVENTORY_CACHE, build_content  # noqa: E402
from xiaotuo.stdio import utf8_stdio  # noqa: E402


def main() -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None, help="课程根目录，默认 $COURSE_DIR 或 ../course-content")
    ap.add_argument("--out", default=str(HERE.parent / "content"))
    ap.add_argument("--write-cache", action="store_true",
                    help=f"engine=course-manifest-js：用浏览器重新生成清单并写入课程目录的 {INVENTORY_CACHE}")
    ap.add_argument("--allow-empty", action="store_true", help="课程根目录存在但没有课程时照样成功（写出空目录，GET /api/courses 返回 []）；默认视为错误")
    a = ap.parse_args()
    return build_content(a.src, a.out, write_cache=a.write_cache, allow_empty=a.allow_empty)


if __name__ == "__main__":
    sys.exit(main())
