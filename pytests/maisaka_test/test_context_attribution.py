"""上下文归属投影测试（批次 5）。"""

from datetime import datetime

from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
from src.llm_models.payload_content.message import RoleType
from src.maisaka.chat_loop_service import _common_prefix_length
from src.maisaka.context.messages import SessionBackedMessage, build_llm_message_from_context
from src.maisaka.memory.mid_term import _select_summary_source_messages


def _backed(text: str, *, speaker_type: str, speaker_agent_id: str) -> SessionBackedMessage:
    return SessionBackedMessage(
        raw_message=MessageSequence([TextComponent(f'<message user="{speaker_agent_id or "user"}">\n{text}')]),
        visible_text=text,
        timestamp=datetime.now(),
        speaker_type=speaker_type,
        speaker_agent_id=speaker_agent_id,
    )


def test_self_message_becomes_assistant():
    message = _backed("我说的话", speaker_type="agent", speaker_agent_id="silver_wolf")

    result = build_llm_message_from_context(message, viewer_agent_id="silver_wolf")

    assert result is not None
    assert result.role is RoleType.Assistant


def test_other_agent_stays_user():
    message = _backed("别人说的话", speaker_type="agent", speaker_agent_id="bronya")

    result = build_llm_message_from_context(message, viewer_agent_id="silver_wolf")

    assert result is not None
    assert result.role is RoleType.User


def test_human_stays_user_even_if_name_matches():
    message = _backed("真人的话", speaker_type="user", speaker_agent_id="silver_wolf")

    result = build_llm_message_from_context(message, viewer_agent_id="silver_wolf")

    assert result is not None
    assert result.role is RoleType.User


def test_empty_viewer_never_projects_assistant():
    message = _backed("我说的话", speaker_type="agent", speaker_agent_id="silver_wolf")

    result = build_llm_message_from_context(message, viewer_agent_id="")

    assert result is not None
    assert result.role is RoleType.User


def test_disabled_never_projects_assistant():
    message = _backed("我说的话", speaker_type="agent", speaker_agent_id="silver_wolf")

    result = build_llm_message_from_context(
        message,
        viewer_agent_id="silver_wolf",
        attribution_enabled=False,
    )

    assert result is not None
    assert result.role is RoleType.User


def test_legacy_unknown_stays_user():
    message = _backed("存量消息", speaker_type="", speaker_agent_id="")

    result = build_llm_message_from_context(message, viewer_agent_id="silver_wolf")

    assert result is not None
    assert result.role is RoleType.User


def test_mid_term_source_keeps_session_backed_messages():
    messages = [
        _backed("普通消息", speaker_type="user", speaker_agent_id=""),
        _backed("角色消息", speaker_type="agent", speaker_agent_id="silver_wolf"),
    ]

    selected = _select_summary_source_messages(messages)

    assert len(selected) == 2


def test_common_prefix_length():
    previous = ("a", "b", "c")
    current = ("a", "b", "d", "e")

    assert _common_prefix_length(previous, current) == 2
    assert _common_prefix_length(previous, previous + ("new",)) == 3