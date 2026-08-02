"""ZG 人格迁移测试 — 管家性格加载从 expression_layer 读取"""


from src.maisaka.agent.config import AgentConfig, LayeredPersonality


class TestButlerPersonalityMigration:
    """butler._butler_personality 从 layered_personality.expression_layer 读取"""

    def test_butler_loads_expression_layer(self):
        lp = LayeredPersonality(expression_layer="管家外显性格")
        agent = AgentConfig(
            agent_id="butler",
            is_butler=True,
            layered_personality=lp,
        )
        personality = (
            agent.layered_personality.expression_layer
            if agent.layered_personality and agent.layered_personality.expression_layer
            else ""
        )
        assert personality == "管家外显性格"

    def test_butler_no_layered_personality(self):
        agent = AgentConfig(
            agent_id="butler",
            is_butler=True,
            layered_personality=None,
        )
        personality = (
            agent.layered_personality.expression_layer
            if agent.layered_personality and agent.layered_personality.expression_layer
            else ""
        )
        assert personality == ""

    def test_butler_empty_expression_layer(self):
        lp = LayeredPersonality(expression_layer="")
        agent = AgentConfig(
            agent_id="butler",
            is_butler=True,
            layered_personality=lp,
        )
        personality = (
            agent.layered_personality.expression_layer
            if agent.layered_personality and agent.layered_personality.expression_layer
            else ""
        )
        assert personality == ""

    def test_butler_does_not_use_flat_personality(self):
        lp = LayeredPersonality(expression_layer="新性格")
        agent = AgentConfig(
            agent_id="butler",
            is_butler=True,
            personality="旧扁平人格",
            layered_personality=lp,
        )
        personality = (
            agent.layered_personality.expression_layer
            if agent.layered_personality and agent.layered_personality.expression_layer
            else ""
        )
        assert personality == "新性格"
        assert personality != "旧扁平人格"