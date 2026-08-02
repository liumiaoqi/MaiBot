from types import SimpleNamespace

from src.common.utils import utils_config
from src.common.utils.utils_config import ChatConfigUtils, ExpressionConfigUtils, JargonConfigUtils
from src.common.utils.utils_session import SessionUtils
from src.config.config import global_config
from src.chat.message_receive.chat_manager import ChatManager

import pytest


@pytest.fixture(autouse=True)
def _init_config():
    """config_manager 显式初始化 + utils_config 端口注入（测试环境不经过 main()）。"""
    from src.config.config import initialize_config
    from src.core.adapters.app_config_port import GlobalConfigAppConfigPort
    from src.core.adapters.chat_config_port import GlobalConfigChatConfigPort
    from src.common.utils.utils_config import set_utils_config_ports

    initialize_config()
    set_utils_config_ports(
        app_config_port=GlobalConfigAppConfigPort(),
        chat_config_port=GlobalConfigChatConfigPort(),
    )
    yield


# 全局单例已移除（SSD-3），测试用裸实例（仅 monkeypatch 方法，不触发 __init__）
chat_manager = ChatManager.__new__(ChatManager)


def test_get_chat_prompt_for_chat_merges_multiple_matching_prompts(monkeypatch):
    session_id = SessionUtils.calculate_session_id("qq", group_id="1036092828")
    monkeypatch.setattr(
        global_config.chat.reply_style,
        "chat_prompts",
        [
            {"platform": "qq", "item_id": "1036092828", "rule_type": "group", "prompt": "你也是群管理员，可以适当进行管理"},
            {"platform": "qq", "item_id": "1036092828", "rule_type": "group", "prompt": "这个群是技术实验群，请你专心讨论技术"},
            {"platform": "qq", "item_id": "other", "rule_type": "group", "prompt": "不应该生效"},
        ],
    )
    monkeypatch.setattr("src.core.session_port_registry.get_session_info", lambda _session_id: None)
    monkeypatch.setattr(
        ChatConfigUtils,
        "resolve_existing_session_ids",
        lambda _p, item_id, _r: {session_id} if item_id == "1036092828" else set(),
    )

    result = ChatConfigUtils.get_chat_prompt_for_chat(session_id, True)

    assert result == "你也是群管理员，可以适当进行管理\n这个群是技术实验群，请你专心讨论技术"


def test_get_chat_prompt_for_chat_matches_routed_session_by_chat_stream(monkeypatch):
    session_id = SessionUtils.calculate_session_id("qq", group_id="1036092828", account_id="bot-a")
    monkeypatch.setattr(
        global_config.chat.reply_style,
        "chat_prompts",
        [
            {"platform": "qq", "item_id": "1036092828", "rule_type": "group", "prompt": "路由会话也应该生效"},
        ],
    )
    monkeypatch.setattr(
        "src.core.session_port_registry.get_session_info",
        lambda _session_id: SimpleNamespace(platform="qq", group_id="1036092828", user_id=None),
    )

    result = ChatConfigUtils.get_chat_prompt_for_chat(session_id, True)

    assert result == "路由会话也应该生效"


def test_expression_learning_list_matches_routed_session_by_chat_stream(monkeypatch):
    session_id = SessionUtils.calculate_session_id("qq", group_id="1036092828", account_id="bot-a")
    monkeypatch.setattr(
        global_config.expression,
        "learning_list",
        [
            {
                "platform": "qq",
                "item_id": "1036092828",
                "type": "group",
                "use": False,
                "learn": False,
            }
        ],
    )
    monkeypatch.setattr(
        "src.core.session_port_registry.get_session_info",
        lambda _session_id: SimpleNamespace(platform="qq", group_id="1036092828", user_id=None),
    )

    assert ExpressionConfigUtils.get_expression_config_for_chat(session_id) == (False, False)


def test_expression_learning_list_wildcard_takes_priority_over_exact(monkeypatch):
    session_id = SessionUtils.calculate_session_id("qq", group_id="1036092828", account_id="bot-a")
    monkeypatch.setattr(
        global_config.expression,
        "learning_list",
        [
            {
                "platform": "qq",
                "item_id": "1036092828",
                "type": "group",
                "use": False,
                "learn": False,
            },
            {
                "platform": "qq",
                "item_id": "*",
                "type": "group",
                "use": True,
                "learn": True,
            },
            {
                "platform": "",
                "item_id": "",
                "type": "group",
                "use": False,
                "learn": True,
            },
        ],
    )
    monkeypatch.setattr(
        "src.core.session_port_registry.get_session_info",
        lambda _session_id: SimpleNamespace(platform="qq", group_id="1036092828", user_id=None),
    )

    assert ExpressionConfigUtils.get_expression_config_for_chat(session_id) == (True, True)


def test_expression_learning_list_exact_takes_priority_when_no_wildcard_matches(monkeypatch):
    session_id = SessionUtils.calculate_session_id("qq", group_id="1036092828", account_id="bot-a")
    monkeypatch.setattr(
        global_config.expression,
        "learning_list",
        [
            {
                "platform": "telegram",
                "item_id": "*",
                "type": "group",
                "use": True,
                "learn": True,
            },
            {
                "platform": "qq",
                "item_id": "1036092828",
                "type": "group",
                "use": False,
                "learn": False,
            },
            {
                "platform": "",
                "item_id": "",
                "type": "group",
                "use": True,
                "learn": True,
            },
        ],
    )
    monkeypatch.setattr(
        "src.core.session_port_registry.get_session_info",
        lambda _session_id: SimpleNamespace(platform="qq", group_id="1036092828", user_id=None),
    )

    assert ExpressionConfigUtils.get_expression_config_for_chat(session_id) == (False, False)








def test_jargon_learning_list_matches_routed_session_by_chat_stream(monkeypatch):
    session_id = SessionUtils.calculate_session_id("qq", group_id="1036092828", account_id="bot-a")
    monkeypatch.setattr(
        global_config.jargon,
        "learning_list",
        [
            {
                "platform": "qq",
                "item_id": "1036092828",
                "type": "group",
                "learn": False,
            }
        ],
    )
    monkeypatch.setattr(
        "src.core.session_port_registry.get_session_info",
        lambda _session_id: SimpleNamespace(platform="qq", group_id="1036092828", user_id=None, is_group_session=True),
    )

    assert JargonConfigUtils.get_jargon_config_for_chat(session_id) == (True, False)


def test_jargon_learning_list_wildcard_takes_priority_over_exact(monkeypatch):
    session_id = SessionUtils.calculate_session_id("qq", group_id="1036092828", account_id="bot-a")
    monkeypatch.setattr(
        global_config.jargon,
        "learning_list",
        [
            {
                "platform": "qq",
                "item_id": "1036092828",
                "type": "group",
                "learn": False,
            },
            {
                "platform": "qq",
                "item_id": "*",
                "type": "group",
                "learn": True,
            },
        ],
    )
    monkeypatch.setattr(
        "src.core.session_port_registry.get_session_info",
        lambda _session_id: SimpleNamespace(platform="qq", group_id="1036092828", user_id=None, is_group_session=True),
    )

    assert JargonConfigUtils.get_jargon_config_for_chat(session_id) == (True, True)


def test_jargon_learning_list_supports_platform_wildcard(monkeypatch):
    session_id = SessionUtils.calculate_session_id("qq", group_id="1036092828", account_id="bot-a")
    monkeypatch.setattr(
        global_config.jargon,
        "learning_list",
        [
            {
                "platform": "*",
                "item_id": "1036092828",
                "type": "group",
                "learn": False,
            }
        ],
    )
    monkeypatch.setattr(
        "src.core.session_port_registry.get_session_info",
        lambda _session_id: SimpleNamespace(platform="qq", group_id="1036092828", user_id=None, is_group_session=True),
    )

    assert JargonConfigUtils.get_jargon_config_for_chat(session_id) == (True, False)


def test_jargon_group_scope_supports_item_id_wildcard(monkeypatch):
    session_id = "session-a"
    other_session_id = "session-b"
    private_session_id = "session-c"
    monkeypatch.setattr(
        global_config.jargon,
        "jargon_groups",
        [
            {
                "targets": [
                    {"platform": "qq", "item_id": "*", "rule_type": "group"},
                ]
            }
        ],
    )
    sessions = {
        session_id: SimpleNamespace(
            session_id=session_id,
            platform="qq",
            group_id="10001",
            user_id=None,
            is_group_session=True,
        ),
        other_session_id: SimpleNamespace(
            session_id=other_session_id,
            platform="qq",
            group_id="10002",
            user_id=None,
            is_group_session=True,
        ),
        private_session_id: SimpleNamespace(
            session_id=private_session_id,
            platform="qq",
            group_id=None,
            user_id="10003",
            is_group_session=False,
        ),
    }
    monkeypatch.setattr("src.core.session_port_registry.get_session_info", lambda target_session_id: sessions.get(target_session_id))
    monkeypatch.setattr(
        "src.core.session_port_registry.get_session_query_port",
        lambda: type("Q", (), {"list_sessions": lambda self: list(sessions.values())})(),
    )

    related_session_ids, has_global_share = JargonConfigUtils.resolve_jargon_group_scope(session_id)

    assert related_session_ids >= {session_id, other_session_id}
    assert private_session_id not in related_session_ids
    assert has_global_share is False


def test_talk_value_rules_match_routed_session_by_chat_stream(monkeypatch):
    session_id = SessionUtils.calculate_session_id("qq", group_id="1036092828", account_id="bot-a")
    monkeypatch.setattr(global_config.chat.reply_timing, "talk_value", 0.1)
    monkeypatch.setattr(global_config.chat.reply_timing, "enable_talk_value_rules", True)
    monkeypatch.setattr(
        global_config.chat.reply_timing,
        "talk_value_rules",
        [
            {"platform": "qq", "item_id": "1036092828", "rule_type": "group", "time": "00:00-23:59", "value": 0.7}
        ],
    )
    monkeypatch.setattr(
        "src.core.session_port_registry.get_session_info",
        lambda _session_id: SimpleNamespace(platform="qq", group_id="1036092828", user_id=None),
    )

    assert ChatConfigUtils.get_talk_value(session_id, True) == 0.7


def test_talk_value_rule_empty_time_is_fallback_and_time_range_overrides(monkeypatch):
    current_time = SimpleNamespace(tm_hour=10, tm_min=30)
    monkeypatch.setattr(utils_config.time, "localtime", lambda: current_time)
    monkeypatch.setattr(global_config.chat.reply_timing, "talk_value", 0.1)
    monkeypatch.setattr(global_config.chat.reply_timing, "enable_talk_value_rules", True)
    monkeypatch.setattr(
        global_config.chat.reply_timing,
        "talk_value_rules",
        [
            {"platform": "", "item_id": "", "rule_type": "group", "time": "", "value": 0.2},
            {"platform": "", "item_id": "", "rule_type": "group", "time": "09:00-11:00", "value": 0.5},
        ],
    )

    assert ChatConfigUtils.get_talk_value(None, True) == 0.5

    current_time.tm_hour = 12
    assert ChatConfigUtils.get_talk_value(None, True) == 0.2


def test_talk_value_rule_star_time_overrides_fallback_and_time_range(monkeypatch):
    monkeypatch.setattr(utils_config.time, "localtime", lambda: SimpleNamespace(tm_hour=10, tm_min=30))
    monkeypatch.setattr(global_config.chat.reply_timing, "talk_value", 0.1)
    monkeypatch.setattr(global_config.chat.reply_timing, "enable_talk_value_rules", True)
    monkeypatch.setattr(
        global_config.chat.reply_timing,
        "talk_value_rules",
        [
            {"platform": "", "item_id": "", "rule_type": "group", "time": "", "value": 0.2},
            {"platform": "", "item_id": "", "rule_type": "group", "time": "09:00-11:00", "value": 0.5},
            {"platform": "", "item_id": "", "rule_type": "group", "time": "*", "value": 0.8},
        ],
    )

    assert ChatConfigUtils.get_talk_value(None, True) == 0.8


def test_talk_value_rule_platform_only_is_platform_default(monkeypatch):
    session_id = "session-a"
    monkeypatch.setattr(utils_config.time, "localtime", lambda: SimpleNamespace(tm_hour=10, tm_min=30))
    monkeypatch.setattr(global_config.chat.reply_timing, "talk_value", 0.1)
    monkeypatch.setattr(global_config.chat.reply_timing, "enable_talk_value_rules", True)
    monkeypatch.setattr(
        global_config.chat.reply_timing,
        "talk_value_rules",
        [
            {"platform": "", "item_id": "", "rule_type": "group", "time": "", "value": 0.2},
            {"platform": "qq", "item_id": "", "rule_type": "group", "time": "", "value": 0.4},
        ],
    )
    monkeypatch.setattr(
        "src.core.session_port_registry.get_session_info",
        lambda _session_id: SimpleNamespace(platform="qq", group_id="10001", user_id=None),
    )

    assert ChatConfigUtils.get_talk_value(session_id, True) == 0.4


def test_talk_value_rule_item_only_is_item_default(monkeypatch):
    session_id = "session-a"
    monkeypatch.setattr(utils_config.time, "localtime", lambda: SimpleNamespace(tm_hour=10, tm_min=30))
    monkeypatch.setattr(global_config.chat.reply_timing, "talk_value", 0.1)
    monkeypatch.setattr(global_config.chat.reply_timing, "enable_talk_value_rules", True)
    monkeypatch.setattr(
        global_config.chat.reply_timing,
        "talk_value_rules",
        [
            {"platform": "", "item_id": "", "rule_type": "group", "time": "", "value": 0.2},
            {"platform": "", "item_id": "10001", "rule_type": "group", "time": "", "value": 0.4},
        ],
    )
    monkeypatch.setattr(
        "src.core.session_port_registry.get_session_info",
        lambda _session_id: SimpleNamespace(platform="telegram", group_id="10001", user_id=None),
    )

    assert ChatConfigUtils.get_talk_value(session_id, True) == 0.4


def test_talk_value_rule_exact_target_overrides_partial_default(monkeypatch):
    session_id = "session-a"
    monkeypatch.setattr(utils_config.time, "localtime", lambda: SimpleNamespace(tm_hour=10, tm_min=30))
    monkeypatch.setattr(global_config.chat.reply_timing, "talk_value", 0.1)
    monkeypatch.setattr(global_config.chat.reply_timing, "enable_talk_value_rules", True)
    monkeypatch.setattr(
        global_config.chat.reply_timing,
        "talk_value_rules",
        [
            {"platform": "qq", "item_id": "", "rule_type": "group", "time": "*", "value": 0.4},
            {"platform": "qq", "item_id": "10001", "rule_type": "group", "time": "", "value": 0.7},
        ],
    )
    monkeypatch.setattr(
        "src.core.session_port_registry.get_session_info",
        lambda _session_id: SimpleNamespace(platform="qq", group_id="10001", user_id=None),
    )

    assert ChatConfigUtils.get_talk_value(session_id, True) == 0.7


def test_talk_value_rule_wildcard_target_overrides_partial_default(monkeypatch):
    session_id = "session-a"
    monkeypatch.setattr(utils_config.time, "localtime", lambda: SimpleNamespace(tm_hour=10, tm_min=30))
    monkeypatch.setattr(global_config.chat.reply_timing, "talk_value", 0.1)
    monkeypatch.setattr(global_config.chat.reply_timing, "enable_talk_value_rules", True)
    monkeypatch.setattr(
        global_config.chat.reply_timing,
        "talk_value_rules",
        [
            {"platform": "qq", "item_id": "", "rule_type": "group", "time": "*", "value": 0.4},
            {"platform": "qq", "item_id": "*", "rule_type": "group", "time": "", "value": 0.6},
        ],
    )
    monkeypatch.setattr(
        "src.core.session_port_registry.get_session_info",
        lambda _session_id: SimpleNamespace(platform="qq", group_id="10001", user_id=None),
    )

    assert ChatConfigUtils.get_talk_value(session_id, True) == 0.6
