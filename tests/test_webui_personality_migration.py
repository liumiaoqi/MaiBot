"""ZG 人格迁移测试 — WebUI 序列化：layered_personality 替代 personality"""

from src.maisaka.agent.config import AgentConfig, LayeredPersonality
from src.webui.schemas.agent import AgentConfigResponse, LayeredPersonalityResponse


class TestWebUISerializationMigration:
    """_config_to_response 输出 layered_personality，不含 personality"""

    def test_layered_personality_serialized(self):
        lp = LayeredPersonality(
            existence_layer="时代世界",
            expression_layer="外显行为",
            experience_layer="内心感受",
            identity_layer="自我认知",
            self_constraints="绝不撒谎",
        )
        config = AgentConfig(agent_id="test", display_name="测试", layered_personality=lp)
        resp = _config_to_response(config)
        assert resp.layered_personality is not None
        assert resp.layered_personality.expression_layer == "外显行为"
        assert resp.layered_personality.existence_layer == "时代世界"
        assert resp.layered_personality.experience_layer == "内心感受"
        assert resp.layered_personality.identity_layer == "自我认知"
        assert resp.layered_personality.self_constraints == "绝不撒谎"

    def test_no_layered_personality(self):
        config = AgentConfig(agent_id="test", display_name="测试", layered_personality=None)
        resp = _config_to_response(config)
        assert resp.layered_personality is None

    def test_no_personality_field(self):
        config = AgentConfig(agent_id="test", display_name="测试")
        resp = _config_to_response(config)
        assert not hasattr(resp, "personality")

    def test_response_model_has_no_personality(self):
        assert "personality" not in AgentConfigResponse.model_fields


def _config_to_response(config: AgentConfig) -> AgentConfigResponse:
    return AgentConfigResponse(
        agent_id=config.agent_id,
        display_name=config.display_name,
        layered_personality=(
            LayeredPersonalityResponse(
                existence_layer=config.layered_personality.existence_layer,
                expression_layer=config.layered_personality.expression_layer,
                experience_layer=config.layered_personality.experience_layer,
                identity_layer=config.layered_personality.identity_layer,
                self_constraints=config.layered_personality.self_constraints,
            )
            if config.layered_personality
            else None
        ),
        reply_style=config.reply_style,
        is_default=config.is_default,
        color=config.color,
        emotion_baseline=config.emotion_baseline,
        emotion_decay_rate=config.emotion_decay_rate,
        relationship_growth_rate=config.relationship_growth_rate,
        talk_value_modifier=config.talk_value_modifier,
        memory_focus_areas=config.memory_focus_areas,
        internal_relationships=[],
        anti_mechanization_rules=config.anti_mechanization_rules,
    )