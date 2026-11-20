"""Butler 收尾能力单测（批次 4：能力就位，生产未接线）。

覆盖 T4.1–T4.12。依赖外部在进程启动前设置 MAIBOT_DATA_DIR。
"""

import asyncio
import time

from copy import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.common.database.database import get_db_session
from src.common.database.database_model import ButlerTopicActionRecord, ButlerTopicState
from src.maisaka.agent_autonomy import butler as butler_module
from src.maisaka.agent_autonomy.butler import Butler
from src.maisaka.agent_autonomy.butler_closure import (
    ButlerClosureConfig,
    TopicContext,
    TopicTrigger,
)


SESSION_ID = "session-butler-opening"
TZ_CN = timezone(timedelta(hours=8))
T0 = datetime(2026, 11, 20, 20, 0, 0, tzinfo=TZ_CN)


class _FakeLogger:
    def __init__(self):
        self.warnings: list[tuple] = []

    def info(self, *args, **kwargs):
        return None

    def debug(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        self.warnings.append((args, kwargs))


class _FakePort:
    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []

    async def send_message(self, *, session_id, message, agent_id, source):
        self.sent.append((message.components[0].text, agent_id, source))
        return SimpleNamespace(success=True)


class _FakeErrorPort:
    def __init__(self):
        self.reports: list[tuple] = []

    def report(self, *args, **kwargs):
        self.reports.append((args, kwargs))


class _FakeLLM:
    def __init__(self, response: str = "", *, delay: float = 0.0, raises: Exception | None = None):
        self.response = response
        self.delay = delay
        self.raises = raises
        self.calls = 0

    async def generate_response_with_messages(self, *args, **kwargs):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raises is not None:
            raise self.raises
        return SimpleNamespace(response=self.response)


def _agent(agent_id: str, name: str, *, is_butler: bool = False):
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


class _Registry:
    def __init__(self, agents):
        self._agents = agents

    def list_agents(self):
        return self._agents


@pytest.fixture(autouse=True)
def clean_tables():
    with get_db_session() as session:
        session.query(ButlerTopicActionRecord).delete()
        session.query(ButlerTopicState).delete()
    yield


@pytest.fixture
def env(monkeypatch):
    fake_logger = _FakeLogger()
    fake_port = _FakePort()
    fake_error_port = _FakeErrorPort()

    monkeypatch.setattr(
        butler_module,
        "get_agent_config_provider",
        lambda: _Registry([
            _agent("butler", "丽塔", is_butler=True),
            _agent("a", "阿一"),
            _agent("b", "小乙"),
        ]),
    )
    monkeypatch.setattr(butler_module, "get_message_port_v2", lambda: fake_port)
    monkeypatch.setattr(butler_module, "_now", lambda: T0)
    monkeypatch.setattr(butler_module, "logger", fake_logger)
    monkeypatch.setattr(
        "src.core.error_escalation_port_registry.get_error_escalation_port",
        lambda: fake_error_port,
    )

    def _make(config: ButlerClosureConfig | None = None) -> Butler:
        return Butler(
            "a",
            SESSION_ID,
            reminder_manager=SimpleNamespace(),
            message_port=fake_port,
            closure_config=config,
        )

    return SimpleNamespace(
        make=_make,
        logger=fake_logger,
        port=fake_port,
        error_port=fake_error_port,
    )


async def _topic(butler: Butler):
    return await butler.ensure_topic(
        message_id="m1",
        message_at=T0,
        session_last_active_at=None,
    )


def _action_count(kind: str) -> int:
    with get_db_session() as session:
        return session.query(ButlerTopicActionRecord).filter_by(kind=kind).count()


def _state(topic_id: str) -> ButlerTopicState:
    with get_db_session() as session:
        return session.query(ButlerTopicState).filter_by(topic_id=topic_id).one()


def test_build_scene_filters_unknown_ids(env):
    butler = env.make()
    scene = butler.build_scene(["a", "b"], {})

    assert tuple(agent.agent_id for agent in scene.present) == ("a", "b")
    assert scene.missing == ()

    scene_with_unknown = butler.build_scene(["a", "zzz"], {})
    assert tuple(agent.agent_id for agent in scene_with_unknown.present) == ("a",)
    assert "zzz" in scene_with_unknown.missing


def test_build_scene_neutral_when_no_emotion(env):
    butler = env.make()
    scene = butler.build_scene(["a"], {})

    assert scene.emotion_hint is None
    _, user_prompt = butler._build_opening_prompt(scene, "今天好累")
    assert "客厅安静着" in user_prompt
    for word in ("低落", "开心", "难过", "兴奋"):
        assert word not in user_prompt


async def test_try_opening_calls_llm_once(env, monkeypatch):
    fake_llm = _FakeLLM("傍晚的客厅安静着。")
    monkeypatch.setattr("src.core.adapters.llm_service_port.get_llm_service", lambda: fake_llm)

    butler = env.make()
    topic = await _topic(butler)
    scene = butler.build_scene(["a"], {})

    assert await butler.try_opening(topic, scene, "今天好累") is True
    assert fake_llm.calls == 1
    assert len(env.port.sent) == 1


async def test_try_opening_skips_on_empty(env, monkeypatch):
    fake_llm = _FakeLLM("")
    monkeypatch.setattr("src.core.adapters.llm_service_port.get_llm_service", lambda: fake_llm)

    butler = env.make()
    topic = await _topic(butler)

    assert await butler.try_opening(topic, butler.build_scene(["a"], {}), "今天好累") is False
    assert len(env.port.sent) == 0
    assert _state(topic.topic_id).opening_outcome == "skipped"


async def test_try_opening_skips_on_none(env, monkeypatch):
    fake_llm = _FakeLLM("NONE")
    monkeypatch.setattr("src.core.adapters.llm_service_port.get_llm_service", lambda: fake_llm)

    butler = env.make()
    topic = await _topic(butler)

    assert await butler.try_opening(topic, butler.build_scene(["a"], {}), "今天好累") is False
    assert len(env.port.sent) == 0
    assert _state(topic.topic_id).opening_outcome == "skipped"


async def test_try_opening_failure_does_not_escape(env, monkeypatch):
    fake_llm = _FakeLLM(raises=RuntimeError("boom"))
    monkeypatch.setattr("src.core.adapters.llm_service_port.get_llm_service", lambda: fake_llm)

    butler = env.make()
    topic = await _topic(butler)

    assert await butler.try_opening(topic, butler.build_scene(["a"], {}), "今天好累") is False
    assert _state(topic.topic_id).opening_outcome == "failed"
    assert len(env.logger.warnings) == 1
    assert len(env.error_port.reports) == 1


async def test_try_opening_timeout_is_bounded(env, monkeypatch):
    fake_llm = _FakeLLM("迟到的开场", delay=10)
    monkeypatch.setattr("src.core.adapters.llm_service_port.get_llm_service", lambda: fake_llm)

    butler = env.make(ButlerClosureConfig(opening_timeout_seconds=0.5))
    topic = await _topic(butler)

    started = time.perf_counter()
    assert await butler.try_opening(topic, butler.build_scene(["a"], {}), "今天好累") is False
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert _state(topic.topic_id).opening_outcome == "failed"


async def test_try_opening_truncates_long_text(env, monkeypatch):
    fake_llm = _FakeLLM("第一句。第二句。" * 50)
    monkeypatch.setattr("src.core.adapters.llm_service_port.get_llm_service", lambda: fake_llm)

    butler = env.make(ButlerClosureConfig(opening_max_chars=120))
    topic = await _topic(butler)

    assert await butler.try_opening(topic, butler.build_scene(["a"], {}), "今天好累") is True
    assert _state(topic.topic_id).opening_chars <= 120


async def test_summon_budget_exhausted(env):
    butler = env.make(ButlerClosureConfig(budget_limit=1))
    topic = await _topic(butler)

    first = await butler.summon_or_fallback(topic=topic, present_ids=["a"], user_text="在吗")
    second = await butler.summon_or_fallback(topic=topic, present_ids=["a"], user_text="在吗")

    assert first is not None
    assert second is None
    assert _action_count("budget_exhausted") == 1


async def test_summon_without_present_agents(env):
    butler = env.make()
    topic = await _topic(butler)

    assert await butler.summon_or_fallback(topic=topic, present_ids=[], user_text="在吗") is None
    assert _action_count("summon_dropped") == 1
    assert _state(topic.topic_id).budget_used == 0


def test_should_close_conditions(env):
    butler = env.make()
    topic = TopicContext(
        topic_id="tg:test:1",
        session_id="s",
        trigger=TopicTrigger.SESSION_FIRST,
        started_at=T0,
        silence_seconds=0.0,
        budget_limit=2,
        budget_used=0,
        closure_used=False,
        is_new=False,
    )

    assert butler.should_close("我们今天去吃饭吗？", topic) is True
    assert butler.should_close("今天天气不错。", topic) is False
    assert butler.should_close("我们今天去吃饭吗？", replace(topic, closure_used=True)) is False

    exhausted = replace(topic, budget_used=2)
    assert butler.should_close("我们今天去吃饭吗？", exhausted) is False


async def test_speak_for_consumes_budget(env, monkeypatch):
    butler = env.make(ButlerClosureConfig(budget_limit=1))
    topic = await _topic(butler)

    async def _fake_speak_self(*args, **kwargs):
        return "好呀"

    monkeypatch.setattr(butler, "speak_self", _fake_speak_self)

    assert await butler.speak_for(topic=topic, user_text="在吗") is True
    assert await butler.speak_for(topic=topic, user_text="在吗") is False
    assert _state(topic.topic_id).budget_used == 1