from datetime import datetime
from types import SimpleNamespace

import time

import pytest

from src.chat.heart_flow import heartflow_manager as heartflow_manager_module
from src.chat.heart_flow.heartflow_manager import HEARTFLOW_ACTIVE_RETENTION_SECONDS, HeartflowManager
from src.chat.message_receive.message import SessionMessage
from src.common.data_models.mai_message_data_model import MessageInfo, UserInfo
from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
from src.maisaka import runtime as runtime_module
from src.maisaka.reasoning_engine import MaisakaReasoningEngine
from src.maisaka.runtime import MAX_RETAINED_MESSAGE_CACHE_SIZE, MaisakaHeartFlowChatting


def _build_runtime_with_messages(message_count: int) -> MaisakaHeartFlowChatting:
    runtime = object.__new__(MaisakaHeartFlowChatting)
    runtime.log_prefix = "[test]"
    runtime.message_cache = [SimpleNamespace(message_id=f"msg-{index}") for index in range(message_count)]
    runtime._last_processed_index = message_count
    return runtime


def test_prune_processed_message_cache_keeps_bounded_recent_window() -> None:
    runtime = _build_runtime_with_messages(MAX_RETAINED_MESSAGE_CACHE_SIZE + 25)

    runtime._prune_processed_message_cache()

    assert len(runtime.message_cache) == MAX_RETAINED_MESSAGE_CACHE_SIZE
    assert runtime.message_cache[0].message_id == "msg-25"
    assert runtime._last_processed_index == MAX_RETAINED_MESSAGE_CACHE_SIZE


def test_prune_processed_message_cache_keeps_pending_messages() -> None:
    runtime = _build_runtime_with_messages(MAX_RETAINED_MESSAGE_CACHE_SIZE + 25)
    runtime._last_processed_index = 20

    runtime._prune_processed_message_cache()

    assert len(runtime.message_cache) == MAX_RETAINED_MESSAGE_CACHE_SIZE + 5
    assert runtime.message_cache[0].message_id == "msg-20"
    assert runtime._last_processed_index == 0


def test_collect_pending_messages_uses_single_pending_received_time() -> None:
    runtime = _build_runtime_with_messages(2)
    runtime._last_processed_index = 0
    runtime._oldest_pending_message_received_at = 123.0
    runtime._last_message_received_at = 456.0
    runtime._reply_latency_measurement_started_at = None

    pending_messages = runtime._collect_pending_messages()

    assert [message.message_id for message in pending_messages] == ["msg-0", "msg-1"]
    assert runtime._reply_latency_measurement_started_at == 123.0
    assert runtime._oldest_pending_message_received_at is None


def _build_db_message(message_id: str, user_id: str) -> SessionMessage:
    message = SessionMessage(
        message_id=message_id,
        timestamp=datetime(2026, 5, 29, 12, 0, 0),
        platform="qq",
    )
    message.session_id = "session-1"
    message.message_info = MessageInfo(
        user_info=UserInfo(
            user_id=user_id,
            user_nickname=user_id,
        ),
        additional_config={},
    )
    message.raw_message = MessageSequence([TextComponent(f"text-{message_id}")])
    message.processed_plain_text = f"text-{message_id}"
    message.is_notify = False
    return message


@pytest.mark.asyncio
async def test_restore_recent_context_from_db_marks_restored_messages_processed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = object.__new__(MaisakaHeartFlowChatting)
    runtime.session_id = "session-1"
    runtime.log_prefix = "[test]"
    runtime._chat_history = []
    runtime.message_cache = []
    runtime._last_processed_index = 0

    restored_sources: list[str] = []

    class FakeReasoningEngine:
        async def _build_history_message(
            self,
            message: SessionMessage,
            *,
            source_kind: str = "user",
        ) -> SimpleNamespace:
            restored_sources.append(source_kind)
            return SimpleNamespace(message_id=message.message_id, source_kind=source_kind)

    runtime._reasoning_engine = FakeReasoningEngine()
    monkeypatch.setattr(MaisakaHeartFlowChatting, "_max_context_size", property(lambda self: 12))
    monkeypatch.setattr(runtime_module, "get_bot_account", lambda platform: "bot-id")

    captured_kwargs: dict[str, object] = {}

    def fake_find_messages(**kwargs: object) -> list[SessionMessage]:
        captured_kwargs.update(kwargs)
        return [
            _build_db_message("user-message", "user-id"),
            _build_db_message("bot-message", "bot-id"),
        ]

    monkeypatch.setattr(runtime_module, "find_messages", fake_find_messages)

    await runtime._restore_recent_context_from_db()

    assert captured_kwargs["session_id"] == "session-1"
    assert captured_kwargs["limit_mode"] == "latest"
    assert captured_kwargs["filter_command"] is True
    assert captured_kwargs["limit"] == MAX_RETAINED_MESSAGE_CACHE_SIZE
    assert restored_sources == ["user", "guided_reply"]
    assert [message.message_id for message in runtime.message_cache] == ["user-message"]
    assert runtime._last_processed_index == 1
    assert [message.message_id for message in runtime._chat_history] == ["user-message", "bot-message"]


@pytest.mark.asyncio
async def test_ingest_messages_skips_context_already_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = object.__new__(MaisakaHeartFlowChatting)
    runtime.session_id = "session-1"
    runtime.log_prefix = "[test]"
    runtime._chat_history = [SimpleNamespace(message_id="user-message")]
    engine = MaisakaReasoningEngine(runtime)

    async def fail_build_history_message(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("重复消息不应再次构建上下文")

    monkeypatch.setattr(engine, "_build_history_message", fail_build_history_message)

    await engine._ingest_messages([_build_db_message("user-message", "user-id")])

    assert [message.message_id for message in runtime._chat_history] == ["user-message"]


@pytest.mark.asyncio
async def test_heartflow_manager_evicts_lru_chat_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = HeartflowManager()
    stopped_session_ids: list[str] = []
    old_active_at = time.time() - HEARTFLOW_ACTIVE_RETENTION_SECONDS - 1

    class FakeChat:
        def __init__(self, session_id: str) -> None:
            self.session_id = session_id

        async def stop(self) -> None:
            stopped_session_ids.append(self.session_id)

    monkeypatch.setattr(heartflow_manager_module, "HEARTFLOW_MAX_ACTIVE_CHATS", 2)
    manager.heartflow_chat_list["session-1"] = FakeChat("session-1")
    manager.heartflow_chat_list["session-2"] = FakeChat("session-2")
    manager.heartflow_chat_list["session-3"] = FakeChat("session-3")
    manager._chat_last_active_at["session-1"] = old_active_at
    manager._chat_last_active_at["session-2"] = old_active_at
    manager._chat_last_active_at["session-3"] = time.time()

    await manager._evict_over_limit_chats(protected_session_id="session-3")

    assert stopped_session_ids == ["session-1"]
    assert list(manager.heartflow_chat_list) == ["session-2", "session-3"]


@pytest.mark.asyncio
async def test_heartflow_manager_keeps_recent_chats_even_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = HeartflowManager()
    stopped_session_ids: list[str] = []

    class FakeChat:
        def __init__(self, session_id: str) -> None:
            self.session_id = session_id

        async def stop(self) -> None:
            stopped_session_ids.append(self.session_id)

    monkeypatch.setattr(heartflow_manager_module, "HEARTFLOW_MAX_ACTIVE_CHATS", 2)
    for session_id in ("session-1", "session-2", "session-3"):
        manager.heartflow_chat_list[session_id] = FakeChat(session_id)
        manager._chat_last_active_at[session_id] = time.time()

    await manager._evict_over_limit_chats(protected_session_id="session-3")

    assert stopped_session_ids == []
    assert list(manager.heartflow_chat_list) == ["session-1", "session-2", "session-3"]
