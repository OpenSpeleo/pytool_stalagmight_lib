FROM python:3.14.0-bookworm

# Keep development tools on the versions maintained by Debian Bookworm.
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    unzip \
    vim \
    nano \
    zsh \
    tmux \
    # cleaning up unused files
    && apt-get clean \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_CACHE_DIR="/workspace/.uv/cache"
