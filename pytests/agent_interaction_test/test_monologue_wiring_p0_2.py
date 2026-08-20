"""P0-2 验收：MonologueEngine 接线行为测试。

对应 tasks.md 6.4：验证
1. bootstrap 装配后 scheduler 持有 monologue_engine（同一对象引用）
2. scheduler 与 monologue_engine 共享同一 emotion_registry（状态不分裂）
3. 交互成功路径触发 record_activity + monologue_engine.execute
4. 交互失败路径不触发 monologue_engine
5. MonologueEngine.record_activity 薄透传到 MonologueTrigger.record_activity
6. monologue_engine=None 时 scheduler 不报错（兼容关闭独白场景）
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


@pytest.fixture
def interaction_config_monologue_off():
    """交互开但独白关——验证 scheduler 不持有 monologue_engine。"""
    from src.core.adapters.agent_config_port import (
        reset_agent_config_provider,
        set_agent_config_provider,
    )

    cfg = AgentInteractionSnapshot(
        enabled=True,
        monologue_enabled=False,
        evaluation_interval_seconds=10,
    )
    app_config_port = MagicMock()
    app_config_port.get_agent_interaction_config.return_value = cfg
    set_app_config_port(app_config_port)
    set_agent_config_provider(MagicMock())
    yield cfg
    reset_app_config_port()
    reset_agent_config_provider()


def test_scheduler_holds_monologue_engine_same_ref(interaction_config) -> None:
    """bootstrap 装配后 scheduler._monologue_engine 是 MonologueEngine 实例（非 None）。"""
    from src.maisaka.agent_interaction.bootstrap import build_interaction_scheduler
    from src.maisaka.agent_interaction.monologue_engine import MonologueEngine

    port = MagicMock()
    scheduler = build_interaction_scheduler(port)
    assert scheduler is not None
    assert isinstance(scheduler._monologue_engine, MonologueEngine)


def test_scheduler_and_monologue_share_emotion_registry(interaction_config) -> None:
    """scheduler 引擎与 monologue_engine 共享同一 emotion_registry（状态不分裂）。"""
    from src.maisaka.agent_interaction.bootstrap import build_interaction_scheduler

    port = MagicMock()
    scheduler = build_interaction_scheduler(port)
    assert scheduler is not None
    engine_emotion = scheduler._trigger._engine._emotion_registry
    monologue_emotion = scheduler._monologue_engine._emotion_registry
    assert engine_emotion is monologue_emotion


def test_scheduler_and_monologue_share_memory_adapter(interaction_config) -> None:
    """scheduler 引擎与 monologue_engine 共享同一 memory_adapter。"""
    from src.maisaka.agent_interaction.bootstrap import build_interaction_scheduler

    port = MagicMock()
    scheduler = build_interaction_scheduler(port)
    assert scheduler is not None
    engine_memory = scheduler._trigger._engine._memory_adapter
    monologue_memory = scheduler._monologue_engine._memory_adapter
    assert engine_memory is monologue_memory


def test_monologue_off_scheduler_has_no_engine(interaction_config_monologue_off) -> None:
    """独白关闭时 scheduler._monologue_engine is None（不报错）。"""
    from src.maisaka.agent_interaction.bootstrap import build_interaction_scheduler

    port = MagicMock()
    scheduler = build_interaction_scheduler(port)
    assert scheduler is not None
    assert scheduler._monologue_engine is None


async def test_interaction_success_triggers_record_activity_and_execute(
    interaction_config,
) -> None:
    """交互触发成功 → record_activity 被调用 + monologue_engine.execute 被调用。"""
    from src.maisaka.agent_interaction.monologue_engine import MonologueEngine
    from src.maisaka.agent_interaction.scheduler import InteractionScheduler
    from src.maisaka.agent_interaction.trigger_scheduler import InteractionTrigger

    # 构造 mock trigger 返回 success=True
    trigger_result = MagicMock(success=True, event_id="evt-1")
    mock_trigger = MagicMock(spec=InteractionTrigger)
    mock_trigger.try_trigger = AsyncMock(return_value=trigger_result)

    # 构造 mock config_registry 返回 1 个 agent
    mock_agent = MagicMock(agent_id="agent-a")
    mock_config_registry = MagicMock()
    mock_config_registry.list_agents.return_value = [mock_agent]

    # 构造 mock monologue_engine
    mock_monologue = MagicMock(spec=MonologueEngine)
    mock_monologue.record_activity = MagicMock()
    mock_monologue.execute = AsyncMock(return_value=MagicMock(success=False))

    scheduler = InteractionScheduler(
        trigger=mock_trigger,
        evaluation_interval_seconds=10,
        monologue_engine=mock_monologue,
    )
    scheduler._config_registry = mock_config_registry

    await scheduler._evaluate_all_agents()

    mock_trigger.try_trigger.assert_awaited_once_with("agent-a")
    mock_monologue.record_activity.assert_called_once_with("agent-a")
    mock_monologue.execute.assert_awaited_once_with("agent-a")


async def test_interaction_failure_still_executes_monologue(
    interaction_config,
) -> None:
    """交互触发失败（success=False）→ execute 仍被调（每周期无条件），record_activity 不被调。"""
    from src.maisaka.agent_interaction.monologue_engine import MonologueEngine
    from src.maisaka.agent_interaction.scheduler import InteractionScheduler
    from src.maisaka.agent_interaction.trigger_scheduler import InteractionTrigger

    trigger_result = MagicMock(success=False, event_id="evt-x")
    mock_trigger = MagicMock(spec=InteractionTrigger)
    mock_trigger.try_trigger = AsyncMock(return_value=trigger_result)

    mock_agent = MagicMock(agent_id="agent-b")
    mock_config_registry = MagicMock()
    mock_config_registry.list_agents.return_value = [mock_agent]

    mock_monologue = MagicMock(spec=MonologueEngine)
    mock_monologue.record_activity = MagicMock()
    mock_monologue.execute = AsyncMock()

    scheduler = InteractionScheduler(
        trigger=mock_trigger,
        evaluation_interval_seconds=10,
        monologue_engine=mock_monologue,
    )
    scheduler._config_registry = mock_config_registry

    await scheduler._evaluate_all_agents()

    mock_monologue.record_activity.assert_not_called()
    mock_monologue.execute.assert_awaited_once_with("agent-b")


async def test_interaction_none_result_still_executes_monologue(
    interaction_config,
) -> None:
    """try_trigger 返回 None → execute 仍被调（每周期无条件），record_activity 不被调。"""
    from src.maisaka.agent_interaction.monologue_engine import MonologueEngine
    from src.maisaka.agent_interaction.scheduler import InteractionScheduler
    from src.maisaka.agent_interaction.trigger_scheduler import InteractionTrigger

    mock_trigger = MagicMock(spec=InteractionTrigger)
    mock_trigger.try_trigger = AsyncMock(return_value=None)

    mock_agent = MagicMock(agent_id="agent-c")
    mock_config_registry = MagicMock()
    mock_config_registry.list_agents.return_value = [mock_agent]

    mock_monologue = MagicMock(spec=MonologueEngine)
    mock_monologue.record_activity = MagicMock()
    mock_monologue.execute = AsyncMock()

    scheduler = InteractionScheduler(
        trigger=mock_trigger,
        evaluation_interval_seconds=10,
        monologue_engine=mock_monologue,
    )
    scheduler._config_registry = mock_config_registry

    await scheduler._evaluate_all_agents()

    mock_monologue.record_activity.assert_not_called()
    mock_monologue.execute.assert_awaited_once_with("agent-c")


async def test_monologue_execute_exception_does_not_break_loop(
    interaction_config,
) -> None:
    """monologue_engine.execute 抛异常 → 不影响调度循环（吞掉+warning）。"""
    from src.maisaka.agent_interaction.monologue_engine import MonologueEngine
    from src.maisaka.agent_interaction.scheduler import InteractionScheduler
    from src.maisaka.agent_interaction.trigger_scheduler import InteractionTrigger

    trigger_result = MagicMock(success=True, event_id="evt-2")
    mock_trigger = MagicMock(spec=InteractionTrigger)
    mock_trigger.try_trigger = AsyncMock(return_value=trigger_result)

    mock_agent = MagicMock(agent_id="agent-d")
    mock_config_registry = MagicMock()
    mock_config_registry.list_agents.return_value = [mock_agent]

    mock_monologue = MagicMock(spec=MonologueEngine)
    mock_monologue.record_activity = MagicMock()
    mock_monologue.execute = AsyncMock(side_effect=RuntimeError("独白生成失败"))

    scheduler = InteractionScheduler(
        trigger=mock_trigger,
        evaluation_interval_seconds=10,
        monologue_engine=mock_monologue,
    )
    scheduler._config_registry = mock_config_registry

    # 不抛异常即通过
    await scheduler._evaluate_all_agents()
    mock_monologue.record_activity.assert_called_once_with("agent-d")
    mock_monologue.execute.assert_awaited_once_with("agent-d")


def test_monologue_engine_record_activity_passes_through() -> None:
    """MonologueEngine.record_activity 薄透传到 MonologueTrigger.record_activity。"""
    from src.core.adapters.agent_config_port import (
        reset_agent_config_provider,
        set_agent_config_provider,
    )
    from src.maisaka.agent_interaction.monologue_engine import MonologueEngine
    from src.maisaka.agent_interaction.monologue_trigger import MonologueTrigger

    set_agent_config_provider(MagicMock())
    try:
        mock_trigger = MagicMock(spec=MonologueTrigger)
        mock_trigger.record_activity = MagicMock()

        # emotion_registry 用 MagicMock 避免触发全局 port
        mock_emotion = MagicMock()
        engine = MonologueEngine(
            emotion_registry=mock_emotion,
            monologue_trigger=mock_trigger,
        )
        engine.record_activity("agent-z")
        mock_trigger.record_activity.assert_called_once_with("agent-z")
    finally:
        reset_agent_config_provider()


async def test_record_activity_exception_does_not_block_execute(
    interaction_config,
) -> None:
    """record_activity 抛异常 → execute 仍被调，评估循环不中断。"""
    from src.maisaka.agent_interaction.monologue_engine import MonologueEngine
    from src.maisaka.agent_interaction.scheduler import InteractionScheduler
    from src.maisaka.agent_interaction.trigger_scheduler import InteractionTrigger

    trigger_result = MagicMock(success=True, event_id="evt-ra")
    mock_trigger = MagicMock(spec=InteractionTrigger)
    mock_trigger.try_trigger = AsyncMock(return_value=trigger_result)

    mock_agent = MagicMock(agent_id="agent-ra")
    mock_config_registry = MagicMock()
    mock_config_registry.list_agents.return_value = [mock_agent]

    mock_monologue = MagicMock(spec=MonologueEngine)
    mock_monologue.record_activity = MagicMock(side_effect=RuntimeError("ra fail"))
    mock_monologue.execute = AsyncMock(return_value=MagicMock(success=False))

    scheduler = InteractionScheduler(
        trigger=mock_trigger,
        evaluation_interval_seconds=10,
        monologue_engine=mock_monologue,
    )
    scheduler._config_registry = mock_config_registry

    await scheduler._evaluate_all_agents()

    mock_monologue.record_activity.assert_called_once_with("agent-ra")
    mock_monologue.execute.assert_awaited_once_with("agent-ra")


async def test_monologue_criterion_closure_real_trigger(
    interaction_config,
) -> None:
    """判据闭环真触发测试——走生产装配路径，阈值放低，断言 InnerMonologueEvent 入库。

    P0-R2-1 核心：修复前 execute 在成功分支内，无交互时 execute 不调，事件不入库（死锁）；
    修复后 execute 每周期调，判据满足时事件入库。
    区别于 mock 判据返回 True 的接线测试，本测试走真实判据计算路径。
    """

    from src.common.database.database import get_db_session
    from src.common.database.database_model import InnerMonologueEvent
    from src.core.adapters.agent_config_port import (
        reset_agent_config_provider,
        set_agent_config_provider,
    )
    from src.core.app_config_port_registry import (
        reset_app_config_port,
        set_app_config_port,
    )
    from src.core.types import AgentInteractionSnapshot
    from src.maisaka.agent_interaction.bootstrap import build_interaction_scheduler
    from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry

    # 阈值放低配置（idle_threshold=0 + emotion_threshold=0 → 判据恒可满足）
    cfg = AgentInteractionSnapshot(
        enabled=True,
        monologue_enabled=True,
        evaluation_interval_seconds=10,
        monologue_idle_threshold_minutes=0,
        monologue_emotion_intensity_threshold=0,
        monologue_min_interval_minutes=0,
    )
    app_config_port = MagicMock()
    app_config_port.get_agent_interaction_config.return_value = cfg
    set_app_config_port(app_config_port)

    # 注册一个真实 agent config（has_agent 返回 True，get_agent 返回配置）
    agent_id = "ut:monologue_closure:test"
    mock_agent_cfg = MagicMock()
    mock_agent_cfg.display_name = "测试智能体"
    mock_agent_cfg.relationship_growth_rate = 1.0
    mock_agent_provider = MagicMock()
    mock_agent_provider.has_agent.return_value = True
    mock_agent_provider.get_agent.return_value = mock_agent_cfg
    mock_agent = MagicMock(agent_id=agent_id)
    mock_agent_provider.list_agents.return_value = [mock_agent]
    set_agent_config_provider(mock_agent_provider)


    port = MagicMock()
    try:
        scheduler = build_interaction_scheduler(port)
        assert scheduler is not None
        assert scheduler._monologue_engine is not None

        # 预置非零情绪（确保 emotion_intensity > 0，判据可满足）
        emotion_registry = scheduler._trigger._engine._emotion_registry
        assert isinstance(emotion_registry, AgentEmotionManagerRegistry)
        emotion_registry.apply_trigger(agent_id, "lonely", 50.0)

        # 执行一个评估周期
        await scheduler._evaluate_all_agents()

        # 真库查询 InnerMonologueEvent 表存在该 agent 的新事件
        with get_db_session() as session:
            rows = (
                session.query(InnerMonologueEvent)
                .filter(InnerMonologueEvent.agent_id == agent_id)
                .all()
            )
            assert len(rows) >= 1, (
                f"判据闭环失败：InnerMonologueEvent 表无 {agent_id} 的新事件——独白死锁未消除"
            )
    finally:
        # 清理测试数据
        from sqlalchemy import delete

        with get_db_session() as session:
            session.execute(
                delete(InnerMonologueEvent).where(
                    InnerMonologueEvent.agent_id == agent_id
                )
            )
        reset_app_config_port()
        reset_agent_config_provider()