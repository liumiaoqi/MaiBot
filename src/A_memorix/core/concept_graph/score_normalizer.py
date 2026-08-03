"""ScoreNormalizer — 评分空间统一（MF-P3-003）。

扩散分（联想）+ 向量相似度（事实）来自不同量纲，min-max 归一化到 [0,1]
后按 alpha 加权合并——替代 RRF 拼接（MF-P3-002：非 RRF 拼接）。
"""

from typing import Mapping


class ScoreNormalizer:
    """双路评分归一化合并器。"""

    def normalize(
        self,
        *,
        spread_scores: Mapping[str, float],
        vector_scores: Mapping[str, float],
        alpha: float = 0.5,
    ) -> dict[str, float]:
        """归一化并合并两路评分。

        Args:
            spread_scores: 联想扩散分 {concept_id: raw_score}
            vector_scores: 向量相似度 {concept_id: raw_similarity}
            alpha: 扩散分权重（向量分权重 = 1 - alpha）

        Returns:
            {concept_id: fused_score}，值域 [0, 1]
        """
        alpha = max(0.0, min(1.0, alpha))
        spread_norm = self._minmax(spread_scores)
        vector_norm = self._minmax(vector_scores)

        fused: dict[str, float] = {}
        for cid in set(spread_norm) | set(vector_norm):
            s = spread_norm.get(cid, 0.0)
            v = vector_norm.get(cid, 0.0)
            fused[cid] = alpha * s + (1.0 - alpha) * v
        return fused

    @staticmethod
    def _minmax(scores: Mapping[str, float]) -> dict[str, float]:
        """min-max 归一化到 [0,1]（空输入或零方差返回全 0）。"""
        if not scores:
            return {}
        values = [float(v) for v in scores.values()]
        lo, hi = min(values), max(values)
        if hi - lo < 1e-9:
            return {cid: 0.0 for cid in scores}
        return {
            cid: (float(v) - lo) / (hi - lo)
            for cid, v in scores.items()
        }
