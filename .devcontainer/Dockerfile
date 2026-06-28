FROM mcr.microsoft.com/devcontainers/python:3.14-bookworm

# The base image ships a stale/unreachable Yarn apt source that breaks `apt-get update`; drop it before installing.
# zstd is required by some devcontainer features (e.g. uv) for archive extraction.
# Clean apt caches/lists afterward to keep the final image small.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update && apt-get install -y --no-install-recommends zstd \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*
