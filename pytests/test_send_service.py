"""发送服务回归测试。"""

import sys
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from src.chat.message_receive.chat_manager import BotChatSession
from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
from src.services import send_service


class _FakePlatformIOManager:
    """用于测试的 Platform IO 管理器假对象。"""

    def __init__(self, delivery_batch: Any) -> None:
        self._delivery_batch = delivery_batch
        self.ensure_calls = 0
        self.sent_messages: List[Dict[str, Any]] = []

    async def ensure_send_pipeline_ready(self) -> None:
        self.ensure_calls += 1

    def build_route_key_from_message(self, message: Any) -> Any:
        del message
        return SimpleNamespace(platform="qq")

    async def send_message(self, message: Any, route_key: Any, metadata: Dict[str, Any]) -> Any:
        self.sent_messages.append(
            {
                "message": message,
                "message_id_before_send": str(getattr(message, "message_id", "") or ""),
                "route_key": route_key,
                "metadata": metadata,
            }
        )
        return self._delivery_batch


def _build_private_stream() -> BotChatSession:
    return BotChatSession(
        session_id="test-session",
        platform="qq",
        user_id="target-user",
        group_id=None,
    )


def _build_group_stream() -> BotChatSession:
    return BotChatSession(
        session_id="group-session",
        platform="qq",
        user_id="target-user",
        group_id="target-group",
    )


def test_inherit_platform_io_route_metadata_falls_back_to_bot_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(send_service, "get_bot_account", lambda platform: "bot-qq" if platform == "qq" else "")

    metadata = send_service._inherit_platform_io_route_metadata(_build_private_stream())

    assert metadata["platform_io_account_id"] == "bot-qq"
    assert metadata["platform_io_target_user_id"] == "target-user"


@pytest.mark.asyncio
async def test_text_to_stream_delegates_to_platform_io(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.common.message_server.api as message_server_api

    fake_manager = _FakePlatformIOManager(
        delivery_batch=SimpleNamespace(
            has_success=True,
            sent_receipts=[
                SimpleNamespace(
                    driver_id="plugin.qq.sender",
                    external_message_id="real-message-id",
                    metadata={
                        "adapter_callbacks": [
                            {
                                "name": "message_id_echo",
                                "payload": {
                                    "content": {
                                        "type": "echo",
                                        "echo": "send_api_test",
                                        "actual_id": "real-message-id",
                                    }
                                },
                            }
                        ]
                    },
                )
            ],
            failed_receipts=[],
            route_key=SimpleNamespace(platform="qq"),
        )
    )
    callback_payloads: List[Dict[str, Any]] = []
    stored_messages: List[Any] = []

    async def fake_echo_handler(payload: Dict[str, Any]) -> None:
        """记录发送成功后的消息 ID 回调。"""

        callback_payloads.append(payload)

    monkeypatch.setattr(send_service, "get_platform_io_manager", lambda: fake_manager)
    monkeypatch.setattr(send_service, "get_bot_account", lambda platform: "bot-qq")
    monkeypatch.setattr(
        send_service._chat_manager,
        "get_session_by_session_id",
        lambda stream_id: _build_private_stream() if stream_id == "test-session" else None,
    )
    monkeypatch.setattr(
        send_service.MessageUtils,
        "store_message_to_db",
        lambda message: stored_messages.append(message),
    )
    monkeypatch.setattr(
        message_server_api,
        "global_api",
        SimpleNamespace(_custom_message_handlers={"message_id_echo": fake_echo_handler}),
    )

    result = await send_service.text_to_stream(text="你好", stream_id="test-session")

    assert result is True
    assert fake_manager.ensure_calls == 1
    assert len(fake_manager.sent_messages) == 1
    assert fake_manager.sent_messages[0]["metadata"] == {"show_log": False}
    assert len(stored_messages) == 1
    assert stored_messages[0].message_id == "real-message-id"
    assert callback_payloads == [
        {
            "content": {
                "type": "echo",
                "echo": "send_api_test",
                "actual_id": "real-message-id",
            }
        }
    ]


@pytest.mark.asyncio
async def test_text_to_stream_with_message_returns_sent_message(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_manager = _FakePlatformIOManager(
        delivery_batch=SimpleNamespace(
            has_success=True,
            sent_receipts=[
                SimpleNamespace(
                    driver_id="plugin.qq.sender",
                    external_message_id="real-message-id",
                    metadata={},
                )
            ],
            failed_receipts=[],
            route_key=SimpleNamespace(platform="qq"),
        )
    )
    stored_messages: List[Any] = []

    monkeypatch.setattr(send_service, "get_platform_io_manager", lambda: fake_manager)
    monkeypatch.setattr(send_service, "get_bot_account", lambda platform: "bot-qq")
    monkeypatch.setattr(
        send_service._chat_manager,
        "get_session_by_session_id",
        lambda stream_id: _build_private_stream() if stream_id == "test-session" else None,
    )
    monkeypatch.setattr(
        send_service.MessageUtils,
        "store_message_to_db",
        lambda message: stored_messages.append(message),
    )

    sent_message = await send_service.text_to_stream_with_message(text="你好", stream_id="test-session")

    assert sent_message is not None
    assert sent_message.message_id == "real-message-id"
    assert fake_manager.ensure_calls == 1
    assert len(stored_messages) == 1
    assert stored_messages[0].message_id == "real-message-id"


@pytest.mark.asyncio
async def test_text_to_stream_with_message_triggers_memory_and_syncs_maisaka_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_manager = _FakePlatformIOManager(
        delivery_batch=SimpleNamespace(
            has_success=True,
            sent_receipts=[
                SimpleNamespace(
                    driver_id="plugin.qq.sender",
                    external_message_id="real-message-id",
                    metadata={},
                )
            ],
            failed_receipts=[],
            route_key=SimpleNamespace(platform="qq"),
        )
    )
    stored_messages: List[Any] = []
    memory_events: List[str] = []
    history_events: List[tuple[str, str]] = []

    class FakeMemoryAutomationService:
        async def on_message_sent(self, message: Any) -> None:
            memory_events.append(str(message.message_id))

    class FakeRuntime:
        def append_sent_message_to_chat_history(self, message: Any, *, source_kind: str = "guided_reply") -> None:
            history_events.append((str(message.message_id), source_kind))

    monkeypatch.setattr(send_service, "get_platform_io_manager", lambda: fake_manager)
    monkeypatch.setattr(send_service, "get_bot_account", lambda platform: "bot-qq")
    monkeypatch.setattr(
        send_service._chat_manager,
        "get_session_by_session_id",
        lambda stream_id: _build_private_stream() if stream_id == "test-session" else None,
    )
    monkeypatch.setattr(
        send_service.MessageUtils,
        "store_message_to_db",
        lambda message: stored_messages.append(message),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.services.memory_flow_service",
        SimpleNamespace(memory_automation_service=FakeMemoryAutomationService()),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.chat.heart_flow.heartflow_manager",
        SimpleNamespace(heartflow_manager=SimpleNamespace(heartflow_chat_list={"test-session": FakeRuntime()})),
    )

    sent_message = await send_service.text_to_stream_with_message(
        text="你好",
        stream_id="test-session",
        sync_to_maisaka_history=True,
        maisaka_source_kind="guided_reply",
    )

    assert sent_message is not None
    assert sent_message.message_id == "real-message-id"
    assert fake_manager.ensure_calls == 1
    assert len(stored_messages) == 1
    assert stored_messages[0].message_id == "real-message-id"
    assert memory_events == ["real-message-id"]
    assert history_events == [("real-message-id", "guided_reply")]


@pytest.mark.asyncio
async def test_text_to_stream_returns_false_when_platform_io_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_manager = _FakePlatformIOManager(
        delivery_batch=SimpleNamespace(
            has_success=False,
            sent_receipts=[],
            failed_receipts=[
                SimpleNamespace(
                    driver_id="plugin.qq.sender",
                    status="failed",
                    error="network error",
                )
            ],
            route_key=SimpleNamespace(platform="qq"),
        )
    )

    monkeypatch.setattr(send_service, "get_platform_io_manager", lambda: fake_manager)
    monkeypatch.setattr(send_service, "get_bot_account", lambda platform: "bot-qq")
    monkeypatch.setattr(
        send_service._chat_manager,
        "get_session_by_session_id",
        lambda stream_id: _build_private_stream() if stream_id == "test-session" else None,
    )

    result = await send_service.text_to_stream(text="发送失败", stream_id="test-session")

    assert result is False
    assert fake_manager.ensure_calls == 1
    assert len(fake_manager.sent_messages) == 1


@pytest.mark.asyncio
async def test_private_outbound_message_preserves_bot_sender_and_receiver_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(send_service, "get_bot_account", lambda platform: "bot-qq")
    monkeypatch.setattr(
        send_service._chat_manager,
        "get_session_by_session_id",
        lambda stream_id: _build_private_stream() if stream_id == "test-session" else None,
    )

    outbound_message = send_service._build_outbound_session_message(
        message_sequence=MessageSequence(components=[TextComponent(text="你好")]),
        stream_id="test-session",
        processed_plain_text="你好",
    )

    assert outbound_message is not None
    maim_message = await outbound_message.to_maim_message()

    assert maim_message.message_info.user_info is not None
    assert maim_message.message_info.user_info.user_id == "bot-qq"
    assert maim_message.message_info.group_info is None
    assert maim_message.message_info.sender_info is not None
    assert maim_message.message_info.sender_info.user_info is not None
    assert maim_message.message_info.sender_info.user_info.user_id == "bot-qq"
    assert maim_message.message_info.receiver_info is not None
    assert maim_message.message_info.receiver_info.user_info is not None
    assert maim_message.message_info.receiver_info.user_info.user_id == "target-user"


@pytest.mark.asyncio
async def test_group_outbound_message_preserves_bot_sender_and_target_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(send_service, "get_bot_account", lambda platform: "bot-qq")
    monkeypatch.setattr(
        send_service._chat_manager,
        "get_session_by_session_id",
        lambda stream_id: _build_group_stream() if stream_id == "group-session" else None,
    )

    outbound_message = send_service._build_outbound_session_message(
        message_sequence=MessageSequence(components=[TextComponent(text="大家好")]),
        stream_id="group-session",
        processed_plain_text="大家好",
    )

    assert outbound_message is not None
    maim_message = await outbound_message.to_maim_message()

    assert maim_message.message_info.user_info is not None
    assert maim_message.message_info.user_info.user_id == "bot-qq"
    assert maim_message.message_info.group_info is not None
    assert maim_message.message_info.group_info.group_id == "target-group"
    assert maim_message.message_info.receiver_info is not None
    assert maim_message.message_info.receiver_info.group_info is not None
    assert maim_message.message_info.receiver_info.group_info.group_id == "target-group"
