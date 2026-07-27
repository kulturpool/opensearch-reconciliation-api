FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    gzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-dev.txt /app/requirements.txt

RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt

COPY api /app/api
COPY importer /app/importer
COPY indexer /app/indexer
COPY scripts /app/scripts
COPY config /app/config

RUN chmod +x /app/scripts/*.sh || true

EXPOSE 8083

CMD ["bash", "scripts/start_container_services.sh"]