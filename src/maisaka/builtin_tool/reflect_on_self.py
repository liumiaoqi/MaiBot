"""LS-7 工具: reflect_on_self — 反思自我认知，影响认同层"""

from collections import deque
from typing import Optional

from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec
from src.core.types import ObserveRequest
from src.maisaka.agent.config import PersonalityLayer

from .context import BuiltinToolRuntimeContext

# 近期反思缓存（进程内，重启清空）
_recent_reflections: dict[str, deque[float]] = {}
_MAX_RECENT = 10


def _normalized_text_hash(text: str) -> float:
    """将文本哈希为 [0, 1] 范围的浮点数"""
    h = hash(text)
    return abs(h % 10000) / 10000.0


def _count_similar_reflections(agent_id: str, new_hash: float, threshold: float = 0.3) -> int:
    """统计近期相似反思的数量（哈希距离 < threshold 视为相似）"""
    history = _recent_reflections.get(agent_id)
    if history is None:
        return 0
    count = 0
    for past_hash in history:
        if abs(new_hash - past_hash) < threshold:
            count += 1
    return count


def _record_reflection(agent_id: str, content_hash: float) -> None:
    """记录本次反思哈希到近期缓存"""
    if agent_id not in _recent_reflections:
        _recent_reflections[agent_id] = deque(maxlen=_MAX_RECENT)
    _recent_reflections[agent_id].append(content_hash)


def get_tool_spec() -> ToolSpec:
    """获取 reflect_on_self 工具声明。"""

    return ToolSpec(
        name="reflect_on_self",
        description="反思自我认知，影响认同层。通过自我观察来更新'我认为自己是什么样的人'。",
        parameters_schema={
            "type": "object",
            "properties": {
                "observation": {
                    "type": "string",
                    "description": "关于自身的观察或反思内容",
                },
            },
            "required": ["observation"],
        },
        provider_name="maisaka_builtin",
        provider_type="builtin",
    )


async def handle_tool(
    tool_ctx: BuiltinToolRuntimeContext,
    invocation: ToolInvocation,
    context: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    """执行 reflect_on_self 内置工具。

    参数: observation: str
    """

    observation = str(invocation.arguments.get("observation", "")).strip()
    if not observation:
        return tool_ctx.build_failure_result(invocation.tool_name, "需要提供 observation 参数")

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

    # A6 gate: 自我验证 vs 自我提升判断
    from src.maisaka.agent_autonomy.personality_algo.self_verification import SelfVerificationCalculator

    sv_calc = SelfVerificationCalculator(config=agent_config.layered_personality_config)

    # 用认同层文本生成 self_concept_hash，用场合公开度判断策略
    identity_text = agent_config.layered_personality.identity_layer
    self_concept_hash = _normalized_text_hash(identity_text) if identity_text.strip() else 0.5

    # 自我确定度：认同层文本长度 / 基准长度（400 字符为基准高确定度）
    self_certainty = min(1.0, len(identity_text) / 400.0) if identity_text.strip() else 0.3
    # 场合公开度：群聊为高公开度，私聊为低公开度
    context_publicness = 0.8 if (context is not None and context.is_group_chat) else 0.3

    strategy = sv_calc.verification_vs_enhancement(self_certainty, context_publicness)

    # 如果是 enhancement 且观察与当前认同层矛盾，降低权重
    effective_weight = 1.0
    if strategy == "enhancement":
        observation_hash = _normalized_text_hash(observation)
        if abs(observation_hash - self_concept_hash) > 0.5:
            effective_weight = 0.3

    # 写入 A_memorix
    memorix_success = False
    memorix_warning = ""
    try:
        observe_request = ObserveRequest(
            text=observation,
            valence="neutral",
            source_id="reflect_on_self",
            session_id=tool_ctx.runtime.session_id if tool_ctx.runtime else "",
            agent_id=agent_id,
            tags=("stable_trait", "self_reflection"),
            metadata={"cognitive_type": "stable_trait", "effective_weight": effective_weight},
        )
        await tool_ctx.memory_port.observe_experience(observe_request)
        memorix_success = True
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "A_memorix 写入失败，反思仅影响本次会话", exception=exc)
        # A_memorix 不可用 → 本地缓存 + 警告
        memorix_warning = f"A_memorix 写入失败（{exc}），反思仅影响本次会话。"
        # 本地缓存：记录反思哈希
        _record_reflection(agent_id, _normalized_text_hash(observation))

    # Identity layer update: 统计近期相似反思，≥ 3 则逐步更新认同层
    observation_hash = _normalized_text_hash(observation)
    similar_count = _count_similar_reflections(agent_id, observation_hash)
    _record_reflection(agent_id, observation_hash)

    identity_updated = False
    if similar_count >= 3:
        # 计算可塑性
        from src.maisaka.agent_autonomy.personality_algo.plasticity import PlasticityCalculator
        from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager

        plasticity_calc = PlasticityCalculator(config=agent_config.layered_personality_config)

        interaction_count = 0
        try:
            relationship_manager = AgentRelationshipManager()
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
                port.report(ErrorLevel.WARNING, "统计交互次数失败，按 0 处理", exception=exc)
            interaction_count = 0

        plasticity = plasticity_calc.compute(interaction_count)
        modification_amount = plasticity * effective_weight * len(observation)

        if modification_amount >= 1.0:
            current_identity = agent_config.layered_personality.identity_layer
            if current_identity.strip():
                new_identity = f"{current_identity}，{observation}"
            else:
                new_identity = observation
            agent_config.layered_personality.set_layer_text(PersonalityLayer.IDENTITY, new_identity)

            # 持久化
            from src.maisaka.agent_autonomy.personality_persistence import PersonalityPersistence

            persistence = PersonalityPersistence()
            await persistence.save_modification(
                agent_id=agent_id,
                layer=PersonalityLayer.IDENTITY,
                field="text",
                modification_text=observation,
                trigger="reflect_on_self_tool",
            )
            identity_updated = True

    # 构建返回内容
    parts = [f"反思已记录：{observation[:100]}{'...' if len(observation) > 100 else ''}"]
    parts.append(f"策略：{strategy}（自我确定度={self_certainty:.2f}，场合公开度={context_publicness:.2f}）")
    parts.append(f"有效权重：{effective_weight:.1f}")

    if memorix_success:
        parts.append("长期记忆：已写入")
    elif memorix_warning:
        parts.append(f"长期记忆：{memorix_warning}")

    if identity_updated:
        parts.append(f"认同层：已更新（相似反思累计 {similar_count + 1} 次）")
    else:
        parts.append(f"认同层：未更新（相似反思 {similar_count + 1} 次，需 ≥ 3 次）")

    return tool_ctx.build_success_result(
        invocation.tool_name,
        "\n".join(parts),
        metadata={
            "strategy": strategy,
            "self_certainty": self_certainty,
            "context_publicness": context_publicness,
            "effective_weight": effective_weight,
            "memorix_success": memorix_success,
            "identity_updated": identity_updated,
            "similar_reflection_count": similar_count + 1,
        },
    )
