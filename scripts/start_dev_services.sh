#!/usr/bin/env bash
set -e

mkdir -p data/logs data/state data/raw data/processed

# Clean up stale lock file from previous runs
if [ -f "data/state/index_build.lock" ]; then
  echo "[START] Removing stale index build lock..."
  rm -f data/state/index_build.lock
fi

echo "[START] Running GND bootstrap..."
python scripts/bootstrap_gnd.py --auto

echo "[START] Checking FastAPI service..."

if pgrep -f "uvicorn api.main:app" > /dev/null; then
  echo "[START] FastAPI is already running."
else
  echo "[START] Starting FastAPI on port 8083..."

  nohup uvicorn api.main:app \
    --host 0.0.0.0 \
    --port 8083 \
    --reload \
    --access-log \
    > data/logs/uvicorn.log 2>&1 &

  echo $! > data/state/uvicorn.pid

  echo "[START] FastAPI started with PID $(cat data/state/uvicorn.pid)"
fi

echo "[START] Done."
echo "[START] OpenRefine service URL:"
echo "http://127.0.0.1:8083"