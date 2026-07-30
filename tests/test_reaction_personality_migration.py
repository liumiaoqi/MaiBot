"""ZG 人格迁移测试 — 红包反应从 expression_layer 匹配"""

from src.maisaka.agent.config import AgentConfig, LayeredPersonality


class TestReactionPersonalityMigration:
    """红包反应从 layered_personality.expression_layer.lower() 匹配关键词"""

    def _get_personality(self, agent_config: AgentConfig) -> str:
        return (
            agent_config.layered_personality.expression_layer.lower()
            if agent_config.layered_personality and agent_config.layered_personality.expression_layer
            else ""
        )

    def test_active_keywords_match(self):
        for kw in ["活泼", "调皮", "贪吃", "琪亚娜", "银狼"]:
            lp = LayeredPersonality(expression_layer=kw)
            cfg = AgentConfig(layered_personality=lp)
            personality = self._get_personality(cfg)
            assert kw in personality, f"关键词 {kw} 应在 personality 中"

    def test_no_match_quiet_personality(self):
        lp = LayeredPersonality(expression_layer="安静沉稳")
        cfg = AgentConfig(layered_personality=lp)
        personality = self._get_personality(cfg)
        assert not any(kw in personality for kw in ["活泼", "调皮", "贪吃", "琪亚娜", "银狼"])

    def test_no_layered_personality(self):
        cfg = AgentConfig(layered_personality=None)
        personality = self._get_personality(cfg)
        assert personality == ""

    def test_empty_expression_layer(self):
        lp = LayeredPersonality(expression_layer="")
        cfg = AgentConfig(layered_personality=lp)
        personality = self._get_personality(cfg)
        assert personality == ""

    def test_case_insensitive(self):
        lp = LayeredPersonality(expression_layer="活波")
        cfg = AgentConfig(layered_personality=lp)
        personality = self._get_personality(cfg)
        assert personality == "活波"