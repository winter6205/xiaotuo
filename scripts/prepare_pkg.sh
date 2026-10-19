#!/usr/bin/env bash
# Prepare packaging: build the frontend, copy the build output and the sample
# courses into backend/xiaotuo/ (both gitignored), and check the LICENSE copy.
# Usage: scripts/prepare_pkg.sh [--skip-frontend]
#   --skip-frontend: do not run npm; reuse an existing frontend/dist (local debugging).
# The work tree must be clean at the end: any non-ignored change makes hatch-vcs
# produce a version with a local suffix, which PyPI rejects.
set -euo pipefail
ROOT=$(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)
PKG="$ROOT/backend/xiaotuo"

if [ "${1:-}" != "--skip-frontend" ]; then
  # The frontend build reads no course directory (the catalog comes from GET /api/courses at runtime)
  ( cd "$ROOT/frontend" && npm ci && env -u COURSE_DIR -u CONTENT_DIR npm run build )
fi
test -f "$ROOT/frontend/dist/index.html" || { echo "frontend/dist/index.html not found" >&2; exit 1; }
test ! -e "$ROOT/frontend/dist/course" || { echo "frontend/dist/course must not exist (course pages are not packaged)" >&2; exit 1; }

rm -rf "$PKG/web" "$PKG/examples"
cp -R "$ROOT/frontend/dist" "$PKG/web"
cp -R "$ROOT/examples" "$PKG/examples"

cmp -s "$ROOT/LICENSE" "$ROOT/backend/LICENSE" || { echo "backend/LICENSE differs from the repository LICENSE" >&2; exit 1; }
if [ -n "$(git -C "$ROOT" status --porcelain)" ]; then
  echo "work tree is not clean; the version would get a local suffix:" >&2
  git -C "$ROOT" status --short >&2
  exit 1
fi
echo "packaging prepared: $PKG/web, $PKG/examples"
