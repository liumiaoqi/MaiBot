#!/bin/sh
# MaiBot 自定义入口包装脚本
# 1. 去重 napcat-adapter
# 2. 修补 official_configs.py: 注入 AMemorixRelationVectorizationConfig
#    根因: Pydantic extra=forbid 导致 TOML 中 [a_memorix.retrieval.relation_vectorization] 被丢弃
#    方案: 用 sed 在容器内原文件上精确注入缺失的类定义和字段引用

ADAPTER_A="/MaiMBot/plugins/MaiBot-Napcat-Adapter"
ADAPTER_B="/MaiMBot/plugins/maibot-team_napcat-adapter"

if [ -d "$ADAPTER_A" ] && [ -d "$ADAPTER_B" ]; then
    echo "[wrapper] 检测到重复 napcat-adapter 插件，删除镜像自带版本: $ADAPTER_A"
    rm -rf "$ADAPTER_A"
fi

CFG_FILE="/MaiMBot/src/config/official_configs.py"

if grep -q "AMemorixRelationVectorizationConfig" "$CFG_FILE" 2>/dev/null; then
    echo "[wrapper] official_configs.py 已含 AMemorixRelationVectorizationConfig，跳过"
else
    echo "[wrapper] 修补 official_configs.py ..."

    # 动态查找行号（不硬编码，兼容未来镜像更新）
    # 找 AMemorixRetrievalConfig 类定义行
    CLASS_LINE=$(grep -n "^class AMemorixRetrievalConfig(ConfigBase):" "$CFG_FILE" | head -1 | cut -d: -f1)
    # 找 AMemorixRetrievalConfig 类中 sparse 字段的 docstring 行
    # 从 CLASS_LINE 开始搜索"稀疏检索配置"
    SPARSE_DOC_LINE=$(sed -n "${CLASS_LINE},\$p" "$CFG_FILE" | grep -n "稀疏检索配置" | head -1 | cut -d: -f1)
    SPARSE_DOC_LINE=$((CLASS_LINE + SPARSE_DOC_LINE - 1))

    echo "[wrapper] CLASS_LINE=$CLASS_LINE SPARSE_DOC_LINE=$SPARSE_DOC_LINE"

    if [ -z "$CLASS_LINE" ] || [ -z "$SPARSE_DOC_LINE" ]; then
        echo "[wrapper] ERROR: 未找到插入位置，跳过修补"
    else
        # Step 1: 在 CLASS_LINE 前插入新类定义
        INSERT_BEFORE=$((CLASS_LINE))
        sed -i "${INSERT_BEFORE}i\\
\\
class AMemorixRelationVectorizationConfig(ConfigBase):\\
    \"\"\"A_Memorix 关系向量化配置\"\"\"\\
\\
    enabled: bool = Field(default=False)\\
    \"\"\"为关系生成向量（启用后关系也能参与向量相似检索）\"\"\"\\
\\
    backfill_enabled: bool = Field(default=False)\\
    \"\"\"启用历史关系向量回填任务\"\"\"" "$CFG_FILE"

        # Step 1 插入了9行，SPARSE_DOC_LINE 需要偏移
        SPARSE_DOC_LINE=$((SPARSE_DOC_LINE + 9))

        # Step 2: 在 SPARSE_DOC_LINE 后插入 relation_vectorization 字段
        sed -i "${SPARSE_DOC_LINE}a\\
\\
    relation_vectorization: AMemorixRelationVectorizationConfig = Field(\\
        default_factory=AMemorixRelationVectorizationConfig,\\
    )\\
    \"\"\"关系向量化配置\"\"\"" "$CFG_FILE"

        # 清除 pycache
        rm -rf /MaiMBot/src/config/__pycache__
        echo "[wrapper] 修补完成"
    fi
fi

exec /MaiMBot/docker-entrypoint.sh "$@"
