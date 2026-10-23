#!/usr/bin/env bash
# One-time setup: install deps, create the SQLite DB, load synthetic employees.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# WeasyPrint (PDF reports) loads Homebrew's pango via dlopen.
[ -d /opt/homebrew/lib ] && export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
cd "$ROOT/apps/api"
command -v brew >/dev/null && (brew list pango >/dev/null 2>&1 || brew install pango)
uv sync --python 3.12
uv run alembic upgrade head
for f in employees payroll reviews; do [ -f "$ROOT/seed/$f.csv" ] || { python3 "$ROOT/seed/generate.py"; break; }; done
uv run python -m app.cli seed
cd "$ROOT/apps/web"
npm install
npx playwright install chromium
echo "Setup done. Run ./dev.sh, then open http://localhost:3100 (demo password: unlink-demo)"
