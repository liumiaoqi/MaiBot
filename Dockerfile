# Stage 1: Extract Python 3.14 runtime from official image
# Pin 具体补丁版本（可复现构建；升级 Python 时手动改此标签，如 3.14.8）
#
# ── 为什么是 3.14.10（2026-11-19 从 3.14.8 升上来）──────────────────
# 升级本身没有问题，但有一个排查陷阱必须记住：
# 容器从启动到 WebUI 在容器内监听 8001 约需 1–2 分钟（A_Memorix 向量库 +
# jieba 词典 + 插件 runner 逐个初始化），这段时间里 connect_ex(8001) 一直是 111，
# 看起来和「启动卡死」一模一样。
# 第一次升的时候就是这样误判的：等 20–30 秒测到 111 就判定失败，反复
# up/restart，反而把启动流程打断，最后错怪成补丁版本的问题回滚了一次。
# ⇒ 判定启动失败的正确判据：等满 2 分钟再测，别按固定秒数猜；
#    或者在容器内轮询 connect_ex 直到 0，而不是 sleep 一个定值。
# ⇒ 旧版镜像保留为 maibot:ubuntu-migration-pre31410 以备回滚。
FROM python:3.14.10-slim AS python-builder

# Stage 2: Build on Ubuntu 26.04 LTS
FROM ubuntu:26.04

# Copy Python 3.14 runtime from builder stage
COPY --from=python-builder /usr/local /usr/local
# Pin uv 版本（可复现构建；升级 uv 时手动改此标签）
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/

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

# apt 源换清华镜像（2026-10-15 迁移补：archive.ubuntu.com 从本网络批量下载持续超时，
# 构建因包下载大面积失败告终；清华实测快 ~6 倍且稳定。Ubuntu 26.04 为 deb822 格式源）
# ⚠️ 必须用 http：此基础镜像内**尚无 ca-certificates**（它就是待装包之一），https 会撞证书验证失败；
#    包完整性由 apt 的 GPG 签名验证保证，与传输加密无关。
RUN sed -i 's|http://archive.ubuntu.com/ubuntu|http://mirrors.tuna.tsinghua.edu.cn/ubuntu|g; s|http://security.ubuntu.com/ubuntu|http://mirrors.tuna.tsinghua.edu.cn/ubuntu|g' /etc/apt/sources.list.d/ubuntu.sources

# Install C extension build toolchain + git, then install Python dependencies.
# 构建期写入 .venv 的 Python 版本标记：entrypoint 以此判断是否需要重建依赖；
# 构建期写好 ⇒ 容器首启免联网执行 uv sync（2026-10-15 迁移补）。
RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential libffi-dev libssl-dev libsqlite3-dev ca-certificates ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && uv sync --frozen --no-dev --no-install-project \
    && echo "$(python3 --version | cut -d' ' -f2 | cut -d. -f1,2)" > /MaiMBot/.venv/.python-version \
    && rm -rf /root/.cache/uv \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Install system libraries required by Playwright Chromium. The browser binary
# itself is downloaded lazily into the configured data directory at runtime.
RUN python -m playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Copy project source
COPY . .

# WebUI 静态资源（**镜像自足**，2026-10-17 publish-image 线补；决策见 .shared/decisions/publish_image_line.md）
# `.dockerignore` 没有排除 `mingtang/dist` ⇒ 上面 `COPY . .` 已经把它带进镜像了（compose L64 的
# `./mingtang/dist:/MaiMBot/mingtang/dist:ro` 在**开发**场景仍可覆盖）。这里只加**构建期断言**：
#   构建上下文里没有前端产物时**立刻失败**，而不是推一个 "healthcheck 永远红" 的镜像出去。
# 判据来源：compose `healthcheck.test = ["CMD","test","-f","/MaiMBot/mingtang/dist/index.html"]`。
RUN test -f /MaiMBot/mingtang/dist/index.html

RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

EXPOSE 8000 8001

ENTRYPOINT [ "./docker-entrypoint.sh" ]
