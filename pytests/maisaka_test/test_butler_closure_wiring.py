"""butler_closure 生产接线测试（批次 5）。

真实 `AgentOrchestrator(...)` 构造 + fake `ThinkingOrganFactory` / fake LLM /
fake `MessagePort`，通过 `handle_message` 触发生产装配链。
禁止测试内 new Butler 或 new TopicLedger。
"""

import asyncio

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.common.database.database import get_db_session
from src.common.database.database_model import ButlerTopicActionRecord, ButlerTopicState
from src.core.types import NoticeKind, ThinkAction, ThinkResult
from src.maisaka.agent_autonomy import butler as butler_module
from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator


def _now_base() -> datetime:
    return datetime.now().replace(microsecond=0)
SESSION_ID = "session-wiring-test"


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
    butler_topic_budget=2,
    butler_opening_max_chars=120,
    butler_opening_timeout_seconds=4.0,
    butler_closure_round_enabled=True,
)


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
        self.calls = 0

    def schedule(self, agent_id, organ, context):
        self.calls += 1
        result = self._results.pop(0) if self._results else ThinkResult()

        async def _run():
            return result

        return asyncio.create_task(_run())


class _Registry:
    def __init__(self, agents):
        self._agents = agents

    def list_agents(self):
        return self._agents


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


class _FakeConfigKwargs(dict):
    pass


@pytest.fixture(autouse=True)
def clean_tables():
    with get_db_session() as session:
        session.query(ButlerTopicActionRecord).delete()
        session.query(ButlerTopicState).delete()
    yield


async def _noop_async(*args, **kwargs):
    return None


@pytest.fixture
def make_orchestrator(monkeypatch):
    from src.core.app_config_port_registry import reset_app_config_port, set_app_config_port
    from src.core.event_bus_port_registry import reset_event_bus_port, set_event_bus_port
    from src.core.routing_port_registry import register_routing_service

    created: list[AgentOrchestrator] = []

    def _make(
        *,
        llm_responses,
        think_results,
        budget_limit: int = 2,
        opening_enabled: bool = True,
        opening_timeout: float = 4.0,
        session_id: str = SESSION_ID,
    ):
        config = SimpleNamespace(**_CONFIG_FIELDS)
        config.butler_topic_budget = budget_limit
        config.butler_scene_opening_enabled = opening_enabled
        config.butler_opening_timeout_seconds = opening_timeout

        app_port = MagicMock()
        app_port.get_agent_autonomy_config.return_value = config
        set_app_config_port(app_port)
        set_event_bus_port(MagicMock())
        register_routing_service(MagicMock())

        fake_port = _FakePort()
        fake_llm = _FakeLLM(llm_responses)
        fake_error_port = SimpleNamespace(reports=[], report=lambda *a, **k: fake_error_port.reports.append((a, k)))
        reminder_manager = MagicMock()
        reminder_manager.try_create = AsyncMock(return_value=None)
        reminder_manager.check_due.return_value = []

        monkeypatch.setattr(
            butler_module,
            "get_agent_config_provider",
            lambda: _Registry([
                _agent_config("butler", "丽塔", is_butler=True),
                _agent_config("a", "阿一"),
                _agent_config("b", "小乙"),
            ]),
        )
        monkeypatch.setattr(butler_module, "get_message_port_v2", lambda: fake_port)
        monkeypatch.setattr(butler_module, "ReminderManager", lambda: reminder_manager)
        monkeypatch.setattr(
            butler_module,
            "_now",
            lambda: _now_base(),
        )
        monkeypatch.setattr(
            "src.core.message_port_registry.get_message_port_v2",
            lambda: fake_port,
        )
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

        orchestrator = AgentOrchestrator(
            session_id=session_id,
            session_name="测试会话",
            chat_loop_adapter=MagicMock(),
            thinking_organ_factory=MagicMock(),
            routing_service=MagicMock(),
            notice_classifier=MagicMock(),
            is_group_chat=False,
        )
        created.append(orchestrator)

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
            llm=fake_llm,
            error_port=fake_error_port,
            config=config,
            t0=_now_base(),
        )

    yield _make

    for orchestrator in created:
        orchestrator._vitality_tick_scheduler.stop()
        AgentOrchestrator._registry.pop(orchestrator._session_id, None)
    reset_app_config_port()
    reset_event_bus_port()
    register_routing_service(None)


def _action_count(kind: str) -> int:
    with get_db_session() as session:
        return session.query(ButlerTopicActionRecord).filter_by(kind=kind).count()


def _topic_rows() -> list[ButlerTopicState]:
    with get_db_session() as session:
        return list(session.query(ButlerTopicState).all())


async def test_opening_precedes_primary_reply(make_orchestrator):
    env = make_orchestrator(
        llm_responses=["傍晚的客厅安静着。"],
        think_results=[_thinking_result(ThinkAction.REPLY, "我来接一句。")],
    )

    await env.orchestrator.handle_message(_message())

    assert [item[0] for item in env.port.sent] == ["butler", "a"]
    assert env.port.sent[0][1] == "butler_opening"
    assert env.port.sent[1][1] == "primary_reply"
    assert _action_count("opening") == 1
    assert _topic_rows()[0].budget_used == 0


async def test_opening_is_idempotent_for_same_message(make_orchestrator):
    env = make_orchestrator(
        llm_responses=["傍晚的客厅安静着。", "第二次不该出现。"],
        think_results=[
            _thinking_result(ThinkAction.REPLY, "收到。"),
            _thinking_result(ThinkAction.REPLY, "收到。"),
        ],
    )

    await env.orchestrator.handle_message(_message(message_id="m1"))
    await env.orchestrator.handle_message(_message(message_id="m1"))

    opening_sent = [item for item in env.port.sent if item[1] == "butler_opening"]
    assert len(opening_sent) == 1
    assert _action_count("opening") == 1


async def test_new_topic_on_silence_gap(make_orchestrator):
    env = make_orchestrator(
        llm_responses=["傍晚的客厅安静着。", "夜深了。"],
        think_results=[
            _thinking_result(ThinkAction.REPLY, "好。"),
            _thinking_result(ThinkAction.REPLY, "好。"),
        ],
    )

    await env.orchestrator.handle_message(_message(message_id="m1", at=env.t0))
    await env.orchestrator.handle_message(
        _message(message_id="m2", at=env.t0 + timedelta(minutes=31)),
    )

    rows = _topic_rows()
    assert len(rows) == 2
    assert {row.trigger_type for row in rows} == {"session_first", "silence_gap"}
    assert _action_count("opening") == 2


async def test_no_new_topic_within_threshold(make_orchestrator):
    env = make_orchestrator(
        llm_responses=["傍晚的客厅安静着。"],
        think_results=[
            _thinking_result(ThinkAction.REPLY, "好。"),
            _thinking_result(ThinkAction.REPLY, "好。"),
        ],
    )

    await env.orchestrator.handle_message(_message(message_id="m1", at=env.t0))
    await env.orchestrator.handle_message(
        _message(message_id="m2", at=env.t0 + timedelta(minutes=29)),
    )

    assert len(_topic_rows()) == 1
    assert _action_count("opening") == 1


async def test_summon_before_speak_for(make_orchestrator):
    env = make_orchestrator(
        llm_responses=["傍晚的客厅安静着。"],
        think_results=[
            _thinking_result(ThinkAction.SILENT),
            _thinking_result(ThinkAction.REPLY, "我在。"),
        ],
    )

    await env.orchestrator.handle_message(_message())

    role_sent = [item for item in env.port.sent if item[0] == "a" and item[1] == "butler_interjection"]
    assert len(role_sent) == 1
    assert _action_count("summon") == 1
    assert _action_count("speak_for") == 0


async def test_speak_for_when_summon_gets_no_reply(make_orchestrator):
    env = make_orchestrator(
        llm_responses=["傍晚的客厅安静着。", "好呀，我在听。"],
        think_results=[
            _thinking_result(ThinkAction.SILENT),
            _thinking_result(ThinkAction.SILENT),
        ],
    )

    await env.orchestrator.handle_message(_message())

    assert _action_count("summon") == 1
    assert _action_count("speak_for") == 1
    assert any(item[1] == "butler_speak" for item in env.port.sent)


async def test_budget_exhausted_stops_output(make_orchestrator):
    env = make_orchestrator(
        llm_responses=["傍晚的客厅安静着。"],
        think_results=[
            _thinking_result(ThinkAction.SILENT),
            _thinking_result(ThinkAction.SILENT),
            _thinking_result(ThinkAction.SILENT),
            _thinking_result(ThinkAction.SILENT),
        ],
        budget_limit=1,
    )

    await env.orchestrator.handle_message(_message(message_id="m1", at=env.t0))
    first_count = len(env.port.sent)
    llm_calls = env.llm.calls

    await env.orchestrator.handle_message(
        _message(message_id="m2", at=env.t0 + timedelta(minutes=1)),
    )

    assert len(env.port.sent) == first_count
    assert env.llm.calls == llm_calls
    assert _action_count("budget_exhausted") >= 1


async def test_opening_failure_does_not_block_primary(make_orchestrator):
    env = make_orchestrator(
        llm_responses=[RuntimeError("opening boom")],
        think_results=[_thinking_result(ThinkAction.REPLY, "主回复照常。")],
    )

    await env.orchestrator.handle_message(_message())

    assert env.port.sent[-1][0] == "a"
    assert env.port.sent[-1][1] == "primary_reply"
    assert _action_count("opening_failed") == 1
    assert _topic_rows()[0].opening_outcome == "failed"


async def test_notify_message_does_not_open(make_orchestrator):
    env = make_orchestrator(
        llm_responses=[],
        think_results=[],
    )

    await env.orchestrator.handle_message(_message(is_notify=True))

    assert _action_count("opening") == 0
    assert _topic_rows() == []


async def test_closure_round_once_per_topic(make_orchestrator):
    env = make_orchestrator(
        llm_responses=[""],
        think_results=[
            _thinking_result(ThinkAction.SILENT),
            _thinking_result(ThinkAction.SILENT),
            _thinking_result(ThinkAction.REPLY, "我来回答。"),
        ],
        opening_enabled=False,
        budget_limit=3,
    )

    await env.orchestrator.handle_message(_message(text="我们要不要吃饭？"))

    assert _action_count("closure") == 1
    assert env.orchestrator._closure_used_topic_id

    await env.orchestrator.handle_message(
        _message(text="那到底要不要？", message_id="m2", at=env.t0 + timedelta(minutes=1)),
    )

    assert _action_count("closure") == 1


async def test_three_creation_paths_share_closure_config(make_orchestrator, monkeypatch):
    env = make_orchestrator(
        llm_responses=[],
        think_results=[],
        opening_timeout=9.5,
        session_id="session-paths",
    )
    orchestrator = env.orchestrator

    from src.maisaka.agent_autonomy.butler import Butler

    created_configs: list[float] = []
    real_butler = Butler

    def _spy_butler(*args, **kwargs):
        instance = real_butler(*args, **kwargs)
        created_configs.append(instance._closure_config.opening_timeout_seconds)
        return instance

    monkeypatch.setattr("src.maisaka.agent_autonomy.orchestrator.Butler", _spy_butler)

    # 路径 1：延迟装配（handle_message / _schedule_primary_reply 共用）
    orchestrator._butler = None
    orchestrator._primary_agent_id = "a"
    orchestrator._ensure_butler()
    assert created_configs[-1] == 9.5

    # 路径 2：activate_agent 的 is_primary 分支
    orchestrator._butler = None
    orchestrator._primary_agent_id = None
    orchestrator._active_agents = {}
    assert await orchestrator.activate_agent("c", "test_activation") is True
    assert created_configs[-1] == 9.5

    # 路径 3：restore_agent 的 is_primary 分支
    orchestrator._butler = None
    orchestrator._primary_agent_id = None
    orchestrator._active_agents = {}
    orchestrator.restore_agent("d", is_primary=True)
    assert created_configs[-1] == 9.5

    assert orchestrator._butler._closure_config.opening_timeout_seconds == 9.5