"""butler_closure 观测收口测试（批次 6）。

覆盖 T6.1–T6.8：六类动作可还原、kind 可筛、日志双标识、
预算耗尽兼容记录、旧口径不污染、detail 不泄露、导出可用、写表失败不阻断。
"""

import asyncio
import re

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.common.database.database import get_db_session
from src.common.database.database_model import (
    AgentAutonomySpeakerChangeRecord,
    ButlerTopicActionRecord,
    ButlerTopicState,
)
from src.core.types import NoticeKind, ThinkAction, ThinkResult
from src.maisaka.agent_autonomy import butler as butler_module
from src.maisaka.agent_autonomy import orchestrator as orchestrator_module
from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator


def _now_base() -> datetime:
    return datetime.now().replace(microsecond=0)
SESSION_ID = "session-observability-test"


_CONFIG_FIELDS = dict(
    orchestrator_strategy="default",
    vitality_tick_interval_seconds=3600,
    max_active_agents=4,
    state_awareness_enabled=False,
    interjection_enabled=False,
    interjection_cooldown_minutes=1,
    max_interjections_per_hour=5,
    max_interjections_per_session_per_hour=10,
    outbound_dedup_window_seconds=3.0,
    outbound_dedup_max_entries=5000,
    mention_chain_decay_base=0.6,
    mention_chain_max_depth=4,
    cohabitation_decay_factor=0.5,
    cohabitation_min_max=2,
    speaker_tag_format="【{agent_name}】",
    zh1_role_drift_enabled=False,
    zh1_role_drift_drift_period=500,
    zh1_role_drift_regression_rate=0.03,
    zh1_role_drift_sigma_max=0.3,
    zh1_role_drift_selection_ratio=0.167,
    zh1_role_drift_w_interaction=0.4,
    zh1_role_drift_w_relation=0.2,
    zh1_role_drift_w_uniqueness=0.3,
    zh1_role_drift_w_emotion=0.0,
    zh1_role_drift_reflection_interval=3600,
    butler_scene_opening_enabled=True,
    butler_opening_silence_minutes=30,
    butler_topic_budget=3,
    butler_opening_max_chars=120,
    butler_opening_timeout_seconds=4.0,
    butler_closure_round_enabled=True,
    # 2026-11-21 补：AgentAutonomySnapshot 新增的两个开关，伪造配置时漏了
    # （orchestrator.py:100 读 context_identity_enabled）
    context_identity_enabled=False,
    self_narration_first_person=False,
)


class _FakeLogger:
    def __init__(self):
        self.lines: list[str] = []
        self.warnings: list[str] = []

    def info(self, message, *args, **kwargs):
        self.lines.append(str(message))

    def debug(self, message, *args, **kwargs):
        self.lines.append(str(message))

    def error(self, message, *args, **kwargs):
        self.lines.append(str(message))

    def warning(self, message, *args, **kwargs):
        self.warnings.append(str(message))


class _FakePort:
    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []

    async def send_message(self, *, session_id, message, agent_id, source):
        self.sent.append((agent_id, source, message.components[0].text))
        return SimpleNamespace(success=True)


class _FakeLLM:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def generate_response_with_messages(self, *args, **kwargs):
        self.calls += 1
        if not self._responses:
            return SimpleNamespace(response="")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(response=item)


class _FakeScheduler:
    def __init__(self, results):
        self._results = list(results)

    def schedule(self, agent_id, organ, context):
        result = self._results.pop(0) if self._results else ThinkResult()

        async def _run():
            return result

        return asyncio.create_task(_run())


class _Registry:
    def __init__(self, agents):
        self._agents = agents
        self._by_id = {agent.agent_id: agent for agent in agents}

    def list_agents(self):
        return self._agents

    def has_agent(self, agent_id: str) -> bool:
        return agent_id in self._by_id

    def get_agent(self, agent_id: str):
        return self._by_id.get(agent_id)


def _agent_config(agent_id: str, name: str, *, is_butler: bool = False):
    return SimpleNamespace(
        agent_id=agent_id,
        display_name=name,
        is_butler=is_butler,
        layered_personality=SimpleNamespace(expression_layer=f"{name}的表达层") if is_butler else None,
        anti_mechanization_rules=[],
        internal_relationships=None,
        memory_personality=SimpleNamespace(attention_tags=[]),
        butler_config={},
        reply_style="",
        get_identity_summary=lambda: f"{name}的身份",
    )


def _message(text="今天好累", message_id="m1", at: datetime | None = None, *, is_notify=False):
    if at is None:
        at = _now_base()
    return SimpleNamespace(
        processed_plain_text=text,
        message_id=message_id,
        timestamp=at,
        is_notify=is_notify,
        message_info=SimpleNamespace(
            user_info=SimpleNamespace(user_id="u1", user_cardname=""),
        ),
    )


