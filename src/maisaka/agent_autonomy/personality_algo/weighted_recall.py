"""A2: 加权记忆检索 — 基于 Park 记忆模型，recency × importance × relevance"""

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.maisaka.agent.config import LayeredPersonalityConfig


# 从 cognitive_type 到重要性权重的映射
_COGNITIVE_IMPORTANCE_MAP: dict[str, float] = {
    "immutable_fact": 1.5,
    "stable_trait": 1.2,
    "current_state": 1.0,
    "active_hypothesis": 0.8,
    "emotional_imprint": 1.3,
}


class WeightedRecallCalculator:
    """A2: 加权记忆检索 — recency × importance × relevance

    每条记忆的复合得分：
        score = normalize(recency) + normalize(importance) + normalize(relevance)

    其中：
    - recency = gamma ^ hours_ago（Park 修正指数衰减）
    - importance 由 cognitive_type 推断
    - relevance = cosine_sim(query_embedding, memory_embedding)
    """

    def __init__(self, config: "LayeredPersonalityConfig") -> None:
        self.gamma = config.recall_gamma

    def score_memories(
        self,
        query_embedding: list[float],
        memories: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """计算每条记忆的复合得分并排序。

        memories 中每条记忆需包含：
        - embedding: list[float] — 记忆向量
        - hours_ago: float — 距今小时数
        - cognitive_type: str — 认知类型

        返回排序后的记忆列表，每项额外包含 score 字段。
        """
        if not memories:
            return []

        scored: list[dict[str, Any]] = []
        for mem in memories:
            mem_emb = mem.get("embedding", [])
            hours_ago = float(mem.get("hours_ago", 0))
            cog_type = str(mem.get("cognitive_type", "current_state"))

            recency = self.gamma ** hours_ago
            importance = self.infer_importance(cog_type)
            relevance = _cosine_similarity(query_embedding, mem_emb)

            # 三项各自已在 [0, ~1.5] 范围，简单相加后待外部归一化
            score = recency + importance + relevance
            scored.append({**mem, "score": score, "_recency": recency, "_importance": importance, "_relevance": relevance})

        scored.sort(key=lambda m: m["score"], reverse=True)
        return scored

    @staticmethod
    def infer_importance(cognitive_type: str) -> float:
        """从 cognitive_type 推断重要性权重。

        - immutable_fact: 1.5（不可变事实，最高权重）
        - stable_trait: 1.2（稳定特质）
        - current_state: 1.0（当前状态，基准）
        - active_hypothesis: 0.8（活跃假设，最低权重）
        - emotional_imprint: 1.3（情感印记）
        """
        return _COGNITIVE_IMPORTANCE_MAP.get(cognitive_type, 1.0)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """两个向量的余弦相似度。零向量或空向量返回 0。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for va, vb in zip(a, b, strict=True):
        dot += va * vb
        norm_a += va * va
        norm_b += vb * vb
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))
