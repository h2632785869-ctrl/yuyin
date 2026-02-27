#!/usr/bin/env bash
set -euo pipefail

# 允许通过环境变量覆盖，便于在不同机器复用。
APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8000}"
APP_WORKERS="${APP_WORKERS:-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${SCRIPT_DIR}"

if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

exec uvicorn app:app --host "${APP_HOST}" --port "${APP_PORT}" --workers "${APP_WORKERS}"
