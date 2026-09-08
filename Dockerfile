# =============================================================================
# Production Dockerfile für GND Reconciliation API
# =============================================================================
# Dieses Dockerfile ist für Production/Runtime optimiert.
# Für Entwicklung bitte .devcontainer/Dockerfile verwenden!

# -----------------------------------------------------------------------------
# Stage 1: Builder - Dependencies installieren
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Build-Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Python-Dependencies in separatem Layer
COPY requirements-dev.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --user -r /tmp/requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: Runtime - Minimales Production Image
# -----------------------------------------------------------------------------
FROM python:3.12-slim

# Metadata
LABEL maintainer="Kulturpool"
LABEL description="OpenSearch Reconciliation API for GND and Getty Vocabularies"

# Python-Environment optimieren
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH=/root/.local/bin:$PATH

# Arbeitsverzeichnis
WORKDIR /app

# Runtime-Dependencies (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python-Packages aus Builder-Stage kopieren
COPY --from=builder /root/.local /root/.local

# Application Code kopieren
COPY api /app/api
COPY importer /app/importer
COPY indexer /app/indexer
COPY scripts /app/scripts
COPY config /app/config

# Skripte ausführbar machen
RUN chmod +x /app/scripts/*.sh 2>/dev/null || true

# Health Check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${API_PORT:-8083}/status/update || exit 1

# API Port exponieren
EXPOSE 8083

# Startup-Skript ausführen
CMD ["bash", "scripts/start_container_services.sh"]