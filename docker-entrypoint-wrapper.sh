#!/bin/sh
# MaiBot 自定义入口包装脚本
# 解决：docker-entrypoint.sh 自动从模板复制 MaiBot-Napcat-Adapter，
# 而 WebUI 安装的 maibot-team_napcat-adapter 与之同ID，
# 导致 IPC 插件系统检测到重复插件ID后拒绝启动整个插件运行时。
# 方案：入口脚本执行后，检测并删除重复的 napcat-adapter。

# 执行原始入口脚本（后台不阻塞，或直接 exec）
# 由于原入口脚本末尾是 exec，我们在这里做前置去重后直接 exec 原脚本

ADAPTER_A="/MaiMBot/plugins/MaiBot-Napcat-Adapter"
ADAPTER_B="/MaiMBot/plugins/maibot-team_napcat-adapter"

# 如果两个目录同时存在，删除镜像自带的那份（没有用户配置）
if [ -d "$ADAPTER_A" ] && [ -d "$ADAPTER_B" ]; then
    echo "[wrapper] 检测到重复 napcat-adapter 插件，删除镜像自带版本: $ADAPTER_A"
    rm -rf "$ADAPTER_A"
fi

# 执行原始入口脚本
exec /MaiMBot/docker-entrypoint.sh "$@"
