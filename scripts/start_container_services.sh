#!/usr/bin/env bash
set -euo pipefail

mkdir -p data/logs data/state data/raw data/processed

echo "[CONTAINER] Running GND bootstrap..."
python -m scripts.bootstrap_gnd --auto

if [ "${GND_AUTO_UPDATE:-true}" = "true" ]; then
  echo "[CONTAINER] Starting daily update scheduler..."

  nohup python -m scripts.update_scheduler \
    > data/logs/update_scheduler.log 2>&1 &

  echo $! > data/state/update_scheduler.pid
  echo "[CONTAINER] Update scheduler started with PID $(cat data/state/update_scheduler.pid)"
else
  echo "[CONTAINER] Daily update scheduler disabled."
fi

echo "[CONTAINER] Starting FastAPI..."
exec uvicorn api.main:app \
  --host 0.0.0.0 \
  --port "${API_PORT:-8083}" \
  --access-log