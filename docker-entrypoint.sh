#!/bin/sh
set -e

echo "Initializing data directories..."

mkdir -p \
    /app/data/raw \
    /app/data/processed \
    /app/data/state \
    /app/data/logs \
    /app/data/opensearch

chown -R 1000:1000 /app/data/opensearch || true
chmod -R u+rwX,g+rwX /app/data/opensearch || true

echo "Initialization complete."

exec "$@"