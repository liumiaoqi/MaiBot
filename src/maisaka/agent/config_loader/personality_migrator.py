"""性格迁移脚本 — 将扁平 personality 文本迁移为四层模型。

幂等：layered_personality 已存在时跳过迁移。
输出新格式到单独文件，不修改原 YAML。
"""

import re

from src.maisaka.agent.config import AgentConfig, LayeredPersonality


# 关系维度规则匹配模式
_RELATION_PATTERN = re.compile(r"对[^\s,，]+(?:[的之][^\s,，]+)?")


def migrate_personality_to_layers(config: AgentConfig) -> LayeredPersonality:
    """将扁平 personality 文本迁移为四层性格模型。

    拆分策略：
    - personality → expression_layer（默认）
    - reply_style → 合并 expression_layer
    - anti_mechanization_rules 全局规则 → self_constraints
    - anti_mechanization_rules 关系维度 → 保留 InternalRelationship.anti_mechanization
    - existence_layer / experience_layer / identity_layer 初始为空

    幂等：layered_personality 已存在时跳过迁移。
    """
    # ── 幂等检查 ──
    if config.layered_personality is not None:
        return config.layered_personality

    expression_parts: list[str] = []
    self_constraints: list[str] = []

    # ── 表现层 ──
    if config.personality.strip():
        expression_parts.append(config.personality.strip())
    if config.reply_style and config.reply_style.strip():
        expression_parts.append(f"回复风格：{config.reply_style.strip()}")

    expression_layer = "；".join(expression_parts) if expression_parts else ""

    # ── 自我约束 ──
    if config.anti_mechanization_rules:
        for rule in config.anti_mechanization_rules:
            text = str(rule).strip()
            if not text:
                continue
            if _is_relation_rule(text):
                continue
            self_constraints.append(text)

    return LayeredPersonality(
        existence_layer="",
        expression_layer=expression_layer,
        experience_layer="",
        identity_layer="",
        self_constraints="；".join(self_constraints) if self_constraints else "",
    )


def _is_relation_rule(text: str) -> bool:
    """判断 anti_mechanization 规则是否为关系维度规则。

    关系维度包含指向性关键词：对XX、与XX、和XX 等。
    """
    return bool(
        _RELATION_PATTERN.search(text)
        or any(kw in text for kw in ("对于", "相处时", "和对方", "与对方"))
    )
