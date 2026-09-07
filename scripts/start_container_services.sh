#!/usr/bin/env bash
set -euo pipefail

mkdir -p data/logs data/state data/raw data/processed

# Clean up stale lock files from previous container runs
# In containerized environments, any existing lock is from a crashed/interrupted run
if [ -f "data/state/index_build.lock" ]; then
  echo "[CONTAINER] Removing stale index build lock from previous run..."
  rm -f data/state/index_build.lock
fi

if [ -f "data/state/update.lock" ]; then
  echo "[CONTAINER] Removing stale update lock from previous run..."
  rm -f data/state/update.lock
fi

if [ -f "data/state/getty_index_build.lock" ]; then
  echo "[CONTAINER] Removing stale Getty index build lock from previous run..."
  rm -f data/state/getty_index_build.lock
fi

if [ -f "data/state/getty_update.lock" ]; then
  echo "[CONTAINER] Removing stale Getty update lock from previous run..."
  rm -f data/state/getty_update.lock
fi

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

echo "[CONTAINER] Running Getty bootstrap..."
python -m scripts.bootstrap_getty --auto

if [ "${GETTY_AUTO_UPDATE:-true}" = "true" ]; then
  echo "[CONTAINER] Starting Getty update scheduler..."

  nohup python -m scripts.update_getty_scheduler \
    > data/logs/update_getty_scheduler.log 2>&1 &

  echo $! > data/state/update_getty_scheduler.pid
  echo "[CONTAINER] Getty update scheduler started with PID $(cat data/state/update_getty_scheduler.pid)"
else
  echo "[CONTAINER] Getty update scheduler disabled."
fi

echo "[CONTAINER] Starting FastAPI..."
exec uvicorn api.main:app \
  --host 0.0.0.0 \
  --port "${API_PORT:-8083}" \
  --access-log