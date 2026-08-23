"""ZG-N5 压缩升级——策略配置解析与校验。

对标 dsh compaction-basic/src/types.ts CompactionPolicyConfig。
配置词汇：thresholdRatio/retainRatio/retainTokens/compactionRetries/auto/maxOverflowRetries。
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .types import ModelRoute


class ConfigValidationError(Exception):
    """配置校验异常。"""


@dataclass(frozen=True)
class CompactionPolicyConfig:
    """压缩策略配置（原始配置词汇，retain_ratio 与 retain_tokens 互斥）。"""

    threshold_ratio: float = 0.8
    retain_ratio: Optional[float] = 0.16
    retain_tokens: Optional[int] = None
    compaction_retries: int = 1
    max_overflow_retries: int = 1
    auto: bool = True
    summarization_provider: Optional[str] = None
    summarization_model: Optional[str] = None
    max_tokens: int = 8192


@dataclass(frozen=True)
class ResolvedConfig:
    """校验后的不可变配置——retain_ratio 与 retain_tokens 恰一设置。"""

    threshold_ratio: float
    retain_ratio: Optional[float]
    retain_tokens: Optional[int]
    compaction_retries: int
    max_overflow_retries: int
    auto: bool
    summarization_provider: Optional[str]
    summarization_model: Optional[str]
    max_tokens: int

    def to_model_route(self, fallback_provider: str, fallback_model: str) -> ModelRoute:
        """解析为 ModelRoute——优先使用 summarization_provider/model，否则 fallback。"""
        return ModelRoute(
            provider=self.summarization_provider or fallback_provider,
            model=self.summarization_model or fallback_model,
            max_tokens=self.max_tokens,
        )


def resolve_compaction_config(
    cfg: Callable[[str, Any], Any],
) -> ResolvedConfig:
    """从应用配置 memory.compaction.* 读取并解析为 ResolvedConfig。

    Args:
        cfg: 配置读取函数（kernel._cfg），签名 (key, default) -> value

    Returns:
        校验后的 ResolvedConfig

    Raises:
        ConfigValidationError: retain_ratio 与 retain_tokens 同时设置，或 retain_tokens >= 阈值
    """
    raw = cfg("memory.compaction", {}) or {}
    if not isinstance(raw, dict):
        raw = {}

    threshold_ratio = float(raw.get("threshold_ratio", 0.8) or 0.8)
    retain_ratio_raw = raw.get("retain_ratio", None)
    retain_tokens_raw = raw.get("retain_tokens", None)
    retain_ratio = float(retain_ratio_raw) if retain_ratio_raw is not None else None
    retain_tokens = int(retain_tokens_raw) if retain_tokens_raw is not None else None
    compaction_retries = int(raw.get("compaction_retries", 1) or 1)
    max_overflow_retries = int(raw.get("max_overflow_retries", 1) or 1)
    auto = bool(raw.get("auto", True))
    summarization_provider = raw.get("summarization_provider", None)
    summarization_model = raw.get("summarization_model", None)
    max_tokens = int(raw.get("max_tokens", 8192) or 8192)

    # 互斥校验：retain_ratio 与 retain_tokens 不可同时设置
    if retain_ratio is not None and retain_tokens is not None:
        raise ConfigValidationError(
            "retain_ratio 与 retain_tokens 不可同时设置——请仅设置其一"
        )

    # 默认 retain_ratio=0.16（两者都未设置时）
    if retain_ratio is None and retain_tokens is None:
        retain_ratio = 0.16

    # 范围校验：retain_tokens 必须低于阈值
    if retain_tokens is not None:
        context_window = int(cfg("memory.context_window", 32768) or 32768)
        threshold_tokens = int(threshold_ratio * context_window)
        if retain_tokens >= threshold_tokens:
            raise ConfigValidationError(
                f"retain_tokens ({retain_tokens}) 必须低于阈值 ({threshold_tokens})"
            )

    # 范围校验：threshold_ratio 在 (0, 1) 区间
    if not (0.0 < threshold_ratio < 1.0):
        raise ConfigValidationError(
            f"threshold_ratio ({threshold_ratio}) 必须在 (0, 1) 区间"
        )

    # 范围校验：retain_ratio 在 (0, 1) 区间
    if retain_ratio is not None and not (0.0 < retain_ratio < 1.0):
        raise ConfigValidationError(
            f"retain_ratio ({retain_ratio}) 必须在 (0, 1) 区间"
        )

    return ResolvedConfig(
        threshold_ratio=threshold_ratio,
        retain_ratio=retain_ratio,
        retain_tokens=retain_tokens,
        compaction_retries=compaction_retries,
        max_overflow_retries=max_overflow_retries,
        auto=auto,
        summarization_provider=summarization_provider,
        summarization_model=summarization_model,
        max_tokens=max_tokens,
    )