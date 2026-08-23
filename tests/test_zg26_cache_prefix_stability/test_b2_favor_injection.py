"""ZG-26 测试：b2 角色化路径 favor 置空（prompt_builder._build_embodied_context）。

通过 monkeypatch app_config_port 控制配置开关，
构造 EmbodiedPlannerPromptBuilder 实例直接调 _build_embodied_context 断言返回值。
"""

from unittest.mock import patch, MagicMock


def _make_prompt_builder():
    """构造最小 EmbodiedPlannerPromptBuilder 实例用于测试。"""
    from src.maisaka.agent_autonomy.prompt_builder import EmbodiedPlannerPromptBuilder
    builder = EmbodiedPlannerPromptBuilder.__new__(EmbodiedPlannerPromptBuilder)
    builder._agent_id = "test_agent"
    builder._identity_providers = []
    builder._degraded = False
    return builder


def _make_mock_config():
    """构造 mock agent_config。"""
    mock_config = MagicMock()
    mock_config.identity_prompt = "测试人设"
    mock_config.anti_mechanization_prompt = ""
    mock_config.internal_relationships_prompt = ""
    mock_config.internal_relationships = []
    mock_config.get_favor_injection.return_value = "好感度文本"
    return mock_config


async def _run_builder(builder, enabled):
    """在 patch 环境下运行 _build_embodied_context。"""
    mock_config = _make_mock_config()
    with patch("src.core.adapters.agent_config_port.get_agent_config_provider") as mock_reg:
        mock_reg.return_value.get_agent.return_value = mock_config
        with patch("src.maisaka.agent_autonomy.prompt_builder.get_app_config_port") as mock_acp:
            mock_acp.return_value.is_cache_prefix_stability_enabled.return_value = enabled
            with patch.object(builder, "_build_agent_interaction_memory", return_value=""):
                with patch.object(builder, "_get_agent_display_name", return_value="测试"):
                    with patch.object(builder, "_build_query_memory_rule", return_value=""):
                        with patch.object(builder, "_build_butler_context", return_value=""):
                            with patch.object(builder, "_build_cohabitant_states", return_value=""):
                                with patch.object(builder, "_build_expression_layer_text", return_value=""):
                                    return await builder._build_embodied_context("")


async def test_b2_characterized_favor_emptied_when_enabled():
    """配置开启时角色化路径 favor 为空字符串。"""
    builder = _make_prompt_builder()
    result = await _run_builder(builder, enabled=True)
    assert result["agent_favor_injection"] == "", f"favor 应为空: {result['agent_favor_injection']}"


async def test_b2_characterized_favor_preserved_when_disabled():
    """配置关闭时角色化路径 favor 保持原值。"""
    builder = _make_prompt_builder()
    result = await _run_builder(builder, enabled=False)
    assert result["agent_favor_injection"] == "好感度文本", f"favor 应保持原值: {result['agent_favor_injection']}"


async def test_b2_characterized_emotion_relationship_always_empty():
    """角色化路径 emotion/relationship 始终为空（既有行为，ZG-26 不改）。"""
    builder = _make_prompt_builder()
    result = await _run_builder(builder, enabled=False)
    assert result["agent_emotion_state"] == ""
    assert result["agent_relationship"] == ""
