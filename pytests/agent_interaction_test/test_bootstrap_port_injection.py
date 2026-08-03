"""MF-P0-001 验收：AgentInteraction bootstrap 端口注入验证。

对应 tasks.md 1.5：build_interaction_scheduler / build_monologue_engine 的
memory_port 参数必选（MemoryServicePort），AgentMemoryAdapter 收到非 None 端口；
agent 初始化后端口可调用 recall_with_intuition 和 observe_experience。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.app_config_port_registry import (
    reset_app_config_port,
    set_app_config_port,
)
from src.core.types import AgentInteractionSnapshot


@pytest.fixture
def interaction_config():
    """注册交互配置（enabled=True，monologue 开启）+ 依赖 Port。"""
    from src.core.adapters.agent_config_port import (
        reset_agent_config_provider,
        set_agent_config_provider,
    )

    cfg = AgentInteractionSnapshot(
        enabled=True,
        monologue_enabled=True,
        evaluation_interval_seconds=10,
    )
    app_config_port = MagicMock()
    app_config_port.get_agent_interaction_config.return_value = cfg
    set_app_config_port(app_config_port)
    set_agent_config_provider(MagicMock())
    yield cfg
    reset_app_config_port()
    reset_agent_config_provider()


def test_build_interaction_scheduler_requires_memory_port() -> None:
    """memory_port 为必选参数——缺参构造抛 TypeError。"""
    from src.maisaka.agent_interaction.bootstrap import build_interaction_scheduler

    with pytest.raises(TypeError):
        build_interaction_scheduler()  # type: ignore[call-arg]


def test_interaction_scheduler_injects_memory_port(interaction_config) -> None:
    """有效端口注入：scheduler 内 memory_adapter.memory_port 是同一对象。"""
    from src.maisaka.agent_interaction.bootstrap import build_interaction_scheduler

    port = MagicMock()
    scheduler = build_interaction_scheduler(port)
    assert scheduler is not None
    memory_adapter = scheduler._trigger._engine._memory_adapter
    assert memory_adapter.memory_port is port


def test_monologue_engine_injects_memory_port(interaction_config) -> None:
    """monologue engine 同样注入同一端口。"""
    from src.maisaka.agent_interaction.bootstrap import build_monologue_engine

    port = MagicMock()
    engine = build_monologue_engine(port)
    assert engine is not None
    assert engine._memory_adapter.memory_port is port


async def test_agent_memory_port_callable_after_injection(interaction_config) -> None:
    """agent 初始化后端口可调用 recall_with_intuition 和 observe_experience。"""
    from src.maisaka.agent_interaction.bootstrap import build_interaction_scheduler

    port = MagicMock()
    port.recall_with_intuition = AsyncMock(return_value=MagicMock(recall_items=[]))
    port.observe_experience = AsyncMock(return_value=MagicMock(success=True))
    scheduler = build_interaction_scheduler(port)
    assert scheduler is not None
    memory_adapter = scheduler._trigger._engine._memory_adapter

    recall = await memory_adapter.recall_with_intuition(
        agent_id="a1", seeds=["测试"], context_text="上下文",
    )
    assert recall is not None
    port.recall_with_intuition.assert_called_once()

    write = await memory_adapter.memory_port.observe_experience(
        text="体验",
        source_id="s1",
        session_id="chat_1",
        agent_id="a1",
        tags=["test"],
    )
    assert write.success is True
    port.observe_experience.assert_called_once()
