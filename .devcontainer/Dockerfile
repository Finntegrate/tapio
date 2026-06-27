FROM mcr.microsoft.com/devcontainers/python:3.14-bookworm

RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update && apt-get install -y --no-install-recommends zstd \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*
