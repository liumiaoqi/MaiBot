from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeedbackConfig:
    """反馈纠错配置 — 一次性从配置字典读取，替代 15+ 处 getattr 模式。"""

    enabled: bool = False
    window_hours: float = 12.0
    check_interval_seconds: float = 1800.0
    batch_size: int = 20
    auto_apply_threshold: float = 0.85
    max_messages: int = 30
    prefilter_enabled: bool = True
    paragraph_mark_enabled: bool = True
    paragraph_hard_filter_enabled: bool = True
    profile_refresh_enabled: bool = True
    profile_force_refresh_on_read: bool = True
    episode_rebuild_enabled: bool = True
    episode_query_block_enabled: bool = True
    reconcile_interval_seconds: float = 300.0
    reconcile_batch_size: int = 20

    @classmethod
    def from_config_dict(cls, config: dict[str, Any]) -> FeedbackConfig:
        integration = config.get("integration") if isinstance(config, dict) else None
        if not isinstance(integration, dict):
            return cls()
        return cls(
            enabled=bool(integration.get("feedback_correction_enabled", False)),
            window_hours=max(0.1, float(integration.get("feedback_correction_window_hours", 12.0) or 12.0)),
            check_interval_seconds=float(max(1, int(integration.get("feedback_correction_check_interval_minutes", 30) or 30))) * 60.0,
            batch_size=max(1, int(integration.get("feedback_correction_batch_size", 20) or 20)),
            auto_apply_threshold=min(1.0, max(0.0, float(integration.get("feedback_correction_auto_apply_threshold", 0.85) or 0.85))),
            max_messages=max(1, int(integration.get("feedback_correction_max_feedback_messages", 30) or 30)),
            prefilter_enabled=bool(integration.get("feedback_correction_prefilter_enabled", True)),
            paragraph_mark_enabled=bool(integration.get("feedback_correction_paragraph_mark_enabled", True)),
            paragraph_hard_filter_enabled=bool(integration.get("feedback_correction_paragraph_hard_filter_enabled", True)),
            profile_refresh_enabled=bool(integration.get("feedback_correction_profile_refresh_enabled", True)),
            profile_force_refresh_on_read=bool(integration.get("feedback_correction_profile_force_refresh_on_read", True)),
            episode_rebuild_enabled=bool(integration.get("feedback_correction_episode_rebuild_enabled", True)),
            episode_query_block_enabled=bool(integration.get("feedback_correction_episode_query_block_enabled", True)),
            reconcile_interval_seconds=float(max(1, int(integration.get("feedback_correction_reconcile_interval_minutes", 5) or 5))) * 60.0,
            reconcile_batch_size=max(1, int(integration.get("feedback_correction_reconcile_batch_size", 20) or 20)),
        )

    @classmethod
    def from_global_config(cls) -> FeedbackConfig:
        from src.config.config import global_config
        memory_cfg = global_config.a_memorix.integration
        return cls(
            enabled=bool(getattr(memory_cfg, "feedback_correction_enabled", False)),
            window_hours=max(0.1, float(getattr(memory_cfg, "feedback_correction_window_hours", 12.0) or 12.0)),
            check_interval_seconds=float(max(1, int(getattr(memory_cfg, "feedback_correction_check_interval_minutes", 30) or 30))) * 60.0,
            batch_size=max(1, int(getattr(memory_cfg, "feedback_correction_batch_size", 20) or 20)),
            auto_apply_threshold=min(1.0, max(0.0, float(getattr(memory_cfg, "feedback_correction_auto_apply_threshold", 0.85) or 0.85))),
            max_messages=max(1, int(getattr(memory_cfg, "feedback_correction_max_feedback_messages", 30) or 30)),
            prefilter_enabled=bool(getattr(memory_cfg, "feedback_correction_prefilter_enabled", True)),
            paragraph_mark_enabled=bool(getattr(memory_cfg, "feedback_correction_paragraph_mark_enabled", True)),
            paragraph_hard_filter_enabled=bool(getattr(memory_cfg, "feedback_correction_paragraph_hard_filter_enabled", True)),
            profile_refresh_enabled=bool(getattr(memory_cfg, "feedback_correction_profile_refresh_enabled", True)),
            profile_force_refresh_on_read=bool(getattr(memory_cfg, "feedback_correction_profile_force_refresh_on_read", True)),
            episode_rebuild_enabled=bool(getattr(memory_cfg, "feedback_correction_episode_rebuild_enabled", True)),
            episode_query_block_enabled=bool(getattr(memory_cfg, "feedback_correction_episode_query_block_enabled", True)),
            reconcile_interval_seconds=float(max(1, int(getattr(memory_cfg, "feedback_correction_reconcile_interval_minutes", 5) or 5))) * 60.0,
            reconcile_batch_size=max(1, int(getattr(memory_cfg, "feedback_correction_reconcile_batch_size", 20) or 20)),
        )

    @property
    def window_label(self) -> str:
        if self.window_hours >= 24:
            return f"{self.window_hours / 24:.1f}天"
        return f"{self.window_hours:.1f}小时"
