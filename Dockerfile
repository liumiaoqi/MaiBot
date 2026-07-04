# Stage 1: Extract Python 3.14 runtime from official image
FROM python:3.14-slim-bookworm AS python-builder

# Stage 2: Build on Ubuntu 26.04 LTS
FROM ubuntu:26.04

# Copy Python 3.14 runtime from builder stage
COPY --from=python-builder /usr/local /usr/local
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Proxy support
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY}

# Working directory
WORKDIR /MaiMBot

ENV MAIBOT_LEGACY_0X_UPGRADE_CONFIRMED=1
ENV PATH="/MaiMBot/.venv/bin:${PATH}"

# Copy dependency metadata
COPY pyproject.toml uv.lock ./

# Install C extension build toolchain + git, then install Python dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential libffi-dev libssl-dev libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && uv sync --frozen --no-dev --no-install-project \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Install system libraries required by Playwright Chromium. The browser binary
# itself is downloaded lazily into the configured data directory at runtime.
RUN python -m playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Copy project source
COPY . .

RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

EXPOSE 8000 8001

ENTRYPOINT [ "./docker-entrypoint.sh" ]
