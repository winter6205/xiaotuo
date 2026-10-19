#!/usr/bin/env python3
"""Check the wheel and sdist in dist/ before publishing.

Usage: python3 scripts/check_dist.py <dist dir> [--expect-version X] [--terms <term list>]

- Files: exactly one xiaotuo wheel and one sdist; with --expect-version the
  file names must carry that version.
- The wheel must contain the frontend build, the migrations
  (xiaotuo/migrations/: alembic.ini, env.py, versions/*.py), the CLI module,
  the sample courses and the common-password list.
- Neither archive may contain .env / .env.*, node_modules, __pycache__ or
  xiaotuo/web/course/.
- Course directory whitelist: a course.json may only appear under
  xiaotuo/examples/; anything else is rejected.
- --terms: optional local term list (fixed strings, case-insensitive). Only for
  local use; CI never passes it. Hits print the file path and count only, never
  the term or its context.
Exit codes: 0 ok; 1 check failed; 2 bad arguments.
"""
import argparse
import re
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

REQUIRED = [
    "xiaotuo/web/index.html",
    "xiaotuo/migrations/alembic.ini",
    "xiaotuo/migrations/env.py",
    "xiaotuo/data/common-passwords.txt",
    "xiaotuo/cli.py",
]
REQUIRED_PATTERNS = [
    r"xiaotuo/migrations/versions/[^/]+\.py",
    r"xiaotuo/examples/[^/]+/course\.json",
]
FORBIDDEN = [
    r"(^|/)\.env$",
    r"(^|/)\.env\.[^/]*$",
    r"(^|/)node_modules/",
    r"(^|/)__pycache__/",
    r"^xiaotuo/web/course/",
]
COURSE_ROOT = "xiaotuo/examples/"


def read_members(path: Path) -> dict[str, bytes]:
    """Return {path inside the package: content}; strips the sdist's top-level xiaotuo-<version>/ dir."""
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as z:
            return {n: z.read(n) for n in z.namelist() if not n.endswith("/")}
    out = {}
    with tarfile.open(path) as t:
        for m in t.getmembers():
            if m.isfile():
                parts = PurePosixPath(m.name).parts[1:]
                out[str(PurePosixPath(*parts))] = t.extractfile(m).read()
    return out


def check(path: Path, files: dict[str, bytes], terms: list[str], is_wheel: bool) -> list[str]:
    errs = []
    names = list(files)
    if is_wheel:
        errs += [f"missing {r}" for r in REQUIRED if r not in files]
        errs += [f"no file matching {p}" for p in REQUIRED_PATTERNS if not any(re.fullmatch(p, n) for n in names)]
    for n in names:
        if any(re.search(p, n) for p in FORBIDDEN):
            errs.append(f"must not contain {n}")
        if PurePosixPath(n).name == "course.json" and not n.startswith(COURSE_ROOT):
            errs.append(f"course directories are only allowed under {COURSE_ROOT}: {n}")
    for n, data in files.items():
        if not terms or b"\0" in data[:8192]:
            continue
        text = data.decode("utf-8", "replace").lower()
        hits = sum(text.count(t) for t in terms)
        if hits:
            errs.append(f"term list: {hits} hit(s) in {n}")
    return [f"{path.name}: {e}" for e in errs]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dist")
    ap.add_argument("--expect-version")
    ap.add_argument("--terms")
    a = ap.parse_args()

    dist = Path(a.dist)
    wheels = sorted(dist.glob("xiaotuo-*.whl"))
    sdists = sorted(dist.glob("xiaotuo-*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        print(f"expected exactly 1 wheel and 1 sdist in {dist}, found {len(wheels)} / {len(sdists)}", file=sys.stderr)
        return 1

    terms: list[str] = []
    if a.terms:
        p = Path(a.terms)
        if not p.is_file() or p.stat().st_size == 0:
            print("term list file missing or empty", file=sys.stderr)
            return 2
        terms = [t.strip().lower() for t in p.read_text(encoding="utf-8").splitlines() if t.strip()]

    errs = []
    if a.expect_version:
        for f in wheels + sdists:
            if not f.name.startswith(f"xiaotuo-{a.expect_version}-") and f.name != f"xiaotuo-{a.expect_version}.tar.gz":
                errs.append(f"{f.name}: version does not match the tag (expected {a.expect_version})")
    errs += check(wheels[0], read_members(wheels[0]), terms, is_wheel=True)
    errs += check(sdists[0], read_members(sdists[0]), terms, is_wheel=False)

    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        print(f"dist check failed: {len(errs)} problem(s)", file=sys.stderr)
        return 1
    print(f"dist check passed: {wheels[0].name}, {sdists[0].name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
