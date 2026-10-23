#!/usr/bin/env bash
# Run every test suite: API (pytest), web unit (Vitest), web smoke (Playwright, isolated DB + ports).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
[ -d /opt/homebrew/lib ] && export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
(cd "$ROOT/apps/api" && uv run pytest -q)
(cd "$ROOT/apps/web" && npm test && npx playwright test)
