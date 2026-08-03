"""MF-P0-001 验收：Orchestrator 直觉召回直接调用（无 hasattr 防御检查）。

对应 tasks.md 1.3：移除 hasattr(port, "recall_with_intuition") 后直接调用，
触发直觉召回不再抛 'NoneType' object has no attribute 'recall_with_intuition'。
"""

from unittest.mock import AsyncMock, MagicMock


async def test_build_think_context_calls_recall_with_intuition_directly(
    agent_autonomy_ports, monkeypatch,
) -> None:
    """hasattr 移除后：port.recall_with_intuition 被直接调用（无分支绕过）。"""
    from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

    port = MagicMock()
    port.recall_with_intuition = AsyncMock(
        return_value=MagicMock(recall_items=[], intuition=None),
    )
    monkeypatch.setattr("src.core.adapters.get_memory_service_port", lambda: port)

    orchestrator = AgentOrchestrator(
        session_id="test_session",
        session_name="测试会话",
        chat_loop_adapter=MagicMock(),
        thinking_organ_factory=MagicMock(),
        is_group_chat=False,
    )
    agent = MagicMock()
    agent.agent_id = "test_agent"
    agent.get_inner_world_snapshot = AsyncMock(return_value=None)

    message = MagicMock()
    message.plain_text = "你好"

    ctx = await orchestrator._build_think_context(
        agent, (message,), trigger_reason="user_message",
    )
    port.recall_with_intuition.assert_called_once()
    call_kwargs = port.recall_with_intuition.call_args.kwargs
    assert call_kwargs["agent_id"] == "test_agent"
    assert call_kwargs["seeds"] == ["user_message", "测试会话"]
    assert ctx.memory_snippets == ()


async def test_build_think_context_recall_failure_degrades_gracefully(
    agent_autonomy_ports, monkeypatch,
) -> None:
    """recall_with_intuition 抛异常 → 外层捕获降级（不影响 ThinkContext 构建）。"""
    from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

    port = MagicMock()
    port.recall_with_intuition = AsyncMock(side_effect=RuntimeError("端口未就绪"))
    monkeypatch.setattr("src.core.adapters.get_memory_service_port", lambda: port)

    orchestrator = AgentOrchestrator(
        session_id="test_session",
        session_name="测试会话",
        chat_loop_adapter=MagicMock(),
        thinking_organ_factory=MagicMock(),
        is_group_chat=False,
    )
    agent = MagicMock()
    agent.agent_id = "test_agent"
    agent.get_inner_world_snapshot = AsyncMock(return_value=None)

    message = MagicMock()
    message.plain_text = "你好"

    ctx = await orchestrator._build_think_context(
        agent, (message,), trigger_reason="user_message",
    )
    assert ctx.memory_snippets == ()
    assert ctx.intuition_context is None
