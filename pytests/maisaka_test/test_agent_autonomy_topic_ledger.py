"""TopicLedger 的话题起点判定、预算扣减与记账行为单测。

依赖外部在进程启动前设置 MAIBOT_DATA_DIR（engine 在 import 时定型），
避免污染生产库。
"""

import asyncio

from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest

from sqlalchemy import inspect

from src.common.database.database import engine, get_db_session
from src.common.database.database_model import ButlerTopicActionRecord, ButlerTopicState
from src.maisaka.agent_autonomy import topic_ledger as topic_ledger_module
from src.maisaka.agent_autonomy.butler_closure import (
    ActionKind,
    ButlerClosureConfig,
    OpeningOutcome,
    TopicTrigger,
)
from src.maisaka.agent_autonomy.topic_ledger import TopicLedger


SESSION_ID = "session-ledger-test"
T0 = datetime(2026, 11, 20, 12, 0, 0)


@pytest.fixture(autouse=True)
def clean_tables():
    """每个用例前清空两张新表，保证断言只看本用例数据。"""
    with get_db_session() as session:
        session.query(ButlerTopicActionRecord).delete()
        session.query(ButlerTopicState).delete()
    yield


def _ledger(budget_limit: int = 2) -> TopicLedger:
    return TopicLedger(SESSION_ID, ButlerClosureConfig(budget_limit=budget_limit))


def _count_topics() -> int:
    with get_db_session() as session:
        return session.query(ButlerTopicState).filter_by(session_id=SESSION_ID).count()


async def test_first_message_creates_session_first_topic():
    ledger = _ledger()
    context = await ledger.resolve(message_id="m1", message_at=T0, session_last_active_at=None)

    assert context.trigger is TopicTrigger.SESSION_FIRST
    assert context.is_new is True
    assert context.budget_used == 0
    assert context.closure_used is False
    assert ledger.current() == context


async def test_within_threshold_reuses_topic():
    ledger = _ledger()
    first = await ledger.resolve(message_id="m1", message_at=T0, session_last_active_at=None)
    second = await ledger.resolve(
        message_id="m2",
        message_at=T0 + timedelta(minutes=29),
        session_last_active_at=T0,
    )

    assert second.topic_id == first.topic_id
    assert second.is_new is False


async def test_beyond_threshold_starts_new_topic_and_closes_old():
    ledger = _ledger()
    first = await ledger.resolve(message_id="m1", message_at=T0, session_last_active_at=None)
    second = await ledger.resolve(
        message_id="m2",
        message_at=T0 + timedelta(minutes=31),
        session_last_active_at=T0,
    )

    assert second.trigger is TopicTrigger.SILENCE_GAP
    assert second.is_new is True
    assert second.topic_id != first.topic_id
    assert second.silence_seconds == pytest.approx(31 * 60)

    with get_db_session() as session:
        old_row = session.query(ButlerTopicState).filter_by(topic_id=first.topic_id).one()
        assert old_row.ended_reason == "silence_gap"


async def test_concurrent_resolve_same_message_id_creates_one_row():
    ledger = _ledger()
    await asyncio.gather(
        ledger.resolve(message_id="X", message_at=T0, session_last_active_at=None),
        ledger.resolve(message_id="X", message_at=T0, session_last_active_at=None),
    )

    assert _count_topics() == 1


async def test_concurrent_resolve_different_messages_creates_one_row():
    ledger = _ledger()
    await asyncio.gather(
        ledger.resolve(message_id="A", message_at=T0, session_last_active_at=None),
        ledger.resolve(message_id="B", message_at=T0, session_last_active_at=None),
    )

    assert _count_topics() == 1


async def test_budget_consume_caps_at_limit():
    ledger = _ledger(budget_limit=2)
    context = await ledger.resolve(message_id="m1", message_at=T0, session_last_active_at=None)

    first = await ledger.try_consume(context.topic_id, ActionKind.SUMMON)
    second = await ledger.try_consume(context.topic_id, ActionKind.SUMMON)
    third = await ledger.try_consume(context.topic_id, ActionKind.SUMMON)

    assert (first.granted, first.used) == (True, 1)
    assert (second.granted, second.used) == (True, 2)
    assert third.granted is False
    assert third.exhausted is True
    assert third.used == 2


async def test_budget_zero_denies_immediately():
    ledger = _ledger(budget_limit=0)
    context = await ledger.resolve(message_id="m1", message_at=T0, session_last_active_at=None)

    decision = await ledger.try_consume(context.topic_id, ActionKind.SPEAK_FOR)

    assert decision.granted is False
    assert decision.exhausted is True


async def test_mark_opening_and_record_action_persist():
    ledger = _ledger()
    context = await ledger.resolve(message_id="m1", message_at=T0, session_last_active_at=None)

    await ledger.mark_opening(
        context.topic_id,
        OpeningOutcome.SENT,
        chars=18,
        missing=("emotion",),
    )
    await ledger.record_action(
        context.topic_id,
        ActionKind.OPENING,
        outcome="sent",
        detail="present=3; emotion=neutral",
    )

    with get_db_session() as session:
        state = session.query(ButlerTopicState).filter_by(topic_id=context.topic_id).one()
        assert state.opening_outcome == "sent"
        assert state.opening_chars == 18
        assert state.scene_missing == "emotion"
        record = session.query(ButlerTopicActionRecord).filter_by(topic_id=context.topic_id).one()
        assert record.kind == "opening"
        assert record.detail == "present=3; emotion=neutral"


async def test_record_action_swallows_write_failure(monkeypatch):
    ledger = _ledger()
    context = await ledger.resolve(message_id="m1", message_at=T0, session_last_active_at=None)

    warnings: list[tuple] = []
    reports: list[tuple] = []

    class _BrokenQuery:
        def filter_by(self, *args, **kwargs):
            return self

        def first(self):
            return None

    class _BrokenSession:
        def query(self, *args, **kwargs):
            return _BrokenQuery()

        def add(self, *args, **kwargs):
            return None

        def commit(self):
            raise RuntimeError("boom")

        def rollback(self):
            return None

    class _FakeLogger:
        def warning(self, *args, **kwargs):
            warnings.append((args, kwargs))

    class _FakePort:
        def report(self, *args, **kwargs):
            reports.append((args, kwargs))

    @contextmanager
    def _broken_db_session(auto_commit=True):
        yield _BrokenSession()

    monkeypatch.setattr(topic_ledger_module, "get_db_session", _broken_db_session)
    monkeypatch.setattr(topic_ledger_module, "logger", _FakeLogger())
    monkeypatch.setattr(topic_ledger_module, "get_error_escalation_port", lambda: _FakePort())

    await ledger.record_action(context.topic_id, ActionKind.SUMMON)

    assert len(warnings) == 1
    assert len(reports) == 1


def test_legacy_speaker_change_columns_unchanged():
    columns = {
        column["name"]
        for column in inspect(engine).get_columns("agent_autonomy_speaker_change_records")
    }

    assert columns == {
        "record_id",
        "session_id",
        "from_agent_id",
        "to_agent_id",
        "change_type",
        "change_reason",
        "transfer_type",
        "decision_source",
        "created_at",
    }


def test_new_tables_created_by_create_all():
    tables = set(inspect(engine).get_table_names())

    assert "butler_topic_states" in tables
    assert "butler_topic_action_records" in tables