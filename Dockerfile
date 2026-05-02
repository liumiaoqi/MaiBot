# Runtime image
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Working directory
WORKDIR /MaiMBot

ENV MAIBOT_LEGACY_0X_UPGRADE_CONFIRMED=1

# Copy dependency list
COPY requirements.txt .

RUN apt-get update && apt-get install -y git

# Install runtime dependencies
RUN uv pip install --system --upgrade pip
RUN uv pip install --system -r requirements.txt

# Copy project source
COPY . .

RUN git clone --depth 1 --branch plugin https://github.com/Mai-with-u/MaiBot-Napcat-Adapter.git plugin-templates/MaiBot-Napcat-Adapter
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT [ "./docker-entrypoint.sh" ]
