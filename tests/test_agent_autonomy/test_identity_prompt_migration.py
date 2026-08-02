"""ZG 人格迁移测试 — identity_prompt 属性 + get_identity_summary 迁移验证"""


from src.maisaka.agent.config import AgentConfig, LayeredPersonality


class TestIdentityPromptLayered:
    """identity_prompt 从 layered_personality 四层组合"""

    def test_full_layers(self):
        lp = LayeredPersonality(
            expression_layer="外显行为",
            experience_layer="内心感受",
            identity_layer="自我认知",
            self_constraints="绝不撒谎",
        )
        cfg = AgentConfig(layered_personality=lp)
        result = cfg.identity_prompt
        assert "外显行为" in result
        assert "内心感受" in result
        assert "自我认知" in result
        assert "自我约束：绝不撒谎" in result

    def test_partial_layers_skip_empty(self):
        lp = LayeredPersonality(
            expression_layer="活泼",
            experience_layer="",
            identity_layer="认同",
            self_constraints="",
        )
        cfg = AgentConfig(layered_personality=lp)
        result = cfg.identity_prompt
        assert "活泼" in result
        assert "认同" in result
        assert "内心感受" not in result
        assert "自我约束" not in result

    def test_all_empty_layers_returns_empty(self):
        lp = LayeredPersonality()
        cfg = AgentConfig(layered_personality=lp)
        assert cfg.identity_prompt == ""

    def test_constraints_prefix(self):
        lp = LayeredPersonality(self_constraints="不伤害他人")
        cfg = AgentConfig(layered_personality=lp)
        assert cfg.identity_prompt == "自我约束：不伤害他人"


class TestIdentityPromptFallback:
    """identity_prompt fallback 到 deprecated personality"""

    def test_fallback_when_none(self):
        cfg = AgentConfig(personality="旧人格文本", layered_personality=None)
        assert cfg.identity_prompt == "旧人格文本"

    def test_fallback_empty_personality(self):
        cfg = AgentConfig(personality="", layered_personality=None)
        assert cfg.identity_prompt == ""

    def test_layered_takes_priority(self):
        lp = LayeredPersonality(expression_layer="新人格")
        cfg = AgentConfig(personality="旧人格", layered_personality=lp)
        assert cfg.identity_prompt == "新人格"


class TestGetIdentitySummaryMigration:
    """get_identity_summary 从 expression_layer[:80] 生成摘要"""

    def test_expression_layer_summary(self):
        lp = LayeredPersonality(expression_layer="活泼调皮的银狼")
        cfg = AgentConfig(display_name="银狼", layered_personality=lp)
        summary = cfg.get_identity_summary()
        assert "活泼调皮的银狼" in summary

    def test_expression_layer_truncated(self):
        long_text = "a" * 120
        lp = LayeredPersonality(expression_layer=long_text)
        cfg = AgentConfig(layered_personality=lp)
        summary = cfg.get_identity_summary()
        for part in summary.split("；"):
            if part.startswith("a"):
                assert len(part) <= 80

    def test_no_layered_personality(self):
        cfg = AgentConfig(display_name="银狼", layered_personality=None)
        summary = cfg.get_identity_summary()
        assert "银狼" in summary
        assert "无性格描述" in summary

    def test_empty_expression_layer(self):
        lp = LayeredPersonality(expression_layer="")
        cfg = AgentConfig(display_name="银狼", layered_personality=lp)
        summary = cfg.get_identity_summary()
        assert "银狼" in summary
        assert "无性格描述" in summary

    def test_summary_with_relationships(self):
        from src.maisaka.agent.config import InternalRelationship

        lp = LayeredPersonality(expression_layer="活泼")
        cfg = AgentConfig(
            layered_personality=lp,
            internal_relationships=[
                InternalRelationship(target_agent_id="a", relationship_type="friend")
            ],
        )
        summary = cfg.get_identity_summary()
        assert "活泼" in summary
        assert "关系" in summary

    def test_summary_max_200_chars(self):
        lp = LayeredPersonality(expression_layer="x" * 300)
        cfg = AgentConfig(layered_personality=lp)
        summary = cfg.get_identity_summary()
        assert len(summary) <= 200