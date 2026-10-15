#!/bin/sh
# MaiBot 容器入口（2026-10-15 重写：原 docker-entrypoint.sh + docker-entrypoint-wrapper.sh 合并）
# 职责：
#   ① OOM 分层保护（ZG-9）—— orchestrator/thinking_organ 豁免；telemetry/emoji_service 优先杀
#   ② Python 版本自愈 —— .venv 版本标记与当前解释器比对，不一致则 uv sync 重建
#   ③ 插件保守启动姿态 —— 除 napcat-adapter 外，启动时将 enabled 置 false
#   ④ exec 主程序
# 已移除（2026-10-15 迁移清理）：
#   · wrapper 的 sed 补丁段 —— AMemorixRelationVectorizationConfig 早已固化进源码
#     official_configs.py（类定义与字段引用均在），原修补段长期走"已含→跳过"空转
#   · wrapper 的 napcat-adapter 去重段 —— v1 挂载 2026-08-18 已删、镜像内不含 plugins/，
#     条件永不触发
set -eu

# === ① ZG-9: OOM 分层保护 ===
setup_oom_protection() {
    if [ ! -d /proc ]; then
        return
    fi

    # 关键进程：OOM score adj = -1000（绝对豁免）
    for proc_name in orchestrator thinking_organ; do
        for pid in $(pgrep -f "$proc_name" 2>/dev/null); do
            echo -1000 > /proc/$pid/oom_score_adj 2>/dev/null
        done
    done

    # 非关键进程：OOM score adj = 1000（优先被杀）
    for proc_name in telemetry emoji_service; do
        for pid in $(pgrep -f "$proc_name" 2>/dev/null); do
            echo 1000 > /proc/$pid/oom_score_adj 2>/dev/null
        done
    done
}

# ZG-9: 启动 OOM 保护（后台延迟执行，等进程启动后）
(sleep 10 && setup_oom_protection) &

# === ② Python version detection & site-packages rebuild ===
mkdir -p /MaiMBot/plugins
PYTHON_VERSION_FILE="/MaiMBot/.venv/.python-version"
CURRENT_PYTHON_MAJOR=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")

if [ -f "$PYTHON_VERSION_FILE" ]; then
    STORED_VERSION=$(cat "$PYTHON_VERSION_FILE" 2>/dev/null || echo "")
else
    STORED_VERSION=""
fi

if [ "$STORED_VERSION" != "$CURRENT_PYTHON_MAJOR" ]; then
    if [ -n "$STORED_VERSION" ]; then
        echo "[entrypoint] 检测到 .venv 的 Python 版本标记为 $STORED_VERSION，当前容器使用 Python $CURRENT_PYTHON_MAJOR，将重新安装依赖"
    else
        echo "[entrypoint] 首次启动或版本标记缺失，将安装依赖并写入版本标记"
    fi
    uv sync --frozen --no-dev
    echo "$CURRENT_PYTHON_MAJOR" > "$PYTHON_VERSION_FILE"
else
    echo "[entrypoint] Python 版本匹配 ($CURRENT_PYTHON_MAJOR)，跳过依赖重建"
fi

# === ③ Disable all plugins except napcat adapter ===
# 注：v2 插件挂载在 /MaiMBot/plugins-v2；本段遍历 /MaiMBot/plugins（当前为空），
#     保留历史行为，待插件体系接线时统一处置
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

# === ④ exec 主程序 ===
exec /MaiMBot/.venv/bin/python bot.py "$@"
