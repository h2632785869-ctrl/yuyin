#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

LOG_DIR="${MODEL_API_LOG_DIR:-/tmp/h5_model_apis}"
mkdir -p "${LOG_DIR}"

pkill -f "uvicorn model_apis.voice_design_api:app" || true
pkill -f "uvicorn model_apis.tts_api:app" || true
pkill -f "uvicorn model_apis.env_audio_api:app" || true

nohup uvicorn model_apis.voice_design_api:app --host 127.0.0.1 --port 9101 > "${LOG_DIR}/voice_design.log" 2>&1 &
nohup uvicorn model_apis.tts_api:app --host 127.0.0.1 --port 9102 > "${LOG_DIR}/tts.log" 2>&1 &
nohup uvicorn model_apis.env_audio_api:app --host 127.0.0.1 --port 9103 > "${LOG_DIR}/env_audio.log" 2>&1 &

echo "model APIs started:"
echo "  voice_design: http://127.0.0.1:9101/health"
echo "  tts:          http://127.0.0.1:9102/health"
echo "  env_audio:    http://127.0.0.1:9103/health"
echo "logs: ${LOG_DIR}"
