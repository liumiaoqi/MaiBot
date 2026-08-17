"""ZG-26 测试：ThinkContext 向后兼容（favor_injection_text 默认空字符串）。"""

from src.core.types import ThinkContext


def test_think_context_default_favor_empty():
    """不传 favor_injection_text 时默认空字符串——向后兼容。"""
    context = ThinkContext(messages=())
    assert context.favor_injection_text == ""


def test_think_context_favor_set():
    """传入 favor_injection_text 时字段正确存储。"""
    context = ThinkContext(messages=(), favor_injection_text="测试好感度")
    assert context.favor_injection_text == "测试好感度"


def test_think_context_favor_empty_string():
    """显式传空字符串时字段为空。"""
    context = ThinkContext(messages=(), favor_injection_text="")
    assert context.favor_injection_text == ""