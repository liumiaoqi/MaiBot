"""ZG-N6 estimate 纯函数测试——对齐 dsh estimate.ts 行为。"""

import math

import pytest

from src.core.token_meter.estimate import (
    BLOCK_OVERHEAD,
    CHARS_PER_TOKEN,
    ROLE_OVERHEAD,
    estimate_content,
    estimate_message,
    estimate_system_prompt,
    estimate_text,
    estimate_tools_schema,
)


class TestEstimateText:
    def test_empty(self):
        assert estimate_text("") == 0

    def test_basic(self):
        assert estimate_text("abcd") == 1

    def test_cjk(self):
        assert estimate_text("中文字符") == math.ceil(4 / 4)

    def test_ceil(self):
        assert estimate_text("abc") == 1
        assert estimate_text("abcde") == 2

    def test_deterministic(self):
        text = "hello world 你好世界"
        assert estimate_text(text) == estimate_text(text) == estimate_text(text)

    def test_chars_per_token_is_4(self):
        assert CHARS_PER_TOKEN == 4


class TestEstimateContent:
    def test_empty(self):
        assert estimate_content([]) == 0

    def test_text_block(self):
        blocks = [{"type": "text", "text": "abcd"}]
        assert estimate_content(blocks) == 1 + BLOCK_OVERHEAD

    def test_reasoning_block(self):
        blocks = [{"type": "reasoning", "reasoning": "abcd"}]
        assert estimate_content(blocks) == 1 + BLOCK_OVERHEAD

    def test_tool_call_block(self):
        blocks = [{"type": "tool_call", "name": "fn", "arguments": {"k": "v"}}]
        result = estimate_content(blocks)
        assert result > BLOCK_OVERHEAD

    def test_tool_result_block(self):
        blocks = [{"type": "tool_result", "content": "abcd"}]
        assert estimate_content(blocks) == 1 + BLOCK_OVERHEAD

    def test_unknown_block(self):
        blocks = [{"type": "unknown", "data": "xyz"}]
        result = estimate_content(blocks)
        assert result > 0

    def test_multiple_blocks(self):
        blocks = [
            {"type": "text", "text": "abcd"},
            {"type": "text", "text": "efgh"},
        ]
        assert estimate_content(blocks) == 2 * (1 + BLOCK_OVERHEAD)


class TestEstimateMessage:
    def test_none(self):
        assert estimate_message(None) == ROLE_OVERHEAD + BLOCK_OVERHEAD

    def test_string(self):
        assert estimate_message("abcd") == 1

    def test_dict_with_content_list(self):
        msg = {"role": "user", "content": [{"type": "text", "text": "abcd"}]}
        assert estimate_message(msg) == (1 + BLOCK_OVERHEAD) + ROLE_OVERHEAD

    def test_dict_with_content_string(self):
        msg = {"role": "user", "content": "abcd"}
        assert estimate_message(msg) == 1 + BLOCK_OVERHEAD + ROLE_OVERHEAD

    def test_dict_with_text(self):
        msg = {"role": "user", "text": "abcd"}
        assert estimate_message(msg) == 1 + BLOCK_OVERHEAD + ROLE_OVERHEAD

    def test_object_with_content_list(self):
        class FakeMessage:
            def __init__(self):
                self.content = [{"type": "text", "text": "abcd"}]

        assert estimate_message(FakeMessage()) == (1 + BLOCK_OVERHEAD) + ROLE_OVERHEAD

    def test_object_with_processed_plain_text(self):
        class FakeMessage:
            processed_plain_text = "abcd"

        assert estimate_message(FakeMessage()) == 1 + BLOCK_OVERHEAD + ROLE_OVERHEAD

    def test_deterministic(self):
        msg = {"role": "user", "content": "hello"}
        assert estimate_message(msg) == estimate_message(msg) == estimate_message(msg)

    def test_non_negative(self):
        assert estimate_message(None) >= 0
        assert estimate_message("") >= 0
        assert estimate_message({}) >= 0


class TestEstimateSystemPrompt:
    def test_empty(self):
        assert estimate_system_prompt("") == BLOCK_OVERHEAD

    def test_basic(self):
        assert estimate_system_prompt("abcd") == 1 + BLOCK_OVERHEAD


class TestEstimateToolsSchema:
    def test_empty(self):
        assert estimate_tools_schema([]) == estimate_text("[]") + BLOCK_OVERHEAD

    def test_basic(self):
        tools = [{"name": "fn", "description": "do something"}]
        result = estimate_tools_schema(tools)
        assert result > BLOCK_OVERHEAD