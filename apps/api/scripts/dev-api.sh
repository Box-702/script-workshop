#!/usr/bin/env bash
# Run the FastAPI backend on its own, without the monorepo root.
#
# This is the API-only equivalent of the root scripts/dev-api.ps1.
# It reads .env from the repo root and serves uvicorn on port 8000.
#
# Usage:
#   bash apps/api/scripts/dev-api.sh
#
# Environment overrides (optional):
#   API_PORT       default 8000
#   API_HOST       default 127.0.0.1
#   API_RELOAD     default true
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# Prefer the project's venv interpreter when present, fall back to system
# python3. This matches the Makefile target and the PowerShell sibling.
if [ -x "$REPO_ROOT/apps/api/.venv/bin/python" ]; then
  PY="$REPO_ROOT/apps/api/.venv/bin/python"
else
  PY="${PYTHON:-python3}"
fi
HOST="${API_HOST:-127.0.0.1}"
PORT="${API_PORT:-8000}"
export AUTH_MODE="${AUTH_MODE:-local}"
export DATABASE_URL="${DATABASE_URL:-sqlite:///./data/script-workshop.db}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:3000,http://127.0.0.1:3000}"
RELOAD_FLAG=""
if [ "${API_RELOAD:-true}" != "false" ]; then
  RELOAD_FLAG="--reload"
fi

echo "Starting API with AUTH_MODE=$AUTH_MODE"
echo "Using DATABASE_URL=$DATABASE_URL"

exec "$PY" -m uvicorn app.main:app \
  $RELOAD_FLAG \
  --host "$HOST" \
  --port "$PORT" \
  --app-dir apps/api
