"""旧 task_name → capabilities 映射（ZG-12 过渡期兼容层）。

组件自治后任务名不做配置键，只做日志/统计元数据——过渡期内旧调用点
（task_name="planner" 等）通过本映射解析为能力需求后走新路径。
"""

# 11 个配置键 + 2 个配置外键（A_Memorix 域）
TASK_NAME_TO_CAPABILITIES: dict[str, frozenset[str]] = {
    "replyer": frozenset({"text_generation"}),
    "planner": frozenset({"text_generation", "tool_calling"}),
    "utils": frozenset({"text_generation", "tool_calling"}),
    "memory": frozenset({"text_generation"}),
    "mid_memory": frozenset({"text_generation"}),
    "expression_use": frozenset({"text_generation"}),
    "learner": frozenset({"text_generation", "tool_calling"}),
    "emoji": frozenset({"text_generation"}),
    "vlm": frozenset({"vision", "text_generation"}),
    "voice": frozenset({"voice"}),
    "embedding": frozenset({"embedding"}),
    # 配置外键（A_Memorix 域，model_routing 优先级表）
    "lpmm_entity_extract": frozenset({"text_generation", "tool_calling"}),
    "lpmm_rdf_build": frozenset({"text_generation", "tool_calling"}),
}

# 提示可用标签的错误信息（未知 task_name 时）
_KNOWN_TASK_NAMES = sorted(TASK_NAME_TO_CAPABILITIES)


def resolve_legacy_task_name(task_name: str) -> frozenset[str]:
    """将旧 task_name 解析为能力标签集合。

    Args:
        task_name: 旧任务配置名（replyer/planner/utils/...）

    Returns:
        能力标签 frozenset

    Raises:
        ValueError: 未知 task_name（含建议能力标签）
    """
    normalized = (task_name or "").strip()
    if normalized in TASK_NAME_TO_CAPABILITIES:
        return TASK_NAME_TO_CAPABILITIES[normalized]
    raise ValueError(
        f"未注册的模型任务名: {normalized!r}；已知任务名: {_KNOWN_TASK_NAMES}"
    )


def is_known_task_name(task_name: str) -> bool:
    """判断 task_name 是否在映射表中。"""
    return (task_name or "").strip() in TASK_NAME_TO_CAPABILITIES
