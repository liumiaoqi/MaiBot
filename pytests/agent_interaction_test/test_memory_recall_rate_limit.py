"""MF-P0-003 验收：记忆检索 rpm 限流。

对应 tasks.md 3.3/3.4：MemoryDrivenTrigger 与 HeuristicMemoryInjector
每分钟检索次数超限时跳过检索；配置默认值 10。
"""

from unittest.mock import AsyncMock, MagicMock

from src.core.adapters.llm_service_port import set_llm_service

# heuristic_injector 模块级实例化（CLAUDE.md 踩坑 #1）在 import 时调用 get_llm_service()——
# 必须先注册再 import，否则收集期 RuntimeError。
set_llm_service(MagicMock())

from src.maisaka.agent_interaction.config.trigger_config import MemoryDrivenTriggerConfig  # noqa: E402
from src.maisaka.agent_interaction.memory.adapter import AgentMemoryAdapter  # noqa: E402
from src.maisaka.agent_interaction.models import AgentInteractionRelationshipRead  # noqa: E402
from src.maisaka.agent_interaction.triggers.memory_driven import MemoryDrivenTrigger  # noqa: E402
from src.maisaka.agent.emotion import EmotionState  # noqa: E402


def test_memory_driven_config_default_rpm_is_10() -> None:
    """MemoryDrivenTriggerConfig.recall_rate_limit_rpm 默认 10，范围 [1, 60]。"""
    cfg = MemoryDrivenTriggerConfig()
    assert cfg.recall_rate_limit_rpm == 10
    assert MemoryDrivenTriggerConfig(recall_rate_limit_rpm=60).recall_rate_limit_rpm == 60


def _relationship(target: str, score: float = 300.0) -> AgentInteractionRelationshipRead:
    return AgentInteractionRelationshipRead(
        id=1,
        agent_id="a1",
        target_agent_id=target,
        score=score,
        relationship_type="friend",
        attitude="positive",
        interaction_count=3,
        last_interaction_at=None,
    )


def _emotion_state() -> EmotionState:
    return MagicMock()


async def test_trigger_recall_rate_limited_skips_search() -> None:
    """rpm=1：第一次 evaluate 检索，第二次超限跳过（search 只调用一次）。"""
    adapter = MagicMock(spec=AgentMemoryAdapter)
    adapter.search_interaction_memory = AsyncMock(
        return_value=MagicMock(success=False, hits=[]),
    )
    trigger = MemoryDrivenTrigger(memory_adapter=adapter, recall_rate_limit_rpm=1)

    rel = _relationship("a2")
    # 第一次：放行检索
    await trigger.evaluate("a1", _emotion_state(), [rel])
    assert adapter.search_interaction_memory.await_count == 1

    # 第二次：超限跳过（不再调用检索）
    await trigger.evaluate("a1", _emotion_state(), [rel])
    assert adapter.search_interaction_memory.await_count == 1


async def test_trigger_recall_under_limit_always_searches() -> None:
    """rpm 足够时每次 evaluate 都检索。"""
    adapter = MagicMock(spec=AgentMemoryAdapter)
    adapter.search_interaction_memory = AsyncMock(
        return_value=MagicMock(success=False, hits=[]),
    )
    trigger = MemoryDrivenTrigger(memory_adapter=adapter, recall_rate_limit_rpm=10)

    rel = _relationship("a2")
    for _ in range(3):
        await trigger.evaluate("a1", _emotion_state(), [rel])
    assert adapter.search_interaction_memory.await_count == 3


def test_injector_allow_recall_rate_limits() -> None:
    """HeuristicMemoryInjector._allow_recall：窗口内超 rpm 拒绝。"""
    from src.maisaka.memory.heuristic_injector import HeuristicMemoryInjector

    injector = HeuristicMemoryInjector(llm_service=MagicMock())
    assert injector._allow_recall(2) is True
    assert injector._allow_recall(2) is True
    assert injector._allow_recall(2) is False


def test_injector_rate_limit_window_rolls(monkeypatch) -> None:
    """60s 窗口滚动后恢复放行。"""
    from src.maisaka.memory.heuristic_injector import HeuristicMemoryInjector
    import src.maisaka.memory.heuristic_injector as hi

    real_time = hi.time
    fake_now = [real_time()]
    monkeypatch.setattr(hi, "time", lambda: fake_now[0])

    injector = HeuristicMemoryInjector(llm_service=MagicMock())
    assert injector._allow_recall(1) is True
    assert injector._allow_recall(1) is False  # 窗口内超限

    fake_now[0] += 61.0  # 窗口滚动
    assert injector._allow_recall(1) is True
