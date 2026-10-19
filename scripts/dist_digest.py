#!/usr/bin/env python3
"""Print a digest of the files in a dist directory (cross-platform).

Usage: python scripts/dist_digest.py <dist dir> [--summary FILE]

The digest is the sha256 of the text "<sha256>  <file name>\\n" for every file,
sorted by name. The release workflow computes it in the build job and checks
it again in every job that downloads the dist artifact.
--summary appends a Markdown block with the per-file sha256 to FILE
(e.g. $GITHUB_STEP_SUMMARY).
"""
import argparse
import hashlib
import sys
from pathlib import Path


def listing(dist: Path) -> str:
    # Only distributions count: uv build also writes dist/.gitignore, and
    # upload-artifact skips hidden files, so other files would break the digest.
    files = sorted(p for p in dist.iterdir()
                   if p.is_file() and p.name.endswith((".whl", ".tar.gz")))
    if not files:
        raise SystemExit(f"no .whl or .tar.gz files in {dist}")
    return "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in files)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dist")
    ap.add_argument("--summary")
    a = ap.parse_args()
    text = listing(Path(a.dist))
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write("### dist sha256\n\n```\n" + text + "```\n")
    sys.stderr.write(text)
    print(hashlib.sha256(text.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
