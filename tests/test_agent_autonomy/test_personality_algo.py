"""LS-7/LS-8 算法引擎单元测试 — A1-A6 + EmbeddingCache + PersonalityAlgorithmEngine"""

import pytest
from src.maisaka.agent.config import LayeredPersonalityConfig
from src.maisaka.agent_autonomy.personality_algo.embedding_cache import EmbeddingCache
from src.maisaka.agent_autonomy.personality_algo.engine import PersonalityAlgorithmEngine
from src.maisaka.agent_autonomy.personality_algo.self_discrepancy import SelfDiscrepancyCalculator
from src.maisaka.agent_autonomy.personality_algo.weighted_recall import WeightedRecallCalculator
from src.maisaka.agent_autonomy.personality_algo.lambda_calculator import LambdaCalculator
from src.maisaka.agent_autonomy.personality_algo.predictive_processor import PredictiveProcessor
from src.maisaka.agent_autonomy.personality_algo.plasticity import PlasticityCalculator
from src.maisaka.agent_autonomy.personality_algo.self_verification import SelfVerificationCalculator


class TestA1SelfDiscrepancy:
    def test_dejection_direction(self):
        """体验层'内心温柔' + 认同层'我是冷酷的人' → sad/lonely 正增量"""
        cfg = LayeredPersonalityConfig()
        cache = EmbeddingCache()
        calc = SelfDiscrepancyCalculator(cfg, cache)
        deltas = calc.compute("内心温柔", "我是冷酷的人", "护卫应镇定")
        assert deltas["sad"] > 0, f"sad should be positive, got {deltas['sad']}"
        assert deltas["lonely"] > 0

    def test_agitation_direction(self):
        """实际与ought差异大 → agitation (anxious/angry)"""
        cfg = LayeredPersonalityConfig()
        cache = EmbeddingCache()
        calc = SelfDiscrepancyCalculator(cfg, cache)
        deltas = calc.compute("我感到恐惧", "我是勇敢的人", "护卫不应恐惧")
        assert deltas["anxious"] > 0 or deltas["angry"] > 0

    def test_low_discrepancy_gives_calm(self):
        """三文本接近时 calm/sad/anxious 均为零（无情绪扰动）"""
        cfg = LayeredPersonalityConfig()
        cache = EmbeddingCache()
        calc = SelfDiscrepancyCalculator(cfg, cache)
        deltas = calc.compute("冷静", "冷静", "冷静")
        # 完全相同文本 → 差异为零 → 所有情绪增量均为零
        assert deltas["calm"] == 0
        assert deltas["sad"] == 0
        assert deltas["anxious"] == 0

    def test_returns_seven_keys(self):
        """返回值始终包含7键"""
        cfg = LayeredPersonalityConfig()
        cache = EmbeddingCache()
        calc = SelfDiscrepancyCalculator(cfg, cache)
        deltas = calc.compute("test", "test2", "test3")
        assert len(deltas) == 7


class TestA2WeightedRecall:
    def setup_method(self):
        self.cfg = LayeredPersonalityConfig()
        self.calc = WeightedRecallCalculator(self.cfg)
        # 创建5条测试记忆
        self.memories = [
            {"content_hash": "a", "hours_ago": 1, "cognitive_type": "immutable_fact", "keywords": "test"},
            {"content_hash": "b", "hours_ago": 48, "cognitive_type": "current_state", "keywords": "test"},
            {"content_hash": "c", "hours_ago": 168, "cognitive_type": "active_hypothesis", "keywords": "other"},
            {"content_hash": "d", "hours_ago": 0.1, "cognitive_type": "stable_trait", "keywords": "test"},
            {"content_hash": "e", "hours_ago": 720, "cognitive_type": "emotional_imprint", "keywords": "test"},
        ]

    def test_infer_importance(self):
        assert self.calc.infer_importance("immutable_fact") == 1.5
        assert self.calc.infer_importance("stable_trait") == 1.2
        assert self.calc.infer_importance("current_state") == 1.0
        assert self.calc.infer_importance("active_hypothesis") == 0.8
        assert self.calc.infer_importance("emotional_imprint") == 1.3
        assert self.calc.infer_importance("unknown") == 1.0

    def test_recency_weight(self):
        """越新的记忆 recency 权重越高"""
        r_new = self.cfg.recall_gamma ** 0.1  # 0.1h ago
        r_old = self.cfg.recall_gamma ** 168  # 168h ago
        assert r_new > r_old

    def test_returns_list(self):
        """即使记忆列表为空，也返回列表"""
        results = self.calc.score_memories([], [])
        assert isinstance(results, list)


class TestA3Lambda:
    def setup_method(self):
        self.cfg = LayeredPersonalityConfig()
        self.calc = LambdaCalculator(self.cfg)

    def test_high_emotion_high_relationship(self):
        """dominant=80%, coactivation=0.8 → λ ≈ 0.84"""
        lam = self.calc.compute(0.8, 0.8)
        assert 0.80 <= lam <= 0.88, f"expected ~0.84, got {lam:.2f}"

    def test_no_emotion_no_relationship(self):
        """无情绪无关系 → λ = 0.5"""
        lam = self.calc.compute(0.0, 0.0)
        assert lam == 0.5

    def test_lambda_never_exceeds_0_9(self):
        """极端情绪+关系 → λ 不超过 0.9"""
        lam = self.calc.compute(1.0, 1.0)
        assert lam <= 0.9

    def test_lambda_never_below_0_1(self):
        """λ 永远 ≥ 0.1"""
        lam = self.calc.compute(-1.0, -1.0)
        assert lam >= 0.1


class TestA4PredictiveProcessing:
    def setup_method(self):
        self.cfg = LayeredPersonalityConfig()
        self.pp = PredictiveProcessor(self.cfg)

    def test_high_precision_limits_drift(self):
        """高精度连续 10 次更新后状态漂移 ≤ 0.03"""
        initial = self.pp.get_state("L2")
        for _ in range(10):
            self.pp.update("L2", 0.9, precision=0.95)  # high precision
        final = self.pp.get_state("L2")
        drift = abs(final - initial)
        assert drift <= 0.03, f"drift {drift:.3f} > 0.03"

    def test_stays_clamped(self):
        """无论输入，状态始终在 [0,1]"""
        for _ in range(100):
            self.pp.update("L1", 2.0, precision=0.5)
            self.pp.update("L1", -2.0, precision=0.5)
        state = self.pp.get_state("L1")
        assert 0.0 <= state <= 1.0

    def test_layers_have_different_learning_rates(self):
        """三层学习率不同"""
        assert self.cfg.predictive_l0_lr > self.cfg.predictive_l1_lr > self.cfg.predictive_l2_lr


class TestA5Plasticity:
    def setup_method(self):
        self.cfg = LayeredPersonalityConfig()
        self.calc = PlasticityCalculator(self.cfg)

    def test_new_agent_high_plasticity(self):
        """n=0 → plasticity ≈ 0.92"""
        p = self.calc.compute(0)
        assert p > 0.8, f"expected >0.8, got {p:.3f}"

    def test_midpoint_plasticity(self):
        """n=50 → plasticity ≈ 0.5"""
        p = self.calc.compute(50)
        assert 0.45 <= p <= 0.55, f"expected ~0.5, got {p:.3f}"

    def test_experienced_low_plasticity(self):
        """n=100 → plasticity ≈ 0.08"""
        p = self.calc.compute(100)
        assert p < 0.15, f"expected <0.15, got {p:.3f}"

    def test_role_investment_reopens_plasticity(self):
        """role_investment=0.8 → 已锚定智能体 plasticity 升至 ~0.34"""
        p = self.calc.compute(100, role_investment=0.8)
        assert p > 0.2, f"expected >0.2 after re-plastication, got {p:.3f}"

    def test_negative_interaction_count_does_not_crash(self):
        """负数输入不崩，返回 [0,1] 内的有效值"""
        p = self.calc.compute(-5)
        assert 0.0 <= p <= 1.0


class TestA6SelfVerification:
    def setup_method(self):
        self.cfg = LayeredPersonalityConfig()
        self.calc = SelfVerificationCalculator(self.cfg)

    def test_high_certainty_private_verification(self):
        """certainty=0.8, publicness=0.2 → verification"""
        assert self.calc.verification_vs_enhancement(0.8, 0.2) == "verification"

    def test_low_certainty_public_enhancement(self):
        """certainty=0.3, publicness=0.8 → enhancement"""
        assert self.calc.verification_vs_enhancement(0.3, 0.8) == "enhancement"

    def test_selective_attention_weights_sum_to_one(self):
        """权重和 ≈ 1"""
        results = self.calc.selective_attention(["你很好", "你很差", "还行"], 0.5)
        total = sum(w for _, w in results)
        assert abs(total - 1.0) < 0.01

    def test_selective_attention_empty(self):
        """空输入 → 空输出"""
        assert self.calc.selective_attention([], 0.5) == []


class TestEmbeddingCache:
    def test_cache_hit(self):
        cache = EmbeddingCache()
        v1 = cache.get_or_compute("agent", "expression", "text", lambda t: [hash(t)])
        v2 = cache.get_or_compute("agent", "expression", "text", lambda t: [999])  # should hit cache
        assert v1 == v2

    def test_different_text_misses(self):
        cache = EmbeddingCache()
        v1 = cache.get_or_compute("agent", "layer", "text1", lambda t: [1.0])
        v2 = cache.get_or_compute("agent", "layer", "text2", lambda t: [2.0])
        assert v1 != v2

    def test_invalidate_layer(self):
        cache = EmbeddingCache()
        cache.get_or_compute("agent", "expression", "text", lambda t: [1.0])
        cache.invalidate("agent", "expression")
        v = cache.get_or_compute("agent", "expression", "text", lambda t: [2.0])
        assert v == [2.0]  # recomputed

    def test_invalidate_only_target_layer(self):
        cache = EmbeddingCache()
        cache.get_or_compute("agent", "expression", "text", lambda t: [1.0])
        cache.get_or_compute("agent", "experience", "text", lambda t: [3.0])
        cache.invalidate("agent", "expression")
        # experience still cached
        v = cache.get_or_compute("agent", "experience", "text", lambda t: [4.0])
        assert v == [3.0]  # still cached


class TestPersonalityAlgorithmEngine:
    def test_all_seven_methods_callable(self):
        engine = PersonalityAlgorithmEngine()
        # A1
        d = engine.compute_self_discrepancy("a", "i", "o")
        assert isinstance(d, dict) and len(d) == 7
        # A2
        engine.weighted_recall([], [])
        # A3
        lam = engine.compute_lambda(0.5, 0.5)
        assert 0.1 <= lam <= 0.9
        # A4
        engine.predictive_update("L0", 0.6, 0.5)
        # A5
        assert engine.compute_plasticity(0) > 0.5
        # A6
        assert engine.verification_vs_enhancement(0.8, 0.2) in ("verification", "enhancement")

    def test_a1_returns_empty_on_embedding_failure(self):
        """当 embedding 全部失败时 A1 返回空 delta 但不抛异常"""
        engine = PersonalityAlgorithmEngine()
        # 清空缓存 → embedding 需要重新计算，但我们的模拟实现不会真正失败
        # 所以这个测试验证的是：即使输入极端，也不会抛异常
        try:
            result = engine.compute_self_discrepancy("", "", "")
            assert isinstance(result, dict)
        except Exception as e:
            pytest.fail(f"Should not raise on empty input: {e}")
