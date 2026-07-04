#!/bin/sh
set -eu

mkdir -p /MaiMBot/plugins

# --- Python version detection & site-packages rebuild ---
PYTHON_VERSION_FILE="/MaiMBot/.venv/.python-version"
CURRENT_PYTHON_MAJOR=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")

if [ -f "$PYTHON_VERSION_FILE" ]; then
    STORED_VERSION=$(cat "$PYTHON_VERSION_FILE" 2>/dev/null || echo "")
else
    STORED_VERSION=""
fi

if [ "$STORED_VERSION" != "$CURRENT_PYTHON_MAJOR" ]; then
    if [ -n "$STORED_VERSION" ]; then
        echo "[entrypoint] 检测到 site-packages 命名卷中的 Python 版本为 $STORED_VERSION，当前容器使用 Python $CURRENT_PYTHON_MAJOR，将重新安装依赖"
    else
        echo "[entrypoint] 首次启动或版本标记缺失，将安装依赖并写入版本标记"
    fi
    uv sync --frozen --no-dev
    echo "$CURRENT_PYTHON_MAJOR" > "$PYTHON_VERSION_FILE"
else
    echo "[entrypoint] Python 版本匹配 ($CURRENT_PYTHON_MAJOR)，跳过依赖重建"
fi

# --- Disable all plugins except napcat adapter ---
NAPCAT_ADAPTER_DIR="maibot-team.napcat-adapter"

for plugin_dir in /MaiMBot/plugins/*/; do
    dir_name=$(basename "$plugin_dir")
    if [ "$dir_name" = "$NAPCAT_ADAPTER_DIR" ]; then
        continue
    fi

    config_file="$plugin_dir/config.toml"
    if [ ! -f "$config_file" ]; then
        continue
    fi

    # Check if [plugin] section exists and enabled is already false
    if grep -q '^\[plugin\]' "$config_file" 2>/dev/null; then
        if grep -A1 '^\[plugin\]' "$config_file" | grep -q 'enabled.*=.*false'; then
            continue
        fi
        # Set enabled = false in [plugin] section
        sed -i '/^\[plugin\]/,/^\[/{ s/^enabled\s*=\s*true/enabled = false/; }' "$config_file"
        echo "[entrypoint] 已禁用插件: $dir_name"
    fi
done

exec /MaiMBot/.venv/bin/python bot.py "$@"
