"""LS-7 工具: adjust_expression — 调整表现层或体验层性格"""

from typing import Optional

from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec
from src.maisaka.agent.config import PersonalityLayer

from .context import BuiltinToolRuntimeContext


def get_tool_spec() -> ToolSpec:
    """获取 adjust_expression 工具声明。"""

    return ToolSpec(
        name="adjust_expression",
        description="调整性格的表现层或体验层文本。存在层和认同层不可直接修改。",
        parameters_schema={
            "type": "object",
            "properties": {
                "layer": {
                    "type": "string",
                    "description": "性格层：expression（表现层，外显行为）/ experience（体验层，内心感受）",
                    "enum": ["expression", "experience"],
                },
                "modification": {
                    "type": "string",
                    "description": "修改描述文本",
                },
            },
            "required": ["layer", "modification"],
        },
        provider_name="maisaka_builtin",
        provider_type="builtin",
    )


async def handle_tool(
    tool_ctx: BuiltinToolRuntimeContext,
    invocation: ToolInvocation,
    context: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    """执行 adjust_expression 内置工具。

    参数: layer ("expression" | "experience"), modification: str
    """
    del context

    layer_raw = str(invocation.arguments.get("layer", "")).strip().lower()
    modification = str(invocation.arguments.get("modification", "")).strip()

    if not layer_raw:
        return tool_ctx.build_failure_result(invocation.tool_name, "需要提供 layer 参数（expression / experience）")
    if not modification:
        return tool_ctx.build_failure_result(invocation.tool_name, "需要提供 modification 参数")

    match layer_raw:
        case "existence":
            return tool_ctx.build_failure_result(
                invocation.tool_name,
                "存在层不可修改——这是角色的世界设定，不是可变的性格特征。",
            )
        case "identity":
            return tool_ctx.build_failure_result(
                invocation.tool_name,
                "认同层不可直接修改。如需反思自我认知，请使用 reflect_on_self 工具。",
            )
        case "expression":
            layer = PersonalityLayer.EXPRESSION
        case "experience":
            layer = PersonalityLayer.EXPERIENCE
        case _:
            return tool_ctx.build_failure_result(
                invocation.tool_name,
                f"不支持的性格层：{layer_raw}。可选：expression / experience",
            )

    # 获取智能体配置
    from src.core.adapters.agent_config_port import get_agent_config_provider

    agent_id, _ = tool_ctx.resolve_speaker_context()
    if not agent_id:
        return tool_ctx.build_failure_result(invocation.tool_name, "无法解析当前发言智能体")

    registry = get_agent_config_provider()
    agent_config = registry.get_agent(agent_id)

    if agent_config.layered_personality is None:
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "当前智能体未启用分层性格模型（layered_personality 为空）。",
        )

    # 获取交互计数
    from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager

    relationship_manager = AgentRelationshipManager()
    interaction_count = 0
    try:
        all_agents = registry.list_agents()
        for target in all_agents:
            if target.agent_id == agent_id:
                continue
            rel = await relationship_manager.get_relationship(agent_id, target.agent_id)
            if rel is not None:
                interaction_count += rel.interaction_count
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "获取交互次数失败，使用 0", exception=exc)
        interaction_count = 0

    # 计算可塑性
    from src.maisaka.agent_autonomy.personality_algo.plasticity import PlasticityCalculator

    plasticity_calc = PlasticityCalculator(config=agent_config.layered_personality_config)
    plasticity = plasticity_calc.compute(interaction_count)

    # 有效修改量
    effective_change = len(modification) * plasticity
    if effective_change < 1.0:
        return tool_ctx.build_success_result(
            invocation.tool_name,
            "性格已锚定，修改未生效。当前可塑性过低，建议更多互动后再尝试。",
            metadata={"plasticity": plasticity, "effective_change": effective_change},
        )

    # 体验层：放大有效修改量
    if layer == PersonalityLayer.EXPERIENCE:
        effective_change *= 1.5

    # 应用修改
    current_text = agent_config.layered_personality.get_layer_text(layer)
    if current_text.strip():
        new_text = f"{current_text}，{modification}"
    else:
        new_text = modification
    agent_config.layered_personality.set_layer_text(layer, new_text)

    # 持久化
    from src.maisaka.agent_autonomy.personality_persistence import PersonalityPersistence

    persistence = PersonalityPersistence()
    await persistence.save_modification(
        agent_id=agent_id,
        layer=layer,
        field="text",
        modification_text=modification,
        trigger="adjust_expression_tool",
    )

    return tool_ctx.build_success_result(
        invocation.tool_name,
        f"性格已更新：{layer_raw} 层已应用修改（可塑性={plasticity:.3f}，有效修改量={effective_change:.1f}字符）。",
        metadata={
            "layer": layer_raw,
            "plasticity": plasticity,
            "effective_change": effective_change,
        },
    )
