#!/bin/sh
set -eu

ADAPTER_TEMPLATE="/MaiMBot/plugin-templates/MaiBot-Napcat-Adapter"
ADAPTER_TARGET="/MaiMBot/plugins/MaiBot-Napcat-Adapter"

mkdir -p /MaiMBot/plugins

if [ ! -e "$ADAPTER_TARGET" ] && [ -d "$ADAPTER_TEMPLATE" ]; then
    cp -a "$ADAPTER_TEMPLATE" "$ADAPTER_TARGET"
fi

exec python bot.py "$@"
