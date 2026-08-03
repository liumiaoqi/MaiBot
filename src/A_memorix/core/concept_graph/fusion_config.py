"""FusionConfig — 融合配置（MF-M-002，R03+R04 修正）。

仅提供 stage 属性（无 enabled——stage=FUSION_OFF 等价于原 enabled=False）。
取值：FUSION_OFF / FUSION_WRITE / FUSION_FULL。
"""

from typing import Any, Mapping, Optional

_FUSION_STAGES = ("fusion_off", "fusion_write", "fusion_full")


class FusionConfig:
    """融合配置读取（渐进启用开关）。"""

    def __init__(self, config: Optional[Mapping[str, Any]] = None) -> None:
        self._config = config or {}

    @property
    def stage(self) -> str:
        """融合阶段（memory_fusion.stage，默认 FUSION_OFF）。"""
        raw = str(self._config.get("stage", "fusion_off") or "fusion_off").strip().lower()
        if raw in _FUSION_STAGES:
            return raw
        return "fusion_off"

    @property
    def spread_depth(self) -> int:
        """扩散深度上限（memory_fusion.spread_depth，默认 3）。"""
        return max(1, int(self._config.get("spread_depth", 3) or 3))

    @property
    def score_alpha(self) -> float:
        """评分归一化 alpha（memory_fusion.score_alpha，默认 0.5）。"""
        return max(0.0, min(1.0, float(self._config.get("score_alpha", 0.5) or 0.5)))

    @property
    def write_lock_timeout(self) -> float:
        """写入锁超时秒数（memory_fusion.write_lock_timeout，默认 5.0）。"""
        return max(0.1, float(self._config.get("write_lock_timeout", 5.0) or 5.0))

    def is_full(self) -> bool:
        """FUSION_FULL（检索+画像+写入全融合）。"""
        return self.stage == "fusion_full"

    def is_write_enabled(self) -> bool:
        """写入融合启用（FUSION_WRITE 或 FUSION_FULL）。"""
        return self.stage in ("fusion_write", "fusion_full")
