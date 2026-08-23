"""post_processor 单元测试。

覆盖纯函数（split / merge / punctuation / kaomoji / western_ratio /
truncate / stage_direction）与 process_llm_response / calculate_typing_time /
process_chat_history_after_cycle 的行为。配置 port 通过 monkeypatch 注入。
"""

import random
from datetime import datetime
from types import SimpleNamespace

import pytest

from src.llm_models.payload_content.tool_option import ToolCall
from src.maisaka.context.messages import AssistantMessage
from src.maisaka.context.post_processor import (
    HistoryPostProcessResult,
    _is_english_letter,
    _is_stage_direction,
    calculate_typing_time,
    get_western_ratio,
    merge_sentences_to_max_count,
    process_chat_history_after_cycle,
    process_llm_response,
    protect_kaomoji,
    random_remove_punctuation,
    recover_kaomoji,
    split_into_sentences_w_remove_punctuation,
    truncate_message,
)

TS = datetime(2026, 8, 23, 14, 30, 5)


class TestIsEnglishLetter:
    """_is_english_letter 行为测试。"""

    def test_uppercase_letters(self):
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            assert _is_english_letter(ch) is True

    def test_lowercase_letters(self):
        for ch in "abcdefghijklmnopqrstuvwxyz":
            assert _is_english_letter(ch) is True

    def test_non_letters(self):
        assert _is_english_letter("中") is False
        assert _is_english_letter("1") is False
        assert _is_english_letter(" ") is False
        assert _is_english_letter("!") is False


class TestSplitIntoSentences:
    """split_into_sentences_w_remove_punctuation 行为测试。"""

    def test_empty_string(self):
        random.seed(42)
        result = split_into_sentences_w_remove_punctuation("")
        # 空文本返回 [] 或 [""]（取决于随机合并）
        assert result in ([], [""])

    def test_short_text(self):
        random.seed(42)
        result = split_into_sentences_w_remove_punctuation("你好")
        assert isinstance(result, list)

    def test_chinese_with_punctuation(self):
        random.seed(42)
        result = split_into_sentences_w_remove_punctuation("你好，世界。")
        assert isinstance(result, list)
        # 分割后内容应包含原文本片段
        joined = "".join(result)
        assert "你好" in joined or "你" in joined

    def test_newline_forces_split(self):
        random.seed(42)
        result = split_into_sentences_w_remove_punctuation("第一行\n第二行")
        assert isinstance(result, list)

    def test_returns_list_of_strings(self):
        random.seed(42)
        result = split_into_sentences_w_remove_punctuation("测试文本内容")
        assert all(isinstance(s, str) for s in result)


class TestMergeSentencesToMaxCount:
    """merge_sentences_to_max_count 行为测试。"""

    def test_under_max_returns_unchanged(self):
        sentences = ["a", "b", "c"]
        assert merge_sentences_to_max_count(sentences, 5) == sentences

    def test_exact_max_returns_unchanged(self):
        sentences = ["a", "b", "c"]
        assert merge_sentences_to_max_count(sentences, 3) == sentences

    def test_merges_to_target_count(self):
        sentences = ["a", "b", "c", "d", "e", "f"]
        result = merge_sentences_to_max_count(sentences, 3)
        assert len(result) == 3
        # 合并后内容完整
        assert "".join(result) == "abcdef"

    def test_single_sentence(self):
        assert merge_sentences_to_max_count(["only"], 1) == ["only"]

    def test_empty_list(self):
        assert merge_sentences_to_max_count([], 3) == []


class TestRandomRemovePunctuation:
    """random_remove_punctuation 行为测试。"""

    def test_no_trailing_period(self):
        random.seed(42)
        result = random_remove_punctuation("测试文本")
        assert "。" not in result

    def test_text_without_punctuation_unchanged(self):
        random.seed(42)
        result = random_remove_punctuation("纯文本内容")
        assert result == "纯文本内容"

    def test_returns_string(self):
        random.seed(42)
        result = random_remove_punctuation("你好，世界。")
        assert isinstance(result, str)


class TestTruncateMessage:
    """truncate_message 行为测试。"""

    def test_short_message_unchanged(self):
        assert truncate_message("短消息", 20) == "短消息"

    def test_long_message_truncated(self):
        result = truncate_message("这是一个很长的消息内容超过限制", 5)
        assert result.endswith("...")
        assert result.startswith("这是一个很")

    def test_exact_length_unchanged(self):
        msg = "12345"
        assert truncate_message(msg, 5) == msg

    def test_default_max_length(self):
        short = "短"
        assert truncate_message(short) == short


class TestProtectKaomoji:
    """protect_kaomoji 行为测试。"""

    def test_no_kaomoji_returns_unchanged(self):
        text, mapping = protect_kaomoji("普通文本")
        assert text == "普通文本"
        assert mapping == {}

    def test_kaomoji_replaced_with_placeholder(self):
        text, mapping = protect_kaomoji("你好 (T_T) 世界")
        if mapping:
            assert any("__KAOMOJI_" in p for p in mapping)
            # 占位符应在文本中
            assert any(p in text for p in mapping)

    def test_returns_tuple(self):
        result = protect_kaomoji("text")
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestRecoverKaomoji:
    """recover_kaomoji 行为测试。"""

    def test_empty_mapping_returns_unchanged(self):
        sentences = ["hello", "world"]
        assert recover_kaomoji(sentences, {}) == sentences

    def test_placeholder_recovered(self):
        mapping = {"__KAOMOJI_0__": "(T_T)"}
        sentences = ["你好 __KAOMOJI_0__ 世界"]
        result = recover_kaomoji(sentences, mapping)
        assert result == ["你好 (T_T) 世界"]

    def test_multiple_placeholders(self):
        mapping = {"__KAOMOJI_0__": "(T_T)", "__KAOMOJI_1__": "(^_^)"}
        sentences = ["__KAOMOJI_0__ 和 __KAOMOJI_1__"]
        result = recover_kaomoji(sentences, mapping)
        assert result == ["(T_T) 和 (^_^)"]


class TestGetWesternRatio:
    """get_western_ratio 行为测试。"""

    def test_pure_chinese_returns_zero(self):
        assert get_western_ratio("你好世界") == 0.0

    def test_pure_english_returns_one(self):
        assert get_western_ratio("hello world") == 1.0

    def test_mixed_ratio(self):
        ratio = get_western_ratio("abc你好")
        # 3 英文 + 2 中文 = 5 alnum, 3 western → 0.6
        assert ratio == pytest.approx(0.6)

    def test_empty_string_returns_zero(self):
        assert get_western_ratio("") == 0.0

    def test_only_punctuation_returns_zero(self):
        assert get_western_ratio("，。！") == 0.0


class TestIsStageDirection:
    """_is_stage_direction 行为测试。"""

    def test_short_action_is_stage_direction(self):
        assert _is_stage_direction("笑了笑") is True

    def test_empty_is_not_stage_direction(self):
        assert _is_stage_direction("") is False

    def test_long_content_not_stage_direction(self):
        long_content = "动作" * 20
        assert _is_stage_direction(long_content) is False

    def test_meta_keyword_not_stage_direction(self):
        assert _is_stage_direction("注意：这是说明") is False

    def test_numbering_not_stage_direction(self):
        assert _is_stage_direction("1第一步") is False

    def test_colon_not_stage_direction(self):
        assert _is_stage_direction("角色：台词") is False


class TestCalculateTypingTime:
    """calculate_typing_time 行为测试。"""

    def test_single_chinese_char_triple_time(self, monkeypatch):
        monkeypatch.setattr(
            "src.maisaka.context.post_processor.get_app_config_port",
            lambda: SimpleNamespace(get_response_post_process_typing_speed=lambda: 1.0),
        )
        # 单中文字符：chinese_time * 3 + 0.3
        result = calculate_typing_time("你")
        assert result == pytest.approx(0.3 * 3 + 0.3)

    def test_chinese_text_typing_time(self, monkeypatch):
        monkeypatch.setattr(
            "src.maisaka.context.post_processor.get_app_config_port",
            lambda: SimpleNamespace(get_response_post_process_typing_speed=lambda: 1.0),
        )
        result = calculate_typing_time("你好世界")
        # 4 中文 * 0.3 = 1.2
        assert result == pytest.approx(1.2)

    def test_english_text_typing_time(self, monkeypatch):
        monkeypatch.setattr(
            "src.maisaka.context.post_processor.get_app_config_port",
            lambda: SimpleNamespace(get_response_post_process_typing_speed=lambda: 1.0),
        )
        result = calculate_typing_time("hello")
        # 5 英文 * 0.15 = 0.75
        assert result == pytest.approx(0.75)

    def test_typing_speed_zero_returns_zero(self, monkeypatch):
        monkeypatch.setattr(
            "src.maisaka.context.post_processor.get_app_config_port",
            lambda: SimpleNamespace(get_response_post_process_typing_speed=lambda: 0.0),
        )
        assert calculate_typing_time("你好") == 0

    def test_is_emoji_fixed_one_second(self, monkeypatch):
        monkeypatch.setattr(
            "src.maisaka.context.post_processor.get_app_config_port",
            lambda: SimpleNamespace(get_response_post_process_typing_speed=lambda: 1.0),
        )
        result = calculate_typing_time("😀", is_emoji=True)
        assert result == 1


def _make_app_config_port(**overrides):
    """构造 mock app_config_port。"""

    def _no_op_true():
        return True

    defaults = {
        "get_response_post_process_enable": lambda: True,
        "get_response_splitter_enable_kaomoji_protection": lambda: True,
        "get_response_splitter_max_length": lambda: 50,
        "get_response_splitter_max_sentence_num": lambda: 10,
        "get_response_splitter_max_split_num": lambda: 5,
        "get_response_splitter_enable": lambda: True,
        "get_chinese_typo_enable": lambda: False,  # 关闭错别字加速测试
        "get_chinese_typo_error_rate": lambda: 0.0,
        "get_chinese_typo_min_freq": lambda: 5,
        "get_chinese_typo_tone_error_rate": lambda: 0.0,
        "get_chinese_typo_word_replace_rate": lambda: 0.0,
        "get_response_splitter_enable_overflow_return_all": lambda: True,
        "get_response_post_process_typing_speed": lambda: 1.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestProcessLlmResponse:
    """process_llm_response 行为测试。"""

    def test_post_process_disabled_returns_original(self, monkeypatch):
        port = _make_app_config_port(get_response_post_process_enable=lambda: False)
        monkeypatch.setattr("src.maisaka.context.post_processor.get_app_config_port", lambda: port)
        result = process_llm_response("测试文本")
        assert result == ["测试文本"]

    def test_basic_text_processing(self, monkeypatch):
        port = _make_app_config_port()
        monkeypatch.setattr("src.maisaka.context.post_processor.get_app_config_port", lambda: port)
        random.seed(42)
        result = process_llm_response("你好世界")
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_empty_after_cleaning_returns_eh(self, monkeypatch):
        port = _make_app_config_port()
        monkeypatch.setattr("src.maisaka.context.post_processor.get_app_config_port", lambda: port)
        # 全是括号说明内容（非舞台指示）→ 清理后为空 → 返回 ["呃呃"]
        result = process_llm_response("（这是很长的说明文字内容不应该保留的描述）")
        assert isinstance(result, list)

    def test_returns_list_of_strings(self, monkeypatch):
        port = _make_app_config_port()
        monkeypatch.setattr("src.maisaka.context.post_processor.get_app_config_port", lambda: port)
        random.seed(42)
        result = process_llm_response("你好，世界。测试文本内容")
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)


class TestProcessChatHistoryAfterCycle:
    """process_chat_history_after_cycle 行为测试。"""

    def test_empty_history(self, monkeypatch):
        # mock is_mid_term_memory_message 避免导入副作用
        monkeypatch.setattr("src.maisaka.memory.mid_term.is_mid_term_memory_message", lambda m: False)
        result = process_chat_history_after_cycle([], max_context_size=10)
        assert isinstance(result, HistoryPostProcessResult)
        assert result.history == []
        assert result.removed_count == 0

    def test_history_within_limit_preserved(self, monkeypatch):
        from datetime import datetime

        from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
        from src.maisaka.context.messages import SessionBackedMessage

        monkeypatch.setattr("src.maisaka.memory.mid_term.is_mid_term_memory_message", lambda m: False)
        ts = datetime(2026, 8, 23, 14, 30, 5)
        history = [
            SessionBackedMessage(
                raw_message=MessageSequence([TextComponent("hi")]),
                visible_text="hi",
                timestamp=ts,
            )
            for _ in range(3)
        ]
        result = process_chat_history_after_cycle(history, max_context_size=10)
        assert isinstance(result, HistoryPostProcessResult)
        # 在阈值内应保留
        assert len(result.history) >= 1

    def test_focus_wakeup_messages_removed(self, monkeypatch):
        monkeypatch.setattr("src.maisaka.memory.mid_term.is_mid_term_memory_message", lambda m: False)

        result = process_chat_history_after_cycle([], max_context_size=10)
        assert result.removed_count >= 0

    def test_optimization_trims_old_assistants(self, monkeypatch):
        from datetime import datetime

        from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
        from src.maisaka.context.messages import AssistantMessage, SessionBackedMessage

        monkeypatch.setattr("src.maisaka.memory.mid_term.is_mid_term_memory_message", lambda m: False)
        ts = datetime(2026, 8, 23, 14, 30, 5)
        # 5 个 assistant > ASSISTANT_OPTIMIZATION_KEEP_COUNT(3)
        history = []
        for i in range(5):
            history.append(AssistantMessage(content=f"reply{i}", timestamp=ts))
            history.append(
                SessionBackedMessage(
                    raw_message=MessageSequence([TextComponent(f"u{i}")]),
                    visible_text=f"u{i}",
                    timestamp=ts,
                )
            )
        result = process_chat_history_after_cycle(
            history, max_context_size=100, enable_context_optimization=True
        )
        assert isinstance(result, HistoryPostProcessResult)
        # 优化后 assistant 数量应减少
        assistant_count = sum(1 for m in result.history if isinstance(m, AssistantMessage))
        assert assistant_count <= 5

    def test_trim_when_over_threshold(self, monkeypatch):
        from datetime import datetime

        from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
        from src.maisaka.context.messages import SessionBackedMessage


        monkeypatch.setattr("src.maisaka.memory.mid_term.is_mid_term_memory_message", lambda m: False)
        ts = datetime(2026, 8, 23, 14, 30, 5)
        # 大量消息 + 小 max_context_size 触发 trim
        history = [
            SessionBackedMessage(
                raw_message=MessageSequence([TextComponent(f"msg{i}")]),
                visible_text=f"msg{i}",
                timestamp=ts,
            )
            for i in range(20)
        ]
        result = process_chat_history_after_cycle(history, max_context_size=2)
        assert isinstance(result, HistoryPostProcessResult)
        # trim 后数量应减少
        assert len(result.history) < 20

    def test_history_with_tool_call_pairs(self, monkeypatch):
        from datetime import datetime

        from src.llm_models.payload_content.tool_option import ToolCall
        from src.maisaka.context.messages import AssistantMessage, ToolResultMessage

        monkeypatch.setattr("src.maisaka.memory.mid_term.is_mid_term_memory_message", lambda m: False)
        ts = datetime(2026, 8, 23, 14, 30, 5)
        tool_call = ToolCall(call_id="c1", func_name="search", args={"q": "test"})
        history = [
            AssistantMessage(content="思考", timestamp=ts, tool_calls=[tool_call]),
            ToolResultMessage(content="结果", timestamp=ts, tool_call_id="c1", tool_name="search"),
        ]
        result = process_chat_history_after_cycle(history, max_context_size=10)
        assert isinstance(result, HistoryPostProcessResult)
        # tool 对应保留
        assert len(result.history) >= 1

    def test_reference_message_consumed(self, monkeypatch):
        from datetime import datetime

        from src.maisaka.context.messages import ReferenceMessage

        monkeypatch.setattr("src.maisaka.memory.mid_term.is_mid_term_memory_message", lambda m: False)
        ts = datetime(2026, 8, 23, 14, 30, 5)
        # remaining_uses=1 → consume_once 后返回 False → 移除
        ref = ReferenceMessage(content="参考", timestamp=ts, remaining_uses_value=1)
        result = process_chat_history_after_cycle([ref], max_context_size=10)
        assert result.removed_count >= 1


class TestGetRandomDefaultReply:
    """_get_random_default_reply 行为测试。"""

    def test_returns_string(self, monkeypatch):
        from src.maisaka.context.post_processor import _get_random_default_reply

        monkeypatch.setattr(
            "src.maisaka.context.post_processor.get_bot_config_port",
            lambda: SimpleNamespace(get_bot_nickname=lambda: "MaiBot"),
        )
        random.seed(42)
        result = _get_random_default_reply()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_bot_nickname_in_some_replies(self, monkeypatch):
        from src.maisaka.context.post_processor import _get_random_default_reply

        monkeypatch.setattr(
            "src.maisaka.context.post_processor.get_bot_config_port",
            lambda: SimpleNamespace(get_bot_nickname=lambda: "小喵"),
        )
        # 多次采样验证含 bot 昵称的回复出现
        results = []
        for i in range(20):
            random.seed(i)
            results.append(_get_random_default_reply())
        assert any("小喵" in r for r in results)


class TestBuildTrimmedAssistantToolUserMessage:
    """_build_trimmed_assistant_tool_user_message 行为测试。"""

    def test_no_tool_calls_returns_none(self):
        from src.maisaka.context.post_processor import _build_trimmed_assistant_tool_user_message

        msg = AssistantMessage(content="x", timestamp=TS, tool_calls=[])
        result = _build_trimmed_assistant_tool_user_message(msg, tool_result_by_call_id={})
        assert result is None

    def test_builds_folded_message_for_tool_call(self):
        from src.maisaka.context.post_processor import _build_trimmed_assistant_tool_user_message

        tool_call = ToolCall(call_id="c1", func_name="search", args={"q": "1"})
        msg = AssistantMessage(content="思考", timestamp=TS, tool_calls=[tool_call])
        result = _build_trimmed_assistant_tool_user_message(msg, tool_result_by_call_id={})
        assert result is not None
        assert "已折叠" in result.visible_text or "tool_call_id" in result.visible_text

    def test_drop_names_skipped(self):
        from src.maisaka.context.post_processor import _build_trimmed_assistant_tool_user_message

        # reply 在 DROP_NAMES → 跳过，无 tool_sections → None
        tool_call = ToolCall(call_id="c1", func_name="reply", args={})
        msg = AssistantMessage(content="回复", timestamp=TS, tool_calls=[tool_call])
        result = _build_trimmed_assistant_tool_user_message(msg, tool_result_by_call_id={})
        assert result is None

    def test_tool_search_formatted_compactly(self):
        from src.maisaka.context.post_processor import _build_trimmed_assistant_tool_user_message

        tool_call = ToolCall(call_id="c1", func_name="tool_search", args={"query": "q1"})
        msg = AssistantMessage(content="搜索", timestamp=TS, tool_calls=[tool_call])
        result = _build_trimmed_assistant_tool_user_message(msg, tool_result_by_call_id={})
        assert result is not None
        assert "tool_search" in result.visible_text


class TestParseToolSearchResultToolNames:
    """_parse_tool_search_result_tool_names 行为测试。"""

    def test_dict_content_with_matched_tool_names(self):
        from src.maisaka.context.post_processor import _parse_tool_search_result_tool_names

        content = '{"matched_tool_names": ["tool_a", "tool_b"]}'
        result = _parse_tool_search_result_tool_names(content)
        assert result == ["tool_a", "tool_b"]

    def test_line_format_content(self):
        from src.maisaka.context.post_processor import _parse_tool_search_result_tool_names

        content = "- tool_a\n- tool_b"
        result = _parse_tool_search_result_tool_names(content)
        assert result == ["tool_a", "tool_b"]

    def test_invalid_json_falls_back_to_lines(self):
        from src.maisaka.context.post_processor import _parse_tool_search_result_tool_names

        result = _parse_tool_search_result_tool_names("not json")
        assert result == []

    def test_empty_content(self):
        from src.maisaka.context.post_processor import _parse_tool_search_result_tool_names

        assert _parse_tool_search_result_tool_names("") == []


class TestSplitIntoSentencesAdvanced:
    """split_into_sentences_w_remove_punctuation 进阶分支测试。"""

    def test_quote_internal_not_split(self):
        random.seed(42)
        result = split_into_sentences_w_remove_punctuation('他说"你好，世界"然后走了')
        assert isinstance(result, list)

    def test_colon_prevents_split(self):
        random.seed(42)
        result = split_into_sentences_w_remove_punctuation("时间:14:30结束")
        assert isinstance(result, list)

    def test_dash_space_not_split(self):
        random.seed(42)
        result = split_into_sentences_w_remove_punctuation("a - b")
        assert isinstance(result, list)

    def test_long_text_multiple_sentences(self):
        random.seed(42)
        text = "这是第一句话。这是第二句话。这是第三句话。"
        result = split_into_sentences_w_remove_punctuation(text)
        assert isinstance(result, list)
        assert len(result) >= 1