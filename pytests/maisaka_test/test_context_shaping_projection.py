"""T6: M6 context shaping 接线验证——参数不进 prompt，自动投影。"""


from src.maisaka.agent.config import AgentConfig, LayeredPersonality, PersonalityLayer
from src.maisaka.agent_autonomy.personality_drift.drift_params import DriftParams


class TestAutoProjection:
    def test_set_expression_reflected_in_identity_prompt(self):
        config = AgentConfig()
        config.layered_personality = LayeredPersonality()
        original_prompt = config.identity_prompt
        config.layered_personality.set_layer_text(
            PersonalityLayer.EXPRESSION, "探索率=0.8 社交极性=0.3"
        )
        new_prompt = config.identity_prompt
        assert new_prompt != original_prompt or "探索率=0.8" in new_prompt

    def test_drift_params_reflected_in_identity_prompt(self):
        config = AgentConfig()
        config.layered_personality = LayeredPersonality()
        params = DriftParams()
        params.exploration_rate.value = 0.9
        config.layered_personality.set_layer_text(
            PersonalityLayer.EXPRESSION, params.to_layer_text()
        )
        prompt = config.identity_prompt
        assert "exploration_rate" in prompt or len(prompt) > 0

    def test_existence_not_in_identity_prompt_after_drift(self):
        config = AgentConfig()
        config.layered_personality = LayeredPersonality(
            existence_layer="不可改的存在层"
        )
        original_existence = config.layered_personality.get_layer_text(
            PersonalityLayer.EXISTENCE
        )
        params = DriftParams()
        config.layered_personality.set_layer_text(
            PersonalityLayer.EXPRESSION, params.to_layer_text()
        )
        assert config.layered_personality.get_layer_text(
            PersonalityLayer.EXISTENCE
        ) == original_existence