"""ZG-26 测试：配置关闭时行为与当前完全一致（回归测试）。

chat_loop_service 已 revert（P1-1 修复），旁观者路径回归由 test_b1_bystander_path.py 覆盖。
本文件保留 injected 段和 ThinkContext 的配置关闭回归。
"""

from unittest.mock import MagicMock


def test_config_off_injected_no_favor():
    """配置关闭时 injected 不含 favor 段（favor_injection_text 默认空）。"""
    from src.core.types import ThinkContext
    from src.maisaka.agent_autonomy.thinking_organ import ThinkingOrgan

    organ = ThinkingOrgan.__new__(ThinkingOrgan)
    organ._agent_id = "test_agent"
    organ._prompt_builder = MagicMock()
    organ._discovered_tools = []

    context = ThinkContext(messages=(), favor_injection_text="")
    parts = organ._build_injected_messages(context)
    assert not any("好感度：" in p for p in parts)


def test_config_off_think_context_favor_default_empty():
    """ThinkContext favor_injection_text 默认为空字符串。"""
    from src.core.types import ThinkContext

    ctx = ThinkContext(messages=())
    assert ctx.favor_injection_text == ""
