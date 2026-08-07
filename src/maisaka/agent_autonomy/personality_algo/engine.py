"""LS-7/LS-8 算法门面 — 统一入口，代理 A1-A6。所有异常返回安全默认值"""

from typing import Any, Optional

from src.common.logger import get_logger

from .embedding_cache import EmbeddingCache
from .self_discrepancy import SelfDiscrepancyCalculator
from .weighted_recall import WeightedRecallCalculator
from .lambda_calculator import LambdaCalculator
from .predictive_processor import PredictiveProcessor
from .plasticity import PlasticityCalculator
from .self_verification import SelfVerificationCalculator

logger = get_logger(__name__)


class PersonalityAlgorithmEngine:
    """LS-7/LS-8 算法门面 — 统一入口，代理 A1-A6。

    所有公开方法在异常时返回安全默认值，不向调用方传播异常。
    """

    def __init__(self, config=None, embedding_cache: Optional[EmbeddingCache] = None) -> None:
        if config is None:
            from src.maisaka.agent.config import LayeredPersonalityConfig
            config = LayeredPersonalityConfig()
        self._config = config

        if embedding_cache is None:
            embedding_cache = EmbeddingCache()
        self.embedding_cache = embedding_cache

        self.a1 = SelfDiscrepancyCalculator(self._config, self.embedding_cache)
        self.a2 = WeightedRecallCalculator(self._config)
        self.a3 = LambdaCalculator(self._config)
        self.a4 = PredictiveProcessor(self._config)
        self.a5 = PlasticityCalculator(self._config)
        self.a6 = SelfVerificationCalculator(self._config)

    # ------------------------------------------------------------------
    # A1: 自我差异
    # ------------------------------------------------------------------

    def compute_self_discrepancy(
        self,
        actual_text: str,
        ideal_text: str,
        ought_text: str,
        context: str = "",
    ) -> dict[str, float]:
        """A1: actual/ideal/ought 差异 → 7 种情绪增量"""
        try:
            return self.a1.compute(actual_text, ideal_text, ought_text, context)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'A1 self_discrepancy failed', exception=exc)
            logger.warning(f"A1 self_discrepancy failed: {exc}")
            return {}

    # ------------------------------------------------------------------
    # A2: 加权记忆检索
    # ------------------------------------------------------------------

    def weighted_recall(
        self,
        query_embedding: list[float],
        memories: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """A2: recency × importance × relevance 加权排序"""
        try:
            return self.a2.score_memories(query_embedding, memories)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'A2 weighted_recall failed', exception=exc)
            logger.warning(f"A2 weighted_recall failed: {exc}")
            return memories

    # ------------------------------------------------------------------
    # A3: λ 参数
    # ------------------------------------------------------------------

    def compute_lambda(self, emotion_intensity: float, coactivation_strength: float) -> float:
        """A3: λ 参数 — 控制 inner_voice 对 L2 的影响权重"""
        try:
            return self.a3.compute(emotion_intensity, coactivation_strength)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'A3 lambda compute failed', exception=exc)
            logger.warning(f"A3 lambda compute failed: {exc}")
            return 0.5

    # ------------------------------------------------------------------
    # A4: 预测处理
    # ------------------------------------------------------------------

    def predictive_update(
        self,
        layer_name: str,
        observation: float,
        precision: float = 0.5,
    ) -> dict[str, Any]:
        """A4: 感知更新 — 更新指定层状态"""
        try:
            return self.a4.update(layer_name, observation, precision)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'A4 predictive_update failed', exception=exc)
            logger.warning(f"A4 predictive_update failed: {exc}")
            return {
                "layer": layer_name,
                "error": 0.0,
                "update_amount": 0.0,
                "new_state": 0.5,
            }

    def get_predictive_state(self, layer_name: str) -> float:
        """获取预测处理器中指定层的当前状态"""
        try:
            return self.a4.get_state(layer_name)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'A4 get_state failed', exception=exc)
            logger.warning(f"A4 get_state failed: {exc}")
            return 0.5

    def get_predictive_prediction(self, layer_name: str) -> float:
        """获取预测处理器中指定层的当前预测值"""
        try:
            return self.a4.get_prediction(layer_name)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'A4 get_prediction failed', exception=exc)
            logger.warning(f"A4 get_prediction failed: {exc}")
            return 0.5

    def reset_predictive_layers(self) -> None:
        """重置所有预测处理层到默认状态"""
        try:
            self.a4.reset()
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'A4 reset failed', exception=exc)
            logger.warning(f"A4 reset failed: {exc}")

    # ------------------------------------------------------------------
    # A5: 可塑性
    # ------------------------------------------------------------------

    def compute_plasticity(self, interaction_count: int, role_investment: float = 0.0) -> float:
        """A5: 计算当前可塑性"""
        try:
            return self.a5.compute(interaction_count, role_investment)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'A5 plasticity failed', exception=exc)
            logger.warning(f"A5 plasticity failed: {exc}")
            return 0.5

    # ------------------------------------------------------------------
    # A6: 自我验证
    # ------------------------------------------------------------------

    def verification_vs_enhancement(self, self_certainty: float, context_publicness: float) -> str:
        """A6: 判断当前策略是 verification 还是 enhancement"""
        try:
            return self.a6.verification_vs_enhancement(self_certainty, context_publicness)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'A6 verification_vs_enhancement failed', exception=exc)
            logger.warning(f"A6 verification_vs_enhancement failed: {exc}")
            return "verification"

    def selective_attention(
        self,
        incoming_feedback: list[str],
        self_concept_hash: float,
    ) -> list[tuple[str, float]]:
        """A6: 对验证性信息分配更高权重"""
        try:
            return self.a6.selective_attention(incoming_feedback, self_concept_hash)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'A6 selective_attention failed', exception=exc)
            logger.warning(f"A6 selective_attention failed: {exc}")
            if not incoming_feedback:
                return []
            w = 1.0 / len(incoming_feedback)
            return [(fb, w) for fb in incoming_feedback]

    # ------------------------------------------------------------------
    # 便捷方法
    # ------------------------------------------------------------------

    def invalidate_embedding_cache(self, agent_id: str, layer: str) -> None:
        """使指定 agent+layer 的 embedding 缓存失效"""
        try:
            self.embedding_cache.invalidate(agent_id, layer)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'Embedding cache invalidate failed', exception=exc)
            logger.warning(f"Embedding cache invalidate failed: {exc}")

    def clear_embedding_cache(self) -> None:
        """清空所有 embedding 缓存"""
        try:
            self.embedding_cache.clear()
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'Embedding cache clear failed', exception=exc)
            logger.warning(f"Embedding cache clear failed: {exc}")
