"""ZG-26 测试：orchestrator favor 路径行为测试（P1-4 补 P0 未捕获根因）。

dsh 终审 P0：orchestrator.py 函数内 import 路径错误致 b2 favor 注入静默失效。
29 测试无一运行 orchestrator._build_think_context——P0 不可见。
本测试直接调 _build_think_context 断言 favor_injection_text 行为。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.types import ThinkContext
from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator


def _make_orchestrator():
    """构造最小 AgentOrchestrator 实例（绕过 __init__）。"""
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    orch._session_id = "test_session"
    orch._session_name = "test_session_name"
    orch._is_group_chat = False

    # chat_loop_adapter.chat_loop_service 提供用户名/ID
    mock_cls = MagicMock()
    mock_cls._current_user_name = "测试用户"
    mock_cls._current_user_id = "user_123"
    orch._chat_loop_adapter = MagicMock()
    orch._chat_loop_adapter.chat_loop_service = mock_cls
    return orch


def _make_agent(agent_id="test_agent"):
    """构造 mock AutonomousAgent。"""
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.get_inner_world_snapshot = AsyncMock(return_value=None)
    return agent


def _make_mock_agent_config(favor_text="你关心测试用户"):
    """构造 mock agent_config，get_favor_injection 返回非空文本。"""
    mock_config = MagicMock()
    mock_config.get_favor_injection.return_value = favor_text
    return mock_config


@pytest.mark.asyncio
async def test_favor_injection_text_nonempty_when_enabled():
    """配置开启 + agent 有 favor → favor_injection_text 非空（P0 核心断言）。"""
    orch = _make_orchestrator()
    agent = _make_agent()
    mock_config = _make_mock_agent_config("你关心测试用户")

    with patch("src.maisaka.agent_autonomy.orchestrator.get_app_config_port") as mock_acp:
        mock_acp.return_value.is_cache_prefix_stability_enabled.return_value = True
        with patch("src.core.adapters.agent_config_port.get_agent_config_provider") as mock_reg:
            mock_reg.return_value.has_agent.return_value = True
            mock_reg.return_value.get_agent.return_value = mock_config
            with patch("src.maisaka.agent_autonomy.orchestrator.get_bot_config_port") as mock_bcp:
                mock_bcp.return_value.get_bot_owner_user_ids.return_value = ["user_123"]
                with patch.object(orch, "_load_thought_summary", new=AsyncMock(return_value=("", 0.0))):
                    ctx = await orch._build_think_context(agent, messages=())

    assert ctx.favor_injection_text == "你关心测试用户", (
        f"favor_injection_text 应为 '你关心测试用户'，实际: {ctx.favor_injection_text!r}"
    )


@pytest.mark.asyncio
async def test_favor_injection_text_empty_when_disabled():
    """配置关闭 → favor_injection_text 为空。"""
    orch = _make_orchestrator()
    agent = _make_agent()
    mock_config = _make_mock_agent_config("你关心测试用户")

    with patch("src.maisaka.agent_autonomy.orchestrator.get_app_config_port") as mock_acp:
        mock_acp.return_value.is_cache_prefix_stability_enabled.return_value = False
        with patch("src.core.adapters.agent_config_port.get_agent_config_provider") as mock_reg:
            mock_reg.return_value.has_agent.return_value = True
            mock_reg.return_value.get_agent.return_value = mock_config
            with patch("src.maisaka.agent_autonomy.orchestrator.get_bot_config_port") as mock_bcp:
                mock_bcp.return_value.get_bot_owner_user_ids.return_value = ["user_123"]
                with patch.object(orch, "_load_thought_summary", new=AsyncMock(return_value=("", 0.0))):
                    ctx = await orch._build_think_context(agent, messages=())

    assert ctx.favor_injection_text == "", (
        f"配置关闭时 favor_injection_text 应为空，实际: {ctx.favor_injection_text!r}"
    )


@pytest.mark.asyncio
async def test_favor_injection_text_empty_when_port_none():
    """port 为 None（registry 未注册）→ 降级为空，不崩溃。"""
    orch = _make_orchestrator()
    agent = _make_agent()

    with patch("src.maisaka.agent_autonomy.orchestrator.get_app_config_port", return_value=None):
        with patch.object(orch, "_load_thought_summary", new=AsyncMock(return_value=("", 0.0))):
            ctx = await orch._build_think_context(agent, messages=())

    assert ctx.favor_injection_text == ""
    assert isinstance(ctx, ThinkContext)


@pytest.mark.asyncio
async def test_favor_injection_text_empty_when_agent_not_registered():
    """agent 未在 registry 注册 → favor_injection_text 为空。"""
    orch = _make_orchestrator()
    agent = _make_agent()

    with patch("src.maisaka.agent_autonomy.orchestrator.get_app_config_port") as mock_acp:
        mock_acp.return_value.is_cache_prefix_stability_enabled.return_value = True
        with patch("src.core.adapters.agent_config_port.get_agent_config_provider") as mock_reg:
            mock_reg.return_value.has_agent.return_value = False
            with patch.object(orch, "_load_thought_summary", new=AsyncMock(return_value=("", 0.0))):
                ctx = await orch._build_think_context(agent, messages=())

    assert ctx.favor_injection_text == ""


@pytest.mark.asyncio
async def test_favor_uses_real_user_params():
    """P1-2：favor 使用真实 user_name/is_owner（非硬编码空串/False）。"""
    orch = _make_orchestrator()
    agent = _make_agent()
    mock_config = _make_mock_agent_config()

    with patch("src.maisaka.agent_autonomy.orchestrator.get_app_config_port") as mock_acp:
        mock_acp.return_value.is_cache_prefix_stability_enabled.return_value = True
        with patch("src.core.adapters.agent_config_port.get_agent_config_provider") as mock_reg:
            mock_reg.return_value.has_agent.return_value = True
            mock_reg.return_value.get_agent.return_value = mock_config
            with patch("src.maisaka.agent_autonomy.orchestrator.get_bot_config_port") as mock_bcp:
                mock_bcp.return_value.get_bot_owner_user_ids.return_value = ["user_123"]
                with patch.object(orch, "_load_thought_summary", new=AsyncMock(return_value=("", 0.0))):
                    await orch._build_think_context(agent, messages=())

    mock_config.get_favor_injection.assert_called_once_with(user_name="测试用户", is_owner=True)


def test_no_wrong_import_in_orchestrator():
    """P0 静态回归：orchestrator.py 不含错误 import 路径。"""
    from pathlib import Path

    content = Path("src/maisaka/agent_autonomy/orchestrator.py").read_text(encoding="utf-8")
    assert "from src.core.adapters.app_config_port import get_app_config_port" not in content, (
        "orchestrator.py 不应含错误 import 路径 src.core.adapters.app_config_port"
    )