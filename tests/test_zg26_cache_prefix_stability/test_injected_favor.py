"""ZG-26 测试：injected 新增 favor 段（thinking_organ._build_injected_messages）。"""

from src.core.types import ThinkContext
from src.maisaka.agent_autonomy.thinking_organ import ThinkingOrgan


def _make_thinking_organ():
    """构造最小 ThinkingOrgan 实例用于测试 _build_injected_messages。"""
    from unittest.mock import MagicMock
    organ = ThinkingOrgan.__new__(ThinkingOrgan)
    organ._agent_id = "test_agent"
    organ._prompt_builder = MagicMock()
    organ._discovered_tools = []
    return organ


def test_injected_contains_favor():
    """favor_injection_text 非空时 injected 含 '好感度：' 段。"""
    organ = _make_thinking_organ()
    context = ThinkContext(messages=(), favor_injection_text="很喜欢这个用户")
    parts = organ._build_injected_messages(context)
    assert any("好感度：很喜欢这个用户" in p for p in parts), f"favor 段缺失: {parts}"


def test_injected_empty_favor_no_segment():
    """favor_injection_text 为空时 injected 不含 '好感度：' 段。"""
    organ = _make_thinking_organ()
    context = ThinkContext(messages=(), favor_injection_text="")
    parts = organ._build_injected_messages(context)
    assert not any("好感度：" in p for p in parts), f"不应有 favor 段: {parts}"


def test_injected_favor_after_relationship():
    """favor 段在 relationship 段之后（与 design 3.2 顺序一致）。"""
    organ = _make_thinking_organ()
    context = ThinkContext(
        messages=(),
        relationship_text="朋友关系",
        favor_injection_text="好感度高",
    )
    parts = organ._build_injected_messages(context)
    rel_idx = next((i for i, p in enumerate(parts) if "关系描述：" in p), -1)
    favor_idx = next((i for i, p in enumerate(parts) if "好感度：" in p), -1)
    assert rel_idx >= 0, f"relationship 段缺失: {parts}"
    assert favor_idx >= 0, f"favor 段缺失: {parts}"
    assert favor_idx > rel_idx, f"favor 应在 relationship 之后: rel={rel_idx} favor={favor_idx}"