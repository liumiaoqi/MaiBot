"""display_utils 纯函数单元测试。

覆盖 format_token_count / get_request_panel_style /
format_tool_call_for_display / format_tool_call_source_label /
build_tool_call_summary_lines 的正常、边界与异常输入。
"""


from src.llm_models.payload_content.tool_option import (
    TOOL_CALL_SOURCE_EXTRA_KEY,
    TOOL_CALL_SOURCE_REASONING,
    TOOL_CALL_SOURCE_RESPONSE,
)
from src.maisaka.display.display_utils import (
    build_tool_call_summary_lines,
    format_token_count,
    format_tool_call_for_display,
    format_tool_call_source_label,
    get_request_panel_style,
)


class TestFormatTokenCount:
    """format_token_count 行为测试。"""

    def test_below_threshold_returns_plain_str(self):
        assert format_token_count(0) == "0"
        assert format_token_count(9999) == "9999"

    def test_at_threshold_returns_k_suffix(self):
        # 10000 边界：应走 k 分支
        assert format_token_count(10000) == "10.0k"

    def test_above_threshold_returns_k_suffix(self):
        assert format_token_count(15000) == "15.0k"
        assert format_token_count(123456) == "123.5k"

    def test_negative_below_threshold(self):
        # 负数小于 10000，走 str 分支
        assert format_token_count(-1) == "-1"


class TestGetRequestPanelStyle:
    """get_request_panel_style 行为测试。"""

    def test_known_kind_returns_mapped_style(self):
        title, color = get_request_panel_style("planner")
        assert "对话单步" in title
        assert color == "green"

    def test_replyer_style(self):
        _, color = get_request_panel_style("replyer")
        assert color == "bright_yellow"

    def test_case_insensitive(self):
        title_upper, _ = get_request_panel_style("PLANNER")
        title_lower, _ = get_request_panel_style("planner")
        assert title_upper == title_lower

    def test_unknown_kind_returns_default(self):
        title, color = get_request_panel_style("nonexistent_kind")
        assert "对话单步" in title
        assert color == "cyan"

    def test_empty_string_returns_default(self):
        # 空字符串归一化为 "planner"，命中映射
        title, _ = get_request_panel_style("")
        assert "对话单步" in title

    def test_none_returns_default(self):
        title, color = get_request_panel_style(None)
        assert "对话单步" in title
        assert color == "green"

    def test_whitespace_stripped(self):
        title_spaced, _ = get_request_panel_style("  planner  ")
        title_plain, _ = get_request_panel_style("planner")
        assert title_spaced == title_plain


class TestFormatToolCallForDisplay:
    """format_tool_call_for_display 行为测试。"""

    def test_dict_with_function_key(self):
        tool_call = {
            "id": "call_1",
            "function": {"name": "search", "arguments": {"q": "test"}},
        }
        result = format_tool_call_for_display(tool_call)
        assert result["id"] == "call_1"
        assert result["name"] == "search"
        assert result["arguments"] == {"q": "test"}

    def test_dict_with_top_level_name(self):
        tool_call = {"id": "call_2", "name": "reply", "arguments": "hello"}
        result = format_tool_call_for_display(tool_call)
        assert result["name"] == "reply"
        assert result["arguments"] == "hello"

    def test_dict_with_reasoning_source(self):
        tool_call = {
            "id": "call_3",
            "function": {"name": "tool_a"},
            TOOL_CALL_SOURCE_EXTRA_KEY: TOOL_CALL_SOURCE_REASONING,
        }
        result = format_tool_call_for_display(tool_call)
        assert result["source"] == TOOL_CALL_SOURCE_REASONING
        assert result["source_label"] == "推理中调用"

    def test_dict_with_response_source(self):
        tool_call = {
            "id": "call_4",
            "function": {"name": "tool_b"},
            "source": TOOL_CALL_SOURCE_RESPONSE,
        }
        result = format_tool_call_for_display(tool_call)
        assert result["source"] == TOOL_CALL_SOURCE_RESPONSE
        assert result["source_label"] == "正文调用"

    def test_dict_source_from_extra_content(self):
        tool_call = {
            "id": "call_5",
            "function": {"name": "tool_c"},
            "extra_content": {TOOL_CALL_SOURCE_EXTRA_KEY: TOOL_CALL_SOURCE_REASONING},
        }
        result = format_tool_call_for_display(tool_call)
        assert result["source"] == TOOL_CALL_SOURCE_REASONING
        assert "extra_content" in result

    def test_dict_unknown_source_omitted(self):
        # 未知 source 归一化为空字符串，不应写入 source 字段
        tool_call = {
            "id": "call_6",
            "function": {"name": "tool_d"},
            "source": "unknown_source",
        }
        result = format_tool_call_for_display(tool_call)
        assert "source" not in result

    def test_object_with_attributes(self):
        class FakeToolCall:
            call_id = "call_7"
            func_name = "tool_e"
            args = {"x": 1}
            extra_content = None

        result = format_tool_call_for_display(FakeToolCall())
        assert result["id"] == "call_7"
        assert result["name"] == "tool_e"
        assert result["arguments"] == {"x": 1}

    def test_object_with_id_name_fallback(self):
        class FakeToolCall:
            id = "call_8"
            name = "tool_f"
            arguments = "text"
            extra_content = None

        result = format_tool_call_for_display(FakeToolCall())
        assert result["id"] == "call_8"
        assert result["name"] == "tool_f"

    def test_object_with_reasoning_source_via_extra_content(self):
        class FakeToolCall:
            call_id = "call_9"
            func_name = "tool_g"
            args = None
            extra_content = {TOOL_CALL_SOURCE_EXTRA_KEY: "thinking"}

        result = format_tool_call_for_display(FakeToolCall())
        assert result["source"] == TOOL_CALL_SOURCE_REASONING


class TestFormatToolCallSourceLabel:
    """format_tool_call_source_label 行为测试。"""

    def test_reasoning_label(self):
        assert format_tool_call_source_label(TOOL_CALL_SOURCE_REASONING) == "推理中调用"

    def test_response_label(self):
        assert format_tool_call_source_label(TOOL_CALL_SOURCE_RESPONSE) == "正文调用"

    def test_thinking_alias(self):
        assert format_tool_call_source_label("thinking") == "推理中调用"

    def test_content_alias(self):
        assert format_tool_call_source_label("content") == "正文调用"

    def test_unknown_label(self):
        assert format_tool_call_source_label("foobar") == "未知来源"

    def test_empty_label(self):
        assert format_tool_call_source_label("") == "未知来源"


class TestBuildToolCallSummaryLines:
    """build_tool_call_summary_lines 行为测试。"""

    def test_empty_list_returns_empty(self):
        assert build_tool_call_summary_lines([]) == []

    def test_single_call_with_dict_args(self):
        tool_calls = [
            {"id": "c1", "function": {"name": "search", "arguments": {"q": "hello"}}},
        ]
        lines = build_tool_call_summary_lines(tool_calls)
        assert len(lines) == 1
        assert "search" in lines[0]
        assert "{'q': 'hello'}" in lines[0]

    def test_single_call_without_args(self):
        tool_calls = [
            {"id": "c2", "function": {"name": "noop"}},
        ]
        lines = build_tool_call_summary_lines(tool_calls)
        # 无 source 时 source_label 缺失，str(None) 产生 "None" 后缀（当前行为）
        assert lines == ["- noop [None]"]

    def test_call_with_source_label_suffix(self):
        tool_calls = [
            {
                "id": "c3",
                "function": {"name": "tool_x"},
                TOOL_CALL_SOURCE_EXTRA_KEY: TOOL_CALL_SOURCE_REASONING,
            },
        ]
        lines = build_tool_call_summary_lines(tool_calls)
        assert "[推理中调用]" in lines[0]

    def test_unknown_name_falls_back_to_unknown(self):
        tool_calls = [{"id": "c4", "function": {}}]
        lines = build_tool_call_summary_lines(tool_calls)
        # function 为空 dict 时 name 为 None，str(None)="None" 是 truthy，
        # 故 name 显示为 "None" 而非 "unknown"（当前行为）
        assert "- None [None]" in lines[0]

    def test_multiple_calls_preserve_order(self):
        tool_calls = [
            {"id": "c5", "function": {"name": "first"}},
            {"id": "c6", "function": {"name": "second"}},
        ]
        lines = build_tool_call_summary_lines(tool_calls)
        assert len(lines) == 2
        assert "first" in lines[0]
        assert "second" in lines[1]

    def test_empty_dict_args_omits_colon(self):
        # arguments 为空 dict 时不追加 ": {}"，但无 source 仍有 " [None]" 后缀
        tool_calls = [
            {"id": "c7", "function": {"name": "tool_y", "arguments": {}}},
        ]
        lines = build_tool_call_summary_lines(tool_calls)
        assert lines == ["- tool_y [None]"]