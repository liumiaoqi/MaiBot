"""reply 身份接线测试（批次 4）。"""

import inspect

from types import SimpleNamespace

from src.common.data_models.message_component_data_model import MessageSequence
from src.core.types import ThinkContext
from src.services import send_service
from src.services.send_service import _build_outbound_session_message


def _patch_send_env(monkeypatch) -> None:
    session_info = SimpleNamespace(
        platform="qq",
        group_id=None,
        group_name=None,
        session_id="session-wiring",
        user_id="target_user",
    )
    monkeypatch.setattr(
        send_service,
        "get_session_info_port",
        lambda: SimpleNamespace(get_session_info=lambda sid: session_info),
    )
    monkeypatch.setattr(
        send_service,
        "get_session_query_port",
        lambda: SimpleNamespace(
            get_route_metadata=lambda sid: {},
            get_last_message=lambda sid: None,
        ),
    )
    monkeypatch.setattr(send_service, "get_bot_account", lambda platform: "bot_account")
    monkeypatch.setattr(
        send_service,
        "get_bot_config_port",
        lambda: SimpleNamespace(get_bot_nickname=lambda: "麦麦"),
    )


def test_think_context_has_thinking_agent_id():
    assert "thinking_agent_id" in inspect.signature(ThinkContext).parameters
    assert ThinkContext(messages=()).thinking_agent_id == ""


def test_outbound_message_carries_agent_identity(monkeypatch):
    _patch_send_env(monkeypatch)

    outbound = _build_outbound_session_message(
        MessageSequence(components=[]),
        "session-wiring",
        processed_plain_text="hi",
        agent_id="silver_wolf",
    )

    assert outbound is not None
    assert outbound.sender_type == "agent"
    assert outbound.sender_agent_id == "silver_wolf"
    assert outbound.message_info.user_info.user_id == "bot_account"


def test_outbound_message_without_agent_id_is_system(monkeypatch):
    _patch_send_env(monkeypatch)

    outbound = _build_outbound_session_message(
        MessageSequence(components=[]),
        "session-wiring",
        processed_plain_text="hi",
    )

    assert outbound is not None
    assert outbound.sender_type == "system"
    assert outbound.sender_agent_id is None