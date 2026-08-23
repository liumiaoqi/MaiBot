from datetime import datetime

from src.common.data_models.message_component_data_model import (
    MessageSequence,
    ReplyComponent,
    TextComponent,
)
from src.maisaka.context.planner_messages import (
    build_planner_prefix,
    build_session_backed_text_message,
    extract_quote_ids_from_message_sequence,
)


def test_build_planner_prefix_marks_self_message_when_enabled() -> None:
    prefix = build_planner_prefix(
        timestamp=datetime(2026, 6, 13, 1, 9, 30),
        user_name="呢猫",
        message_id="1316095995",
        is_self_message=True,
    )

    assert 'is_self_message="true"' in prefix


def test_build_planner_prefix_omits_self_message_mark_by_default() -> None:
    prefix = build_planner_prefix(
        timestamp=datetime(2026, 6, 13, 1, 9, 30),
        user_name="Luft",
        message_id="-1470070102",
    )

    assert 'is_self_message="true"' not in prefix


class TestBuildPlannerPrefix:
    """build_planner_prefix 完整行为测试。"""

    def test_basic_prefix_structure(self):
        prefix = build_planner_prefix(
            timestamp=datetime(2026, 8, 23, 14, 30, 5),
            user_name="Alice",
            message_id="m1",
        )
        assert prefix.startswith("<message ")
        assert prefix.endswith(">\n")
        assert 'msg_id="m1"' in prefix
        assert 'time="08-23 14:30:05"' in prefix
        assert 'user="Alice"' in prefix

    def test_weekday_rendered(self):
        # 2026-08-23 是周日
        prefix = build_planner_prefix(
            timestamp=datetime(2026, 8, 23, 14, 30, 5),
            user_name="Alice",
            message_id="m1",
        )
        assert 'day="周日"' in prefix

    def test_group_card_included_when_non_empty(self):
        prefix = build_planner_prefix(
            timestamp=datetime(2026, 8, 23, 14, 30, 5),
            user_name="Alice",
            message_id="m1",
            group_card="群名片",
        )
        assert 'group_card="群名片"' in prefix

    def test_group_card_omitted_when_empty(self):
        prefix = build_planner_prefix(
            timestamp=datetime(2026, 8, 23, 14, 30, 5),
            user_name="Alice",
            message_id="m1",
            group_card="   ",
        )
        assert "group_card=" not in prefix

    def test_chat_id_included_when_enabled(self):
        prefix = build_planner_prefix(
            timestamp=datetime(2026, 8, 23, 14, 30, 5),
            user_name="Alice",
            message_id="m1",
            chat_id="chat123",
            include_chat_id=True,
        )
        assert 'chat_id="chat123"' in prefix

    def test_chat_id_omitted_by_default(self):
        prefix = build_planner_prefix(
            timestamp=datetime(2026, 8, 23, 14, 30, 5),
            user_name="Alice",
            message_id="m1",
            chat_id="chat123",
        )
        assert "chat_id=" not in prefix

    def test_message_id_omitted_when_disabled(self):
        prefix = build_planner_prefix(
            timestamp=datetime(2026, 8, 23, 14, 30, 5),
            user_name="Alice",
            message_id="m1",
            include_message_id=False,
        )
        assert "msg_id=" not in prefix

    def test_quote_ids_included(self):
        prefix = build_planner_prefix(
            timestamp=datetime(2026, 8, 23, 14, 30, 5),
            user_name="Alice",
            message_id="m1",
            quote_ids=["q1", "q2"],
        )
        assert 'quote="q1,q2"' in prefix

    def test_quote_ids_deduplicated(self):
        prefix = build_planner_prefix(
            timestamp=datetime(2026, 8, 23, 14, 30, 5),
            user_name="Alice",
            message_id="m1",
            quote_ids=["q1", "q1", "q2"],
        )
        assert 'quote="q1,q2"' in prefix

    def test_html_escaped_user_name(self):
        prefix = build_planner_prefix(
            timestamp=datetime(2026, 8, 23, 14, 30, 5),
            user_name='<script>alert("x")</script>',
            message_id="m1",
        )
        assert "<script>" not in prefix
        assert "&lt;script&gt;" in prefix


class TestExtractQuoteIdsFromMessageSequence:
    """extract_quote_ids_from_message_sequence 行为测试。"""

    def test_extract_single_reply(self):
        seq = MessageSequence([ReplyComponent("msg1")])
        assert extract_quote_ids_from_message_sequence(seq) == ["msg1"]

    def test_extract_multiple_replies(self):
        seq = MessageSequence([ReplyComponent("msg1"), ReplyComponent("msg2")])
        assert extract_quote_ids_from_message_sequence(seq) == ["msg1", "msg2"]

    def test_deduplicate_quote_ids(self):
        seq = MessageSequence([ReplyComponent("msg1"), ReplyComponent("msg1")])
        assert extract_quote_ids_from_message_sequence(seq) == ["msg1"]

    def test_skip_empty_quote_id(self):
        seq = MessageSequence([ReplyComponent("msg1"), ReplyComponent("  ")])
        assert extract_quote_ids_from_message_sequence(seq) == ["msg1"]

    def test_no_reply_components_returns_empty(self):
        seq = MessageSequence([TextComponent("hello")])
        assert extract_quote_ids_from_message_sequence(seq) == []

    def test_empty_sequence(self):
        seq = MessageSequence([])
        assert extract_quote_ids_from_message_sequence(seq) == []


class TestBuildSessionBackedTextMessage:
    """build_session_backed_text_message 行为测试。"""

    def test_basic_message_construction(self):
        msg = build_session_backed_text_message(
            speaker_name="Alice",
            text="你好",
            timestamp=datetime(2026, 8, 23, 14, 30, 5),
            source_kind="user",
            message_id="m1",
        )
        assert msg.source_kind == "user"
        assert msg.message_id == "m1"
        assert msg.timestamp == datetime(2026, 8, 23, 14, 30, 5)
        assert "你好" in msg.visible_text
        assert "Alice" in msg.visible_text

    def test_raw_message_contains_planner_prefix(self):
        msg = build_session_backed_text_message(
            speaker_name="Alice",
            text="内容",
            timestamp=datetime(2026, 8, 23, 14, 30, 5),
            source_kind="user",
            message_id="m1",
        )
        # raw_message 第一个文本组件应含 <message 前缀
        first_component = msg.raw_message.components[0]
        assert "<message " in first_component.text
        assert "内容" in first_component.text

    def test_self_message_flag_propagated(self):
        msg = build_session_backed_text_message(
            speaker_name="Bot",
            text="自言自语",
            timestamp=datetime(2026, 8, 23, 14, 30, 5),
            source_kind="assistant",
            message_id="m1",
            is_self_message=True,
        )
        first_component = msg.raw_message.components[0]
        assert 'is_self_message="true"' in first_component.text

