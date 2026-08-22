"""冷却配置透传测试（P0-A11b-2）。

验证配置 cooldown_minutes/max_interactions_per_hour/max_interactions_per_day
通过 bootstrap 透传到 InteractionTrigger，不再使用硬编码默认值 30/2/8。
"""


from src.core.types import AgentInteractionSnapshot
from src.maisaka.agent_interaction.bootstrap import build_interaction_scheduler


class TestCooldownConfigPassthrough:
    """冷却配置透传验证。"""

    def test_custom_cooldown_minutes_passthrough(
        self, mock_app_config_port, mock_agent_config_provider, mock_memory_port
    ):
        """配置 cooldown_minutes=10 透传到 InteractionTrigger。"""
        mock_app_config_port.get_agent_interaction_config.return_value = (
            AgentInteractionSnapshot(enabled=True, cooldown_minutes=10)
        )
        scheduler = build_interaction_scheduler(mock_memory_port)
        assert scheduler._trigger._cooldown_minutes == 10

    def test_custom_max_per_hour_passthrough(
        self, mock_app_config_port, mock_agent_config_provider, mock_memory_port
    ):
        """配置 max_interactions_per_hour=5 透传到 InteractionTrigger。"""
        mock_app_config_port.get_agent_interaction_config.return_value = (
            AgentInteractionSnapshot(enabled=True, max_interactions_per_hour=5)
        )
        scheduler = build_interaction_scheduler(mock_memory_port)
        assert scheduler._trigger._max_interactions_per_hour == 5

    def test_custom_max_per_day_passthrough(
        self, mock_app_config_port, mock_agent_config_provider, mock_memory_port
    ):
        """配置 max_interactions_per_day=20 透传到 InteractionTrigger。"""
        mock_app_config_port.get_agent_interaction_config.return_value = (
            AgentInteractionSnapshot(enabled=True, max_interactions_per_day=20)
        )
        scheduler = build_interaction_scheduler(mock_memory_port)
        assert scheduler._trigger._max_interactions_per_day == 20

    def test_default_config_not_hardcoded_30_2_8(
        self, mock_app_config_port, mock_agent_config_provider, mock_memory_port
    ):
        """默认配置（5/10/50）透传，非硬编码 30/2/8。"""
        mock_app_config_port.get_agent_interaction_config.return_value = (
            AgentInteractionSnapshot()
        )
        scheduler = build_interaction_scheduler(mock_memory_port)
        assert scheduler._trigger._cooldown_minutes == 5
        assert scheduler._trigger._max_interactions_per_hour == 10
        assert scheduler._trigger._max_interactions_per_day == 50