FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y \
    curl \
    wget \
    jq \
    unzip \
    zip \
    gzip \
    tar \
    sqlite3 \
    tree \
    vim \
    less \
    git \
    httpie \
    netcat-openbsd \
    libxml2-utils \
    xsltproc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*