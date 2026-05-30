#!/bin/sh
set -eu

ADAPTER_TEMPLATE="/MaiMBot/plugin-templates/MaiBot-Napcat-Adapter"
ADAPTER_TARGET="/MaiMBot/plugins/MaiBot-Napcat-Adapter"

mkdir -p /MaiMBot/plugins

if [ ! -e "$ADAPTER_TARGET" ] && [ -d "$ADAPTER_TEMPLATE" ]; then
    cp -a "$ADAPTER_TEMPLATE" "$ADAPTER_TARGET"
fi

<<<<<<< HEAD
# 自动升级核心包到最新版本
uv pip install --python "/MaiMBot/.venv/bin/python" --upgrade maibot-dashboard maibot-plugin-sdk maim-message 2>&1 || true

exec /MaiMBot/.venv/bin/python bot.py "$@"
