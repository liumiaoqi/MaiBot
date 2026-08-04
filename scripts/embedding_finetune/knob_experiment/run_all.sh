#!/usr/bin/env bash
# 旋钮实验一键跑：训练 → 可视化 → 手动调参。
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN="python3"
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "未找到 python/python3，请先安装 Python，并确认 torch/matplotlib 可用" >&2
    exit 1
fi

"$PYTHON_BIN" train_track.py
"$PYTHON_BIN" visualize.py
"$PYTHON_BIN" manual_tune.py
