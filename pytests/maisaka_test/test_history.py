"""history 单元测试。

覆盖 build_prefixed_message_sequence / drop_leading_orphan_tool_results /
drop_orphan_tool_results / drop_unanswered_tool_calls /
normalize_tool_result_order / normalize_tool_call_result_pairs 的
正常、边界与工具协议配对行为。
"""

from datetime import datetime

from src.common.data_models.message_component_data_model import (
    MessageSequence,
    ReplyComponent,
    TextComponent,
)
from src.llm_models.payload_content.tool_option import ToolCall
from src.maisaka.context.history import (
    build_prefixed_message_sequence,
    drop_leading_orphan_tool_results,
    drop_orphan_tool_results,
    drop_unanswered_tool_calls,
    normalize_tool_call_result_pairs,
    normalize_tool_result_order,
)
from src.maisaka.context.messages import (
    AssistantMessage,
    SessionBackedMessage,
    ToolResultMessage,
)

TS = datetime(2026, 8, 23, 14, 30, 5)


def _user_msg(text: str = "hi") -> SessionBackedMessage:
    return SessionBackedMessage(
        raw_message=MessageSequence([TextComponent(text)]),
        visible_text=text,
        timestamp=TS,
    )


def _assistant(content: str = "reply", call_id: str | None = None) -> AssistantMessage:
    tool_calls = [ToolCall(call_id=call_id, func_name="search", args={})] if call_id else []
    return AssistantMessage(content=content, timestamp=TS, tool_calls=tool_calls)


def _tool_result(call_id: str, content: str = "result") -> ToolResultMessage:
    return ToolResultMessage(content=content, timestamp=TS, tool_call_id=call_id, tool_name="search")


class TestBuildPrefixedMessageSequence:
    """build_prefixed_message_sequence 行为测试。"""

    def test_prefix_prepended_to_leading_text(self):
        seq = MessageSequence([TextComponent("内容")])
        result = build_prefixed_message_sequence(seq, "<prefix>")
        assert result.components[0].text == "<prefix>内容"

    def test_reply_components_dropped(self):
        seq = MessageSequence([ReplyComponent("r1"), TextComponent("内容")])
        result = build_prefixed_message_sequence(seq, "<prefix>")
        # ReplyComponent 被过滤
        assert len(result.components) == 1
        assert isinstance(result.components[0], TextComponent)

    def test_prefix_inserted_when_no_leading_text(self):
        from src.common.data_models.message_component_data_model import AtComponent

        seq = MessageSequence([AtComponent("123", "nick")])
        result = build_prefixed_message_sequence(seq, "<prefix>")
        # 首个非文本组件时插入前缀文本
        assert isinstance(result.components[0], TextComponent)
        assert result.components[0].text == "<prefix>"

    def test_empty_sequence(self):
        seq = MessageSequence([])
        result = build_prefixed_message_sequence(seq, "<prefix>")
        # 空序列插入前缀
        assert len(result.components) == 1
        assert result.components[0].text == "<prefix>"


class TestDropLeadingOrphanToolResults:
    """drop_leading_orphan_tool_results 行为测试。"""

    def test_empty_history(self):
        history, count = drop_leading_orphan_tool_results([])
        assert history == []
        assert count == 0

    def test_no_orphan_keeps_all(self):
        history = [_assistant(call_id="c1"), _tool_result("c1"), _user_msg()]
        result, count = drop_leading_orphan_tool_results(history)
        assert result == history
        assert count == 0

    def test_drops_leading_orphan_tool_results(self):
        # 前导 ToolResult 无对应 tool_call → 移除
        history = [_tool_result("orphan1"), _tool_result("orphan2"), _assistant(call_id="c1"), _tool_result("c1")]
        result, count = drop_leading_orphan_tool_results(history)
        assert count == 2
        assert result[0] is history[2]

    def test_stops_at_first_valid(self):
        # 遇到有对应 tool_call 的 ToolResult 即停止
        history = [_tool_result("c1"), _assistant(call_id="c1"), _tool_result("c1")]
        result, count = drop_leading_orphan_tool_results(history)
        # 第一个 _tool_result("c1") 有对应 c1 → 不移除
        assert count == 0
        assert result == history


class TestDropOrphanToolResults:
    """drop_orphan_tool_results 行为测试。"""

    def test_empty_history(self):
        result, count = drop_orphan_tool_results([])
        assert result == []
        assert count == 0

    def test_keeps_matched_pairs(self):
        history = [_assistant(call_id="c1"), _tool_result("c1")]
        result, count = drop_orphan_tool_results(history)
        assert count == 0
        assert len(result) == 2

    def test_removes_orphan_tool_result(self):
        history = [_assistant(call_id="c1"), _tool_result("c1"), _tool_result("orphan")]
        result, count = drop_orphan_tool_results(history)
        assert count == 1
        assert len(result) == 2

    def test_preserves_non_tool_messages(self):
        history = [_user_msg(), _tool_result("orphan"), _user_msg()]
        result, count = drop_orphan_tool_results(history)
        assert count == 1
        assert len(result) == 2


class TestDropUnansweredToolCalls:
    """drop_unanswered_tool_calls 行为测试。"""

    def test_empty_history(self):
        result, count = drop_unanswered_tool_calls([])
        assert result == []
        assert count == 0

    def test_keeps_answered_tool_calls(self):
        history = [_assistant(call_id="c1"), _tool_result("c1")]
        result, count = drop_unanswered_tool_calls(history)
        assert count == 0
        assert len(result) == 2

    def test_drops_unanswered_tool_call_keeps_content(self):
        # assistant 有 tool_call 但无对应 result → 移除 tool_call，保留 content
        history = [_assistant(content="回复内容", call_id="c1"), _user_msg()]
        result, count = drop_unanswered_tool_calls(history)
        assert count == 1
        # assistant 保留但 tool_calls 清空
        assistant = result[0]
        assert assistant.content == "回复内容"
        assert assistant.tool_calls == []

    def test_no_tool_results_drops_all_tool_calls(self):
        history = [_assistant(content="x", call_id="c1"), _user_msg()]
        result, count = drop_unanswered_tool_calls(history)
        assert count == 1
        assert result[0].tool_calls == []


class TestNormalizeToolResultOrder:
    """normalize_tool_result_order 行为测试。"""

    def test_empty_history(self):
        result, count = normalize_tool_result_order([])
        assert result == []
        assert count == 0

    def test_already_ordered_no_move(self):
        history = [_assistant(call_id="c1"), _tool_result("c1"), _user_msg()]
        result, count = normalize_tool_result_order(history)
        assert count == 0

    def test_moves_tool_result_after_assistant(self):
        # tool_result 被其他消息隔开 → 移到 assistant 后面
        history = [_assistant(call_id="c1"), _user_msg(), _tool_result("c1")]
        result, count = normalize_tool_result_order(history)
        assert count == 1
        # tool_result 应紧随 assistant
        assert isinstance(result[1], ToolResultMessage)
        assert isinstance(result[2], SessionBackedMessage)


class TestNormalizeToolCallResultPairs:
    """normalize_tool_call_result_pairs 行为测试。"""

    def test_empty_history(self):
        result, stats = normalize_tool_call_result_pairs([])
        assert result == []
        assert stats == {"orphan_tool_results": 0, "unanswered_tool_calls": 0, "moved_tool_results": 0}

    def test_clean_history_no_changes(self):
        history = [_user_msg(), _assistant(call_id="c1"), _tool_result("c1"), _user_msg()]
        result, stats = normalize_tool_call_result_pairs(history)
        assert stats["orphan_tool_results"] == 0
        assert stats["unanswered_tool_calls"] == 0
        assert stats["moved_tool_results"] == 0
        assert len(result) == 4

    def test_full_cleanup_pipeline(self):
        # 孤立 tool_result + 未回答 tool_call + 错位 tool_result
        history = [
            _tool_result("orphan"),  # 孤立
            _assistant(content="回复", call_id="c1"),  # c1 有 result 但错位
            _user_msg(),
            _tool_result("c1"),
            _assistant(content="无果", call_id="c2"),  # c2 无 result
        ]
        result, stats = normalize_tool_call_result_pairs(history)
        # 应有清理动作
        assert stats["orphan_tool_results"] >= 1
        assert stats["unanswered_tool_calls"] >= 1
        # 结果中不应含孤立的 orphan tool_result
        assert all(not (isinstance(m, ToolResultMessage) and m.tool_call_id == "orphan") for m in result)


class TestBuildSessionMessageVisibleText:
    """build_session_message_visible_text 行为测试。"""

    def test_basic_visible_text(self):
        from types import SimpleNamespace

        from src.maisaka.context.history import build_session_message_visible_text

        message = SimpleNamespace(
            raw_message=MessageSequence([TextComponent("你好")]),
            message_info=SimpleNamespace(
                user_info=SimpleNamespace(
                    user_cardname=None,
                    user_nickname="Alice",
                    user_id="123",
                )
            ),
            timestamp=TS,
            is_notify=False,
            message_id="m1",
        )
        result = build_session_message_visible_text(message)
        assert "Alice" in result
        assert "你好" in result

    def test_notify_message_omits_message_id(self):
        from types import SimpleNamespace

        from src.maisaka.context.history import build_session_message_visible_text

        message = SimpleNamespace(
            raw_message=MessageSequence([TextComponent("通知")]),
            message_info=SimpleNamespace(
                user_info=SimpleNamespace(
                    user_cardname=None,
                    user_nickname="System",
                    user_id="sys",
                )
            ),
            timestamp=TS,
            is_notify=True,
            message_id="m1",
        )
        result = build_session_message_visible_text(message)
        assert "System" in result

    def test_exclude_reply_components(self):
        from types import SimpleNamespace

        from src.maisaka.context.history import build_session_message_visible_text

        seq = MessageSequence([TextComponent("内容"), ReplyComponent("r1")])
        message = SimpleNamespace(
            raw_message=seq,
            message_info=SimpleNamespace(
                user_info=SimpleNamespace(
                    user_cardname=None,
                    user_nickname="Alice",
                    user_id="123",
                )
            ),
            timestamp=TS,
            is_notify=False,
            message_id="m1",
        )
        result = build_session_message_visible_text(message, include_reply_components=False)
        assert "Alice" in result
        assert "[引用消息]" not in result


class TestIsOrphanToolResultMediaMessage:
    """_is_orphan_tool_result_media_message 行为测试。"""

    def test_non_session_backed_returns_false(self):
        from src.maisaka.context.history import _is_orphan_tool_result_media_message

        msg = _assistant()
        assert _is_orphan_tool_result_media_message(msg, set()) is False

    def test_wrong_source_kind_returns_false(self):
        from src.maisaka.context.history import _is_orphan_tool_result_media_message

        msg = SessionBackedMessage(
            raw_message=MessageSequence([TextComponent("x")]),
            visible_text="x",
            timestamp=TS,
            source_kind="user",
            message_id="tool_result:c1:media",
        )
        assert _is_orphan_tool_result_media_message(msg, set()) is False

    def test_orphan_media_returns_true(self):
        from src.maisaka.context.history import (
            TOOL_RESULT_MEDIA_SOURCE_KIND,
            _is_orphan_tool_result_media_message,
        )

        msg = SessionBackedMessage(
            raw_message=MessageSequence([TextComponent("x")]),
            visible_text="x",
            timestamp=TS,
            source_kind=TOOL_RESULT_MEDIA_SOURCE_KIND,
            message_id="tool_result:c1:media",
        )
        # c1 不在 available → 孤立
        assert _is_orphan_tool_result_media_message(msg, set()) is True

    def test_owned_media_returns_false(self):
        from src.maisaka.context.history import (
            TOOL_RESULT_MEDIA_SOURCE_KIND,
            _is_orphan_tool_result_media_message,
        )

        msg = SessionBackedMessage(
            raw_message=MessageSequence([TextComponent("x")]),
            visible_text="x",
            timestamp=TS,
            source_kind=TOOL_RESULT_MEDIA_SOURCE_KIND,
            message_id="tool_result:c1:media",
        )
        # c1 在 available → 非孤立
        assert _is_orphan_tool_result_media_message(msg, {"c1"}) is False

    def test_non_tool_result_message_id_returns_false(self):
        from src.maisaka.context.history import (
            TOOL_RESULT_MEDIA_SOURCE_KIND,
            _is_orphan_tool_result_media_message,
        )

        msg = SessionBackedMessage(
            raw_message=MessageSequence([TextComponent("x")]),
            visible_text="x",
            timestamp=TS,
            source_kind=TOOL_RESULT_MEDIA_SOURCE_KIND,
            message_id="regular_msg",
        )
        assert _is_orphan_tool_result_media_message(msg, set()) is False


class TestParseFoldedToolHistoryCallIds:
    """_parse_folded_tool_history_call_ids 行为测试。"""

    def test_extract_call_ids(self):
        from src.maisaka.context.history import _parse_folded_tool_history_call_ids

        content = "- tool_call_id: c1\n  tool_name: search\n- tool_call_id: c2"
        result = _parse_folded_tool_history_call_ids(content)
        assert result == {"c1", "c2"}

    def test_no_matching_lines_returns_empty(self):
        from src.maisaka.context.history import _parse_folded_tool_history_call_ids

        assert _parse_folded_tool_history_call_ids("普通文本\n无 tool_call") == set()

    def test_empty_content(self):
        from src.maisaka.context.history import _parse_folded_tool_history_call_ids

        assert _parse_folded_tool_history_call_ids("") == set()


class TestCollectFoldedToolHistoryCallIds:
    """_collect_folded_tool_history_call_ids 行为测试。"""

    def test_collects_from_optimized_history(self):
        from src.maisaka.context.history import (
            OPTIMIZED_TOOL_HISTORY_SOURCE_KIND,
            _collect_folded_tool_history_call_ids,
        )

        msg = SessionBackedMessage(
            raw_message=MessageSequence([TextComponent("- tool_call_id: c1")]),
            visible_text="- tool_call_id: c1",
            timestamp=TS,
            source_kind=OPTIMIZED_TOOL_HISTORY_SOURCE_KIND,
        )
        result = _collect_folded_tool_history_call_ids([msg])
        assert "c1" in result

    def test_ignores_non_optimized_messages(self):
        from src.maisaka.context.history import _collect_folded_tool_history_call_ids

        msg = _user_msg()
        assert _collect_folded_tool_history_call_ids([msg]) == set()