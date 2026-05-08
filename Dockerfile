# Runtime image
FROM python:3.13-slim
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

RUN apt-get update && apt-get install -y git

# Install runtime dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Copy project source
COPY . .

RUN git clone --depth 1 --branch plugin https://github.com/Mai-with-u/MaiBot-Napcat-Adapter.git plugin-templates/MaiBot-Napcat-Adapter
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT [ "./docker-entrypoint.sh" ]
