"""LS-7 工具: update_relationship — 更新对另一个智能体的态度"""

from typing import Optional

from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec
from src.maisaka.agent.config import PersonalityLayer

from .context import BuiltinToolRuntimeContext


def get_tool_spec() -> ToolSpec:
    """获取 update_relationship 工具声明。"""

    return ToolSpec(
        name="update_relationship",
        description="更新对另一个智能体的态度描述。仅主发言智能体可调用。",
        parameters_schema={
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "目标智能体 ID",
                },
                "attitude_update": {
                    "type": "string",
                    "description": "更新的态度描述文本",
                },
            },
            "required": ["target", "attitude_update"],
        },
        provider_name="maisaka_builtin",
        provider_type="builtin",
    )


async def handle_tool(
    tool_ctx: BuiltinToolRuntimeContext,
    invocation: ToolInvocation,
    context: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    """执行 update_relationship 内置工具。

    参数: target: str, attitude_update: str
    """
    del context

    target = str(invocation.arguments.get("target", "")).strip()
    attitude_update = str(invocation.arguments.get("attitude_update", "")).strip()

    if not target:
        return tool_ctx.build_failure_result(invocation.tool_name, "需要提供 target 参数（目标智能体 ID）")
    if not attitude_update:
        return tool_ctx.build_failure_result(invocation.tool_name, "需要提供 attitude_update 参数")

    # 解析当前智能体
    from src.core.adapters.agent_config_port import get_agent_config_provider

    agent_id, _ = tool_ctx.resolve_speaker_context()
    if not agent_id:
        return tool_ctx.build_failure_result(invocation.tool_name, "无法解析当前发言智能体")

    # 权限检查：仅主发言智能体可调用
    try:
        orch = tool_ctx.runtime._agent_orchestrator
        if orch is not None:
            primary = orch.get_primary_agent()
            if primary is not None and primary.agent_id != agent_id:
                return tool_ctx.build_failure_result(
                    invocation.tool_name,
                    f"update_relationship 仅供主发言智能体使用。当前主发言：{primary.agent_id}",
                )
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "检查关系权限失败，已放行", exception=exc)
        pass  # 无法检查权限时放行（非多智能体场景）

    if target == agent_id:
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "不能更新对自身的态度。如需反思自我，请使用 reflect_on_self 工具。",
        )

    # 获取智能体配置
    registry = get_agent_config_provider()
    agent_config = registry.get_agent(agent_id)

    # 检查目标是否存在
    if not registry.has_agent(target):
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            f"目标智能体 {target} 不存在。",
        )

    # 查找 internal_relationships 中是否已有该目标的关系
    found = False
    for rel in agent_config.internal_relationships:
        if rel.target_agent_id == target:
            rel.attitude = attitude_update
            found = True
            break

    if not found:
        # 目标不在 internal_relationships 中，追加新关系记录
        from src.maisaka.agent.config import InternalRelationship

        new_rel = InternalRelationship(
            target_agent_id=target,
            attitude=attitude_update,
            relationship_type="friend",
        )
        agent_config.internal_relationships.append(new_rel)

    # 触发 Hebbian 共激活增强
    from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager

    relationship_manager = AgentRelationshipManager()
    try:
        await relationship_manager.update_coactivation(
            agent_id=agent_id,
            target_agent_id=target,
            delta=0.12,  # 提及共激活增量
        )
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "共激活更新失败，不阻断主流程", exception=exc)
        pass  # 共激活更新失败不阻断主流程

    # 持久化修改记录
    from src.maisaka.agent_autonomy.personality_persistence import PersonalityPersistence

    persistence = PersonalityPersistence()
    await persistence.save_modification(
        agent_id=agent_id,
        layer=PersonalityLayer.EXPRESSION,
        field="attitude",
        modification_text=attitude_update,
        trigger=f"update_relationship_tool:{target}",
    )

    return tool_ctx.build_success_result(
        invocation.tool_name,
        f"已更新对 {target} 的态度：{attitude_update[:100]}{'...' if len(attitude_update) > 100 else ''}",
        metadata={
            "target": target,
            "attitude": attitude_update,
            "new_relationship": not found,
        },
    )
