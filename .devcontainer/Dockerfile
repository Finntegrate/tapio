FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends zstd \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*
