"""ZG16-2 token 估算器单元测试——纯函数无副作用验证。

覆盖 estimate_text/estimate_system_prompt/estimate_tools_schema/
estimate_message/estimate_messages 及模块常量，验证 2 字符/token 估算 +
结构开销模型 + 纯函数性（同一输入连续估算结果不变）。
"""


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


def _make_mock_message(text: str) -> MagicMock:
    """构造 mock 消息对象，设置 processed_plain_text 属性。"""
    msg = MagicMock()
    msg.processed_plain_text = text
    return msg


# ════════════════════════════════════════════════════════════════════
# 常量验证
# ════════════════════════════════════════════════════════════════════


def test_constants_values():
    """验证模块常量值符合 design 规格。"""
    assert CHARS_PER_TOKEN == 2
    assert BLOCK_OVERHEAD == 4
    assert ROLE_OVERHEAD == 4
    assert DEFAULT_CONTEXT_WINDOW == 65536


# ════════════════════════════════════════════════════════════════════
# estimate_text
# ════════════════════════════════════════════════════════════════════


def test_estimate_text_chinese_long():
    """中文长文：ceil(100/2) == 50。"""
    assert estimate_text("中" * 100) == 50


def test_estimate_text_english_long():
    """英文长文：ceil(100/2) == 50。"""
    assert estimate_text("a" * 100) == 50


def test_estimate_text_empty():
    """空文本返回 0。"""
    assert estimate_text("") == 0


def test_estimate_text_odd_length():
    """奇数长度向上取整：ceil(101/2) == 51。"""
    assert estimate_text("a" * 101) == 51


# ════════════════════════════════════════════════════════════════════
# estimate_system_prompt
# ════════════════════════════════════════════════════════════════════


def test_estimate_system_prompt_with_overhead():
    """system prompt 含 BLOCK_OVERHEAD：ceil(200/2) + 4 == 104。"""
    assert estimate_system_prompt("a" * 200) == 104


def test_estimate_system_prompt_empty():
    """空 system prompt 仅含开销：0 + 4 == 4。"""
    assert estimate_system_prompt("") == BLOCK_OVERHEAD


# ════════════════════════════════════════════════════════════════════
# estimate_tools_schema
# ════════════════════════════════════════════════════════════════════


def test_estimate_tools_schema_empty_list():
    """空 tools schema 含 BLOCK_OVERHEAD：ceil(len('[]')/2) + 4 == 5。"""
    result = estimate_tools_schema([])
    # json.dumps([]) = "[]"，len=2，ceil(2/2)=1，1+4=5
    assert result == 5
    assert result > BLOCK_OVERHEAD  # 含结构开销


def test_estimate_tools_schema_nonempty():
    """非空 tools schema 估算含结构开销且大于空 schema。"""
    tools = [{"name": "tool1", "description": "test tool"}]
    result = estimate_tools_schema(tools)
    assert result > BLOCK_OVERHEAD
    assert result > estimate_tools_schema([])


# ════════════════════════════════════════════════════════════════════
# estimate_message
# ════════════════════════════════════════════════════════════════════


def test_estimate_message_with_text():
    """单条消息估算：ceil(len/2) + BLOCK_OVERHEAD + ROLE_OVERHEAD。"""
    msg = _make_mock_message("hello")
    # ceil(5/2) + 4 + 4 = 3 + 8 = 11
    assert estimate_message(msg) == 11


def test_estimate_message_empty_text():
    """空消息仅含结构开销：0 + 4 + 4 == 8。"""
    msg = _make_mock_message("")
    assert estimate_message(msg) == BLOCK_OVERHEAD + ROLE_OVERHEAD


def test_estimate_message_pure_function():
    """纯函数性：同一消息连续估算 2 次结果完全相同。"""
    msg = _make_mock_message("test message for purity check")
    first = estimate_message(msg)
    second = estimate_message(msg)
    assert first == second


def test_estimate_message_no_attribute_fallback():
    """消息无 processed_plain_text 属性时降级为空字符串不崩溃。"""

    class _BareMessage:
        """无 processed_plain_text 属性的裸对象。"""

    msg = _BareMessage()
    result = estimate_message(msg)
    assert result == BLOCK_OVERHEAD + ROLE_OVERHEAD


def test_estimate_message_attribute_exception_fallback():
    """processed_plain_text 属性访问抛异常时降级为空字符串不崩溃。"""

    class _ExceptionMessage:
        """processed_plain_text 属性访问会抛异常的对象。"""

        @property
        def processed_plain_text(self) -> str:
            raise RuntimeError("attribute access broken")

    msg = _ExceptionMessage()
    result = estimate_message(msg)
    assert result == BLOCK_OVERHEAD + ROLE_OVERHEAD


# ════════════════════════════════════════════════════════════════════
# estimate_messages
# ════════════════════════════════════════════════════════════════════


def test_estimate_messages_accumulation():
    """estimate_messages 累加：estimate_messages([m1,m2,m3]) == sum(estimate_message(mi))。"""
    msgs = [
        _make_mock_message("hello"),
        _make_mock_message("world"),
        _make_mock_message("foo bar baz"),
    ]
    total = estimate_messages(msgs)
    expected = sum(estimate_message(m) for m in msgs)
    assert total == expected


def test_estimate_messages_empty_list():
    """空消息列表返回 0。"""
    assert estimate_messages([]) == 0


def test_estimate_messages_single_message():
    """单条消息列表等于 estimate_message。"""
    msg = _make_mock_message("single message")
    assert estimate_messages([msg]) == estimate_message(msg)