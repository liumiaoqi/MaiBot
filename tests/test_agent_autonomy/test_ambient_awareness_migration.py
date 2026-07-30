"""ZG 人格迁移测试 — 环境感知从 expression_layer 提取关键词"""

import re

from src.maisaka.agent.config import AgentConfig, LayeredPersonality


class TestAmbientAwarenessMigration:
    """环境感知从 layered_personality.expression_layer 提取中文关键词"""

    def _get_personality(self, agent_config: AgentConfig) -> str:
        return (
            agent_config.layered_personality.expression_layer
            if agent_config.layered_personality and agent_config.layered_personality.expression_layer
            else ""
        )

    def test_extracts_chinese_keywords(self):
        lp = LayeredPersonality(expression_layer="活泼的银狼喜欢游戏")
        cfg = AgentConfig(layered_personality=lp)
        personality = self._get_personality(cfg)
        keywords = set(re.findall(r"[\u4e00-\u9fff]{2,4}", personality))
        assert len(keywords) > 0

    def test_no_layered_personality(self):
        cfg = AgentConfig(layered_personality=None)
        personality = self._get_personality(cfg)
        assert personality == ""

    def test_empty_expression_layer(self):
        lp = LayeredPersonality(expression_layer="")
        cfg = AgentConfig(layered_personality=lp)
        personality = self._get_personality(cfg)
        assert personality == ""
        keywords = set(re.findall(r"[\u4e00-\u9fff]{2,4}", personality))
        assert len(keywords) == 0

    def test_keyword_matching_in_content(self):
        lp = LayeredPersonality(expression_layer="银狼喜欢打游戏")
        cfg = AgentConfig(layered_personality=lp)
        personality = self._get_personality(cfg)
        keywords = set(re.findall(r"[\u4e00-\u9fff]{2,4}", personality))
        content = "今天银狼又打游戏了"
        matched = [kw for kw in keywords if kw in content]
        assert len(matched) > 0