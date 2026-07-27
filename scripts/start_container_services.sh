#!/usr/bin/env bash
set -e

mkdir -p data/logs data/state data/raw data/processed

echo "[CONTAINER] Running GND bootstrap..."
python scripts/bootstrap_gnd.py --auto

echo "[CONTAINER] Starting FastAPI..."
exec uvicorn api.main:app \
  --host 0.0.0.0 \
  --port "${API_PORT:-8083}" \
  --access-log