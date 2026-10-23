#!/usr/bin/env bash
# Start everything for local development. Ctrl+C stops all of it.
#   web         http://localhost:3100
#   API         http://localhost:8000/docs
#   mail viewer http://localhost:8025   (captured email; nothing leaves the machine in development)
#   worker      sends approved notices, retries, escalations, retention sweep, weekly report
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# WeasyPrint (PDF letters and reports) loads Homebrew's pango via dlopen.
[ -d /opt/homebrew/lib ] && export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
trap 'kill 0' EXIT
(cd "$ROOT/apps/api" && uv run uvicorn app.main:app --reload --port 8000) &
(cd "$ROOT/apps/api" && uv run python -m app.worker) &
(cd "$ROOT/apps/api" && uv run uvicorn app.mailview:app --port 8025) &
(cd "$ROOT/apps/web" && npm run dev -- -p 3100) &
wait
