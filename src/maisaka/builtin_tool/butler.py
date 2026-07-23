"""管家专用内置工具 — 丽塔·洛丝薇瑟协调客厅的 LLM 工具。"""

from __future__ import annotations

import traceback
from typing import Any, Optional

from src.common.logger import get_logger
from src.core.tooling import ToolAvailabilityContext, ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec
from src.maisaka.context.message_adapter import build_visible_text_from_sequence

from .context import BuiltinToolRuntimeContext

logger = get_logger("maisaka_builtin_butler")


def _is_butler_agent(ctx: BuiltinToolRuntimeContext) -> bool:
    """检查当前智能体是否为管家。"""
    try:
        orch = ctx.runtime._agent_orchestrator
        if orch is None:
            return False
        from src.core.adapters.agent_config_port import get_agent_config_provider
        registry = get_agent_config_provider()
        if not registry.has_agent(ctx.agent_id):
            return False
        agent_cfg = registry.get_agent(ctx.agent_id)
        return bool(getattr(agent_cfg, "is_butler", False))
    except Exception:
        return False


# ── switch_primary ──────────────────────────────────

def get_switch_primary_spec() -> ToolSpec:
    return ToolSpec(
        name="switch_primary",
        description=(
            "切换主发言智能体。只有管家丽塔可以使用。"
            "当某个角色更适合当前话题时，切换让ta来主导对话。"
            "切换后原来的主智能体变成共居智能体。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "要切换为目标主发言的智能体 ID",
                },
            },
            "required": ["agent_id"],
        },
    )


async def handle_switch_primary(
    invocation: ToolInvocation,
    ctx: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    try:
        tool_ctx = BuiltinToolRuntimeContext.from_context(ctx)
        if not _is_butler_agent(tool_ctx):
            return ToolExecutionResult(error="switch_primary 仅供管家丽塔使用")

        agent_id = str(invocation.params.get("agent_id", "")).strip()
        if not agent_id:
            return ToolExecutionResult(error="需要指定 agent_id")

        orch = tool_ctx.runtime._agent_orchestrator
        await orch.switch_primary_speaker(
            new_primary_id=agent_id,
            transfer_type="borrow",
            decision_source="butler",
        )
        logger.info(f"管家工具: switch_primary agent={agent_id}")
        return ToolExecutionResult(content=f"已将主发言权切换给 {agent_id}")
    except Exception as exc:
        logger.error(f"switch_primary 异常: {traceback.format_exc()}")
        return ToolExecutionResult(error=str(exc))


# ── activate_agent ──────────────────────────────────

def get_activate_agent_spec() -> ToolSpec:
    return ToolSpec(
        name="activate_agent",
        description=(
            "激活一个待命的智能体加入对话。只有管家丽塔可以使用。"
            "当某个角色应该参与当前话题但还在待命时，用此工具叫ta加入。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "要激活的智能体 ID",
                },
            },
            "required": ["agent_id"],
        },
    )


async def handle_activate_agent(
    invocation: ToolInvocation,
    ctx: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    try:
        tool_ctx = BuiltinToolRuntimeContext.from_context(ctx)
        if not _is_butler_agent(tool_ctx):
            return ToolExecutionResult(error="activate_agent 仅供管家丽塔使用")

        agent_id = str(invocation.params.get("agent_id", "")).strip()
        if not agent_id:
            return ToolExecutionResult(error="需要指定 agent_id")

        orch = tool_ctx.runtime._agent_orchestrator
        await orch.activate_agent(agent_id, reason="butler_activation")
        logger.info(f"管家工具: activate_agent agent={agent_id}")
        return ToolExecutionResult(content=f"已激活智能体 {agent_id}")
    except Exception as exc:
        logger.error(f"activate_agent 异常: {traceback.format_exc()}")
        return ToolExecutionResult(error=str(exc))
