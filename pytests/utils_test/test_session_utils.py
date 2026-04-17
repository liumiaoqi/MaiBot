from types import SimpleNamespace

from src.chat.message_receive.chat_manager import ChatManager
from src.common.utils.utils_session import SessionUtils


def test_calculate_session_id_distinguishes_account_and_scope() -> None:
    base_session_id = SessionUtils.calculate_session_id("qq", user_id="42")
    same_base_session_id = SessionUtils.calculate_session_id("qq", user_id="42")
    account_scoped_session_id = SessionUtils.calculate_session_id("qq", user_id="42", account_id="123")
    route_scoped_session_id = SessionUtils.calculate_session_id("qq", user_id="42", account_id="123", scope="main")

    assert base_session_id == same_base_session_id
    assert account_scoped_session_id != base_session_id
    assert route_scoped_session_id != account_scoped_session_id


def test_chat_manager_register_message_uses_route_metadata() -> None:
    chat_manager = ChatManager()
    message = SimpleNamespace(
        platform="qq",
        session_id="",
        message_info=SimpleNamespace(
            user_info=SimpleNamespace(user_id="42"),
            group_info=SimpleNamespace(group_id="1000"),
            additional_config={
                "platform_io_account_id": "123",
                "platform_io_scope": "main",
            },
        ),
    )

    chat_manager.register_message(message)

    assert message.session_id == SessionUtils.calculate_session_id(
        "qq",
        user_id="42",
        group_id="1000",
        account_id="123",
        scope="main",
    )
    assert chat_manager.last_messages[message.session_id] is message
