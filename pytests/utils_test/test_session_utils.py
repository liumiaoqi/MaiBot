from types import SimpleNamespace

from src.chat.message_receive.message_registry import MessageRegistry
from src.chat.message_receive.session_store import SessionStore
from src.common.utils.utils_session import SessionUtils


def test_calculate_session_id_distinguishes_account_and_scope() -> None:
    base_session_id = SessionUtils.calculate_session_id("qq", user_id="42")
    same_base_session_id = SessionUtils.calculate_session_id("qq", user_id="42")
    account_scoped_session_id = SessionUtils.calculate_session_id("qq", user_id="42", account_id="123")
    route_scoped_session_id = SessionUtils.calculate_session_id("qq", user_id="42", account_id="123", scope="main")

    assert base_session_id == same_base_session_id
    assert account_scoped_session_id != base_session_id
    assert route_scoped_session_id != account_scoped_session_id


def test_register_message_uses_route_metadata() -> None:
    """ChatManager 已删除（C 类零创建点），直接测试 MessageRegistry.register 的路由元数据提取。"""
    session_store = SessionStore()
    message_registry = MessageRegistry(session_store)
    session_store.set_message_registry(message_registry)

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

    message_registry.register(message)

    assert message.session_id == SessionUtils.calculate_session_id(
        "qq",
        user_id="42",
        group_id="1000",
        account_id="123",
        scope="main",
    )
    assert message_registry.last_messages[message.session_id] is message