def _thinking_result(action: ThinkAction, text: str = "") -> ThinkResult:
    return ThinkResult(action=action, text=text)


async def _noop_async(*args, **kwargs):
    return None


@pytest.fixture(autouse=True)
def clean_tables():
    with get_db_session() as session:
        session.query(ButlerTopicActionRecord).delete()
        session.query(ButlerTopicState).delete()
        session.query(AgentAutonomySpeakerChangeRecord).delete()
    yield


@pytest.fixture
def env(monkeypatch):
    from src.core.app_config_port_registry import reset_app_config_port, set_app_config_port
    from src.core.adapters.agent_config_port import set_agent_config_provider
    from src.core.event_bus_port_registry import reset_event_bus_port, set_event_bus_port
    from src.core.routing_port_registry import register_routing_service

    fake_logger = _FakeLogger()
    fake_port = _FakePort()
    fake_error_port = SimpleNamespace(
        reports=[],
        report=lambda *a, **k: fake_error_port.reports.append((a, k)),
    )
    reminder_manager = MagicMock()
    reminder_manager.try_create = AsyncMock(return_value=None)
    reminder_manager.check_due.return_value = []

    def _build(
        *,
        llm_responses,
        think_results,
        budget_limit: int = 3,
        opening_enabled: bool = True,
        session_id: str = SESSION_ID,
    ):
        config = SimpleNamespace(**_CONFIG_FIELDS)
        config.butler_topic_budget = budget_limit
        config.butler_scene_opening_enabled = opening_enabled
        fake_llm = _FakeLLM(llm_responses)

        app_port = MagicMock()
        app_port.get_agent_autonomy_config.return_value = config
        set_app_config_port(app_port)
        set_event_bus_port(MagicMock())
        register_routing_service(MagicMock())

        registry = _Registry([
            _agent_config("butler", "丽塔", is_butler=True),
            _agent_config("a", "阿一"),
            _agent_config("b", "小乙"),
        ])
        set_agent_config_provider(registry)
        monkeypatch.setattr(butler_module, "get_agent_config_provider", lambda: registry)
        monkeypatch.setattr(butler_module, "get_message_port_v2", lambda: fake_port)
        monkeypatch.setattr(butler_module, "ReminderManager", lambda: reminder_manager)
        monkeypatch.setattr(butler_module, "_now", lambda: _now_base())
        monkeypatch.setattr("src.core.message_port_registry.get_message_port_v2", lambda: fake_port)
        monkeypatch.setattr(
            "src.core.adapters.llm_service_port.get_llm_service",
            lambda: fake_llm,
        )
        monkeypatch.setattr(
            "src.core.session_port_registry.get_existing_session_info",
            lambda session_id: None,
        )
        monkeypatch.setattr(
            "src.core.error_escalation_port_registry.get_error_escalation_port",
            lambda: fake_error_port,
        )

        async def _empty_decisions(self, *args, **kwargs):
            return []

        monkeypatch.setattr(butler_module.Butler, "decide_speaker_transfer", _empty_decisions)
        monkeypatch.setattr(orchestrator_module, "logger", fake_logger)

        orchestrator = AgentOrchestrator(
            session_id=session_id,
            session_name="观测会话",
            chat_loop_adapter=MagicMock(),
            thinking_organ_factory=MagicMock(),
            routing_service=MagicMock(),
            notice_classifier=MagicMock(),
            is_group_chat=False,
        )

        agent = MagicMock()
        agent.get_emotion_state.return_value = None
        orchestrator._active_agents = {"a": agent}
        orchestrator._primary_agent_id = "a"
        orchestrator._think_scheduler = _FakeScheduler(think_results)

        async def _fake_build_think_context(*args, **kwargs):
            return SimpleNamespace()

        monkeypatch.setattr(orchestrator, "_build_think_context", _fake_build_think_context)
        monkeypatch.setattr(orchestrator, "_try_write_experience", lambda *a, **k: None)
        monkeypatch.setattr(orchestrator, "_persist_thought_summary", _noop_async)
        monkeypatch.setattr(orchestrator, "_update_coactivation_on_message", _noop_async)
        monkeypatch.setattr(orchestrator, "_check_timeout_exit", lambda *a, **k: None)
        monkeypatch.setattr(orchestrator, "_classify_notice", lambda message: NoticeKind.UNKNOWN)
        monkeypatch.setattr(orchestrator._vitality_manager, "sync_standby_agents", lambda *a, **k: None)
        monkeypatch.setattr(orchestrator, "_start_reminder_tick", lambda: None)
        monkeypatch.setattr(orchestrator, "_start_desire_tick", lambda: None)

        return SimpleNamespace(
            orchestrator=orchestrator,
            port=fake_port,
            logger=fake_logger,
            error_port=fake_error_port,
            t0=_now_base(),
        )

    yield _build

    reset_app_config_port()
    reset_event_bus_port()
    register_routing_service(None)
    from src.core.adapters.agent_config_port import reset_agent_config_provider

    reset_agent_config_provider()


def _action_records() -> list[ButlerTopicActionRecord]:
    with get_db_session() as session:
        return list(session.query(ButlerTopicActionRecord).all())


def _speaker_changes() -> list[AgentAutonomySpeakerChangeRecord]:
    with get_db_session() as session:
        return list(session.query(AgentAutonomySpeakerChangeRecord).all())


async def test_action_records_reconstruct_topic_flow(env):
    built = env(
        llm_responses=["今晚想聊点什么吗？", ""],
        think_results=[
            _thinking_result(ThinkAction.SILENT),
            _thinking_result(ThinkAction.SILENT),
            _thinking_result(ThinkAction.REPLY, "我来回答。"),
        ],
        budget_limit=3,
    )

    await built.orchestrator.handle_message(_message(text="我们要不要吃饭？"))

    kinds = {record.kind for record in _action_records()}
    assert {"opening", "summon", "speak_for", "closure"} <= kinds

    closure_only = [record for record in _action_records() if record.kind == "closure"]
    assert len(closure_only) == 1


async def test_log_contains_session_and_topic(env):
    built = env(
        llm_responses=["傍晚的客厅安静着。"],
        think_results=[_thinking_result(ThinkAction.REPLY, "收到。")],
        opening_enabled=False,
    )

    await built.orchestrator.handle_message(_message())

    joined = "\n".join(built.logger.lines)
    assert re.search(r"session=.*topic=", joined)


async def test_budget_exhausted_writes_compat_record(env):
    built = env(
        llm_responses=["傍晚的客厅安静着。"],
        think_results=[_thinking_result(ThinkAction.SILENT), _thinking_result(ThinkAction.SILENT)],
        budget_limit=1,
    )

    await built.orchestrator.handle_message(_message())

    records = [
        record
        for record in _speaker_changes()
        if record.change_type == "butler_budget_exhausted"
    ]
    assert len(records) == 1
    record = records[0]
    assert "used=1/1" in record.change_reason
    assert "reason=budget_exhausted" in record.change_reason
    assert record.transfer_type == "none"
    assert record.decision_source == "rule"

    legacy = [
        record
        for record in _speaker_changes()
        if record.transfer_type in ("permanent_transfer", "temporary_borrow")
    ]
    assert all(record.change_type != "butler_budget_exhausted" for record in legacy)


async def test_details_do_not_leak(env):
    built = env(
        llm_responses=["傍晚的客厅安静着。", "夜深了。"],
        think_results=[
            _thinking_result(ThinkAction.SILENT),
            _thinking_result(ThinkAction.SILENT),

            _thinking_result(ThinkAction.SILENT),
            _thinking_result(ThinkAction.SILENT),
        ],
        budget_limit=1,
    )

    await built.orchestrator.handle_message(_message(text="我们要不要吃饭？"))
    await built.orchestrator.handle_message(
        _message(text="那到底要不要？", message_id="m2", at=built.t0 + timedelta(minutes=31)),
    )

    details = [record.detail for record in _action_records()]
    assert len(details) >= 5
    for detail in details:
        assert "prompt" not in detail.lower()
        assert "deepseek" not in detail.lower()
        assert "sk-" not in detail
        assert "我们要不要吃饭？那到底要不要？"[:30] not in detail


def test_exports_available():
    import src.maisaka.agent_autonomy as pkg
    from src.maisaka.agent_autonomy import (
        ButlerClosureConfig,
        ClosureSignal,
        TopicLedger,
        detect_closure_signal,
    )

    assert TopicLedger is not None
    assert ButlerClosureConfig is not None
    assert ClosureSignal is not None
    assert callable(detect_closure_signal)
    assert "TopicLedger" in pkg.__all__
    assert "ButlerClosureConfig" in pkg.__all__
    assert "detect_closure_signal" in pkg.__all__
    assert "ClosureSignal" in pkg.__all__


async def test_compat_write_failure_does_not_block(env):
    built = env(
        llm_responses=["傍晚的客厅安静着。"],
        think_results=[_thinking_result(ThinkAction.SILENT), _thinking_result(ThinkAction.SILENT)],
        budget_limit=1,
    )
    built.orchestrator._activity_store.save_speaker_change = MagicMock(
        side_effect=RuntimeError("db down"),
    )

    await built.orchestrator.handle_message(_message())

    assert all(agent_id != "butler" or source != "butler_budget_exhausted" for agent_id, source, _ in built.port.sent)
    assert len(built.logger.warnings) == 1
    assert len(built.error_port.reports) == 1