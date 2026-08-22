"""prompt_cli_renderer 单元测试。

覆盖 PromptCLIVisualizer 的纯计算方法：
get_request_panel_style / _format_token_count / build_prompt_stats_text /
_normalize_image_format / _normalize_preview_metadata /
_extract_image_pair / _extract_data_url_image / _extract_image_dict_pair /
format_tool_call_for_display / _serialize_message_content_for_dump /
build_prompt_dump_text / build_structured_message_payload /
_build_structured_output_payload / _select_webui_local_host。
"""

from base64 import b64encode


from src.maisaka.display.prompt_cli_renderer import (
    PromptCLIVisualizer,
    _select_webui_local_host,
)


class TestPromptCLIVisualizerPanelStyle:
    """面板样式方法测试。"""

    def test_get_request_panel_style_delegates(self):
        title, color = PromptCLIVisualizer.get_request_panel_style("planner")
        assert color == "green"

    def test_format_token_count_delegates(self):
        assert PromptCLIVisualizer._format_token_count(15000) == "15.0k"
        assert PromptCLIVisualizer._format_token_count(100) == "100"


class TestBuildPromptStatsText:
    """build_prompt_stats_text 行为测试。"""

    def test_basic_stats(self):
        text = PromptCLIVisualizer.build_prompt_stats_text(
            selected_history_count=10,
            built_message_count=12,
            prompt_tokens=500,
            completion_tokens=100,
            total_tokens=600,
        )
        assert "上下文消息数量=10" in text
        assert "已构建消息数=12" in text
        assert "实际输入Token=500" in text
        assert "输出Token=100" in text
        assert "总Token=600" in text

    def test_large_token_uses_k_suffix(self):
        text = PromptCLIVisualizer.build_prompt_stats_text(
            selected_history_count=0,
            built_message_count=0,
            prompt_tokens=20000,
            completion_tokens=15000,
            total_tokens=35000,
        )
        assert "实际输入Token=20.0k" in text
        assert "输出Token=15.0k" in text
        assert "总Token=35.0k" in text


class TestNormalizeImageFormat:
    """_normalize_image_format 行为测试。"""

    def test_jpg_normalized_to_jpeg(self):
        assert PromptCLIVisualizer._normalize_image_format("jpg") == "jpeg"

    def test_png_unchanged(self):
        assert PromptCLIVisualizer._normalize_image_format("png") == "png"

    def test_case_insensitive(self):
        assert PromptCLIVisualizer._normalize_image_format("PNG") == "png"

    def test_strips_whitespace(self):
        assert PromptCLIVisualizer._normalize_image_format("  webp  ") == "webp"


class TestNormalizePreviewMetadata:
    """_normalize_preview_metadata 行为测试。"""

    def test_empty_returns_empty_dict(self):
        assert PromptCLIVisualizer._normalize_preview_metadata(None) == {}
        assert PromptCLIVisualizer._normalize_preview_metadata({}) == {}

    def test_extracts_model_name(self):
        result = PromptCLIVisualizer._normalize_preview_metadata(
            {"model_name": "deepseek-v3"}
        )
        assert result["model_name"] == "deepseek-v3"

    def test_model_fallback_key(self):
        result = PromptCLIVisualizer._normalize_preview_metadata(
            {"model": "fallback-model"}
        )
        assert result["model_name"] == "fallback-model"

    def test_duration_ms_rounded(self):
        result = PromptCLIVisualizer._normalize_preview_metadata(
            {"duration_ms": 123.456}
        )
        assert result["duration_ms"] == 123.46

    def test_invalid_duration_ms_omitted(self):
        result = PromptCLIVisualizer._normalize_preview_metadata(
            {"duration_ms": "not-a-number"}
        )
        assert "duration_ms" not in result


class TestExtractImagePair:
    """_extract_image_pair 行为测试。"""

    def test_valid_tuple(self):
        img_bytes = b"\x89PNG\r\n\x1a\n"
        b64 = b64encode(img_bytes).decode()
        result = PromptCLIVisualizer._extract_image_pair(("png", b64))
        assert result is not None
        assert result[0] == "png"

    def test_unsupported_format_returns_none(self):
        img_bytes = b"x"
        b64 = b64encode(img_bytes).decode()
        result = PromptCLIVisualizer._extract_image_pair(("bmp", b64))
        assert result is None

    def test_non_string_elements_returns_none(self):
        result = PromptCLIVisualizer._extract_image_pair((123, "abc"))
        assert result is None

    def test_wrong_length_returns_none(self):
        result = PromptCLIVisualizer._extract_image_pair(("png", "abc", "extra"))
        assert result is None

    def test_non_tuple_returns_none(self):
        result = PromptCLIVisualizer._extract_image_pair("not-a-tuple")
        assert result is None


class TestExtractDataUrlImage:
    """_extract_data_url_image 行为测试。"""

    def test_valid_data_url(self):
        b64 = b64encode(b"test").decode()
        url = f"data:image/png;base64,{b64}"
        result = PromptCLIVisualizer._extract_data_url_image(url)
        assert result is not None
        assert result[0] == "png"
        assert result[1] == b64

    def test_non_data_url_returns_none(self):
        assert PromptCLIVisualizer._extract_data_url_image("https://example.com/img.png") is None

    def test_missing_base64_marker_returns_none(self):
        assert PromptCLIVisualizer._extract_data_url_image("data:image/png,raw") is None


class TestExtractImageDictPair:
    """_extract_image_dict_pair 行为测试。"""

    def test_image_url_with_data_url(self):
        b64 = b64encode(b"test").decode()
        item = {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        }
        result = PromptCLIVisualizer._extract_image_dict_pair(item)
        assert result is not None
        assert result[0] == "jpeg"

    def test_image_base64_fields(self):
        item = {
            "type": "image",
            "image_base64": "abc",
            "image_format": "png",
        }
        result = PromptCLIVisualizer._extract_image_dict_pair(item)
        assert result == ("png", "abc")

    def test_unsupported_type_returns_none(self):
        result = PromptCLIVisualizer._extract_image_dict_pair({"type": "text"})
        assert result is None

    def test_non_dict_returns_none(self):
        result = PromptCLIVisualizer._extract_image_dict_pair("not-a-dict")
        assert result is None


class TestSerializeMessageContentForDump:
    """_serialize_message_content_for_dump 行为测试。"""

    def test_string_content_unchanged(self):
        assert PromptCLIVisualizer._serialize_message_content_for_dump("hello") == "hello"

    def test_none_returns_empty(self):
        assert PromptCLIVisualizer._serialize_message_content_for_dump(None) == ""

    def test_list_of_strings_joined(self):
        result = PromptCLIVisualizer._serialize_message_content_for_dump(["a", "b"])
        assert result == "a\nb"

    def test_list_with_text_dict(self):
        result = PromptCLIVisualizer._serialize_message_content_for_dump(
            [{"type": "text", "text": "hello"}]
        )
        assert result == "hello"

    def test_list_with_image_tuple(self):
        b64 = b64encode(b"test").decode()
        result = PromptCLIVisualizer._serialize_message_content_for_dump(
            [("png", b64)]
        )
        assert "图片" in result
        assert "image/png" in result


class TestBuildPromptDumpText:
    """build_prompt_dump_text 行为测试。"""

    def test_empty_messages_returns_placeholder(self):
        result = PromptCLIVisualizer.build_prompt_dump_text([])
        assert result == "[空 Prompt]"

    def test_single_message(self):
        messages = [{"role": "user", "content": "你好"}]
        result = PromptCLIVisualizer.build_prompt_dump_text(messages)
        assert "role=user" in result
        assert "你好" in result

    def test_multiple_messages_separated(self):
        messages = [
            {"role": "user", "content": "问题"},
            {"role": "assistant", "content": "回答"},
        ]
        result = PromptCLIVisualizer.build_prompt_dump_text(messages)
        assert "role=user" in result
        assert "role=assistant" in result
        # 应有分隔线
        assert "=" in result


class TestBuildStructuredMessagePayload:
    """build_structured_message_payload 行为测试。"""

    def test_basic_messages(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        result = PromptCLIVisualizer.build_structured_message_payload(
            messages, keep_base64=False
        )
        assert len(result) == 2
        assert result[0]["index"] == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "hello"
        assert result[1]["index"] == 2

    def test_empty_messages(self):
        result = PromptCLIVisualizer.build_structured_message_payload(
            [], keep_base64=False
        )
        assert result == []

    def test_message_with_tool_calls(self):
        messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "function": {"name": "search", "arguments": {"q": "x"}}},
                ],
            },
        ]
        result = PromptCLIVisualizer.build_structured_message_payload(
            messages, keep_base64=False
        )
        assert "tool_calls" in result[0]
        assert result[0]["tool_calls"][0]["name"] == "search"


class TestBuildStructuredOutputPayload:
    """_build_structured_output_payload 行为测试。"""

    def test_none_content_and_no_tool_calls_returns_none(self):
        result = PromptCLIVisualizer._build_structured_output_payload(
            None, "输出", None, keep_base64=False
        )
        assert result is None

    def test_empty_content_and_no_tool_calls_returns_none(self):
        result = PromptCLIVisualizer._build_structured_output_payload(
            "", "输出", None, keep_base64=False
        )
        assert result is None

    def test_with_content(self):
        result = PromptCLIVisualizer._build_structured_output_payload(
            "回复文本", "输出", None, keep_base64=False
        )
        assert result["title"] == "输出"
        assert result["content"] == "回复文本"

    def test_with_tool_calls(self):
        tool_calls = [
            {"id": "c1", "function": {"name": "reply", "arguments": "hi"}},
        ]
        result = PromptCLIVisualizer._build_structured_output_payload(
            None, "输出", tool_calls, keep_base64=False
        )
        assert "tool_calls" in result
        assert result["tool_calls"][0]["name"] == "reply"


class TestSelectWebuiLocalHost:
    """_select_webui_local_host 行为测试。"""

    def test_string_host(self):
        assert _select_webui_local_host("0.0.0.0") == "0.0.0.0"

    def test_empty_string_returns_localhost(self):
        assert _select_webui_local_host("") == "127.0.0.1"

    def test_list_prefers_127(self):
        result = _select_webui_local_host(["0.0.0.0", "127.0.0.1"])
        assert result == "127.0.0.1"

    def test_list_prefers_ipv6_loopback(self):
        result = _select_webui_local_host(["0.0.0.0", "::1"])
        assert result == "::1"

    def test_list_falls_back_to_first(self):
        result = _select_webui_local_host(["192.168.1.1", "10.0.0.1"])
        assert result == "192.168.1.1"

    def test_non_list_non_string_returns_localhost(self):
        assert _select_webui_local_host(None) == "127.0.0.1"
        assert _select_webui_local_host(123) == "127.0.0.1"

    def test_empty_list_returns_localhost(self):
        assert _select_webui_local_host([]) == "127.0.0.1"