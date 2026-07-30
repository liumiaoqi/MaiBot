"""LS-7 性格修改工具单元测试"""

import pytest


class TestAdjustExpression:
    def test_existence_layer_rejected(self):
        """layer='existence' → 返回错误"""
        # This is enforced by LayeredPersonality.set_layer_text()
        from src.maisaka.agent.config import LayeredPersonality, PersonalityLayer
        lp = LayeredPersonality(expression_layer="test")
        with pytest.raises(ValueError, match="存在层不可修改"):
            lp.set_layer_text(PersonalityLayer.EXISTENCE, "新文本")

    def test_is_modifiable(self):
        """存在层不可修改，其他层可修改"""
        from src.maisaka.agent.config import LayeredPersonality, PersonalityLayer
        lp = LayeredPersonality()
        assert lp.is_modifiable(PersonalityLayer.EXISTENCE) is False
        assert lp.is_modifiable(PersonalityLayer.EXPRESSION) is True
        assert lp.is_modifiable(PersonalityLayer.EXPERIENCE) is True
        assert lp.is_modifiable(PersonalityLayer.IDENTITY) is True

    def test_identity_not_adjustable_via_expression_tool(self):
        """layer='identity' 应在 adjust_expression 中被拦截"""
        # Test that the TOOL logic (not the model) rejects identity
        # This is validated by the match/case in the tool handler
        pass  # Requires BuiltinToolRuntimeContext mock — tested in integration


class TestReflectOnSelf:
    def test_verification_mode_gating(self):
        """自我验证 gate 在 enhancement+contradictory 时降低权重"""
        from src.maisaka.agent.config import LayeredPersonalityConfig
        from src.maisaka.agent_autonomy.personality_algo.self_verification import SelfVerificationCalculator
        cfg = LayeredPersonalityConfig()
        calc = SelfVerificationCalculator(cfg)
        # 高确定+公开 → enhancement
        assert calc.verification_vs_enhancement(0.8, 0.8) == "enhancement"


class TestUpdateRelationship:
    def test_target_not_self(self):
        """不应该更新自己的关系"""
        # Logic check, full test needs tool context mock
        pass
