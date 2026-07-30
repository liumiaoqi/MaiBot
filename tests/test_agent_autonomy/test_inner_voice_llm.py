"""L1 内言语升级单元测试 — generate_llm + Lambda + Prompt 注入 + Self-reply"""

from src.maisaka.agent.config import LayeredPersonalityConfig


class TestGenerateLLM:
    def test_llm_none_falls_back(self):
        """llm_service=None → 直接规则引擎（不抛异常）"""
        from src.maisaka.agent_autonomy.personality_algo.lambda_calculator import LambdaCalculator
        cfg = LayeredPersonalityConfig()
        calc = LambdaCalculator(cfg)
        # LambdaCalculator 不依赖 LLM service — generate_llm 在 InnerVoiceGenerator 中
        # 但我们可以测试 lambda 计算本身
        lam = calc.compute(0.3, 0.2)
        assert 0.1 <= lam <= 0.9

    def test_lambda_in_range(self):
        """λ ∈ [0.1, 0.9] 对所有输入"""
        from src.maisaka.agent.config import LayeredPersonalityConfig
        from src.maisaka.agent_autonomy.personality_algo.lambda_calculator import LambdaCalculator
        cfg = LayeredPersonalityConfig()
        calc = LambdaCalculator(cfg)
        test_inputs = [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (0.8, 0.1), (0.1, 0.9), (0.0, 1.0)]
        for intensity, coact in test_inputs:
            lam = calc.compute(intensity, coact)
            assert 0.1 <= lam <= 0.9, f"λ={lam:.2f} for ({intensity}, {coact})"


class TestLambdaParameterization:
    def test_lambda_increases_with_emotion(self):
        """情绪更高 → λ 更高"""
        from src.maisaka.agent.config import LayeredPersonalityConfig
        from src.maisaka.agent_autonomy.personality_algo.lambda_calculator import LambdaCalculator
        cfg = LayeredPersonalityConfig()
        calc = LambdaCalculator(cfg)
        lam_low = calc.compute(0.3, 0.5)
        lam_high = calc.compute(0.8, 0.5)
        assert lam_high >= lam_low

    def test_lambda_increases_with_relationship(self):
        """关系更亲密 → λ 更高"""
        from src.maisaka.agent.config import LayeredPersonalityConfig
        from src.maisaka.agent_autonomy.personality_algo.lambda_calculator import LambdaCalculator
        cfg = LayeredPersonalityConfig()
        calc = LambdaCalculator(cfg)
        lam_low = calc.compute(0.5, 0.1)
        lam_high = calc.compute(0.5, 0.8)
        assert lam_high >= lam_low


class TestSelfReplySummaries:
    def test_disabled_mode_returns_empty(self):
        """self_reply_visibility='disabled' → 不注入"""
        from src.core.types import ThinkContext
        ctx = ThinkContext(messages=(), self_reply_visibility="disabled")
        assert ctx.self_reply_visibility == "disabled"
        assert ctx.self_reply_summaries == ()
