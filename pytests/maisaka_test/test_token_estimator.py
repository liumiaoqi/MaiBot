"""token_estimator 纯函数单元测试。

覆盖 estimate_text / estimate_system_prompt / estimate_tools_schema /
estimate_message / estimate_messages 的正常、边界与异常输入。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.maisaka.context.token_estimator import (
    BLOCK_OVERHEAD,
    CHARS_PER_TOKEN,
    DEFAULT_CONTEXT_WINDOW,
    ROLE_OVERHEAD,
    estimate_message,
    estimate_messages,
    estimate_system_prompt,
    estimate_text,
    estimate_tools_schema,
)


class TestEstimateText:
    """estimate_text 行为测试。"""

    def test_empty_string_returns_zero(self):
        assert estimate_text("") == 0

    def test_single_char_ceil_to_one(self):
        # len=1, ceil(1/2)=1
        assert estimate_text("a") == 1

    def test_two_chars_one_token(self):
        # len=2, ceil(2/2)=1
        assert estimate_text("ab") == 1

    def test_three_chars_two_tokens(self):
        # len=3, ceil(3/2)=2
        assert estimate_text("abc") == 2

    def test_chinese_text(self):
        # 中文 4 字符 → ceil(4/2)=2
        assert estimate_text("你好世界") == 2

    def test_long_text_scaling(self):
        text = "x" * 100
        assert estimate_text(text) == 50

    def test_odd_length_ceil(self):
        # len=5 → ceil(5/2)=3
        assert estimate_text("abcde") == 3


class TestEstimateSystemPrompt:
    """estimate_system_prompt 行为测试。"""

    def test_empty_prompt_only_overhead(self):
        # 空文本 0 + BLOCK_OVERHEAD
        assert estimate_system_prompt("") == BLOCK_OVERHEAD

    def test_prompt_includes_block_overhead(self):
        result = estimate_system_prompt("abcd")
        # estimate_text("abcd")=2 + BLOCK_OVERHEAD
        assert result == 2 + BLOCK_OVERHEAD

    def test_prompt_structure_overhead_constant(self):
        # 验证结构开销常量
        assert BLOCK_OVERHEAD == 4


class TestEstimateToolsSchema:
    """estimate_tools_schema 行为测试。"""

    def test_empty_list_only_overhead(self):
        # json.dumps([]) = "[]" len=2 → ceil(2/2)=1 + BLOCK_OVERHEAD
        result = estimate_tools_schema([])
        assert result == 1 + BLOCK_OVERHEAD

    def test_simple_tools(self):
        tools = [{"name": "search"}]
        import json

        expected_text = json.dumps(tools, ensure_ascii=False)
        expected = estimate_text(expected_text) + BLOCK_OVERHEAD
        assert estimate_tools_schema(tools) == expected

    def test_chinese_in_tools_preserved(self):
        tools = [{"description": "搜索工具"}]
        import json

        expected_text = json.dumps(tools, ensure_ascii=False)
        # ensure_ascii=False 保证中文不被转义
        assert "搜索工具" in expected_text
        assert estimate_tools_schema(tools) == estimate_text(expected_text) + BLOCK_OVERHEAD


class TestEstimateMessage:
    """estimate_message 行为测试。"""

    def test_empty_projection_returns_role_and_block_overhead(self):
        message = SimpleNamespace(processed_plain_text="")
        result = estimate_message(message)
        assert result == BLOCK_OVERHEAD + ROLE_OVERHEAD

    def test_message_with_text(self):
        message = SimpleNamespace(processed_plain_text="abcd")
        # estimate_text("abcd")=2 + BLOCK_OVERHEAD + ROLE_OVERHEAD
        assert estimate_message(message) == 2 + BLOCK_OVERHEAD + ROLE_OVERHEAD

    def test_enable_visual_message_param_accepted(self):
        # 轻量近似不依赖 enable_visual_message，两个值应相等
        message = SimpleNamespace(processed_plain_text="hello")
        assert estimate_message(message, enable_visual_message=True) == estimate_message(
            message, enable_visual_message=False
        )

    def test_missing_processed_plain_text_falls_back_to_empty(self):
        # getattr 默认返回 "" 兜底
        message = SimpleNamespace()
        result = estimate_message(message)
        assert result == BLOCK_OVERHEAD + ROLE_OVERHEAD

    def test_none_processed_plain_text_falls_back_to_empty(self):
        message = SimpleNamespace(processed_plain_text=None)
        result = estimate_message(message)
        assert result == BLOCK_OVERHEAD + ROLE_OVERHEAD

    def test_property_access_exception_returns_empty(self):
        # 属性访问抛异常时兜底空字符串
        message = MagicMock()
        type(message).processed_plain_text = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        result = estimate_message(message)
        assert result == BLOCK_OVERHEAD + ROLE_OVERHEAD


class TestEstimateMessages:
    """estimate_messages 行为测试。"""

    def test_empty_list_returns_zero(self):
        assert estimate_messages([]) == 0

    def test_single_message(self):
        message = SimpleNamespace(processed_plain_text="abcd")
        assert estimate_messages([message]) == estimate_message(message)

    def test_multiple_messages_summed(self):
        m1 = SimpleNamespace(processed_plain_text="ab")  # 1 + 8
        m2 = SimpleNamespace(processed_plain_text="abcd")  # 2 + 8
        m3 = SimpleNamespace(processed_plain_text="")  # 0 + 8
        total = estimate_messages([m1, m2, m3])
        assert total == estimate_message(m1) + estimate_message(m2) + estimate_message(m3)

    def test_constants_consistency(self):
        assert CHARS_PER_TOKEN == 2
        assert DEFAULT_CONTEXT_WINDOW == 65536
        assert ROLE_OVERHEAD == 4