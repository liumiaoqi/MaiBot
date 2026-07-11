from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FuzzyModifyConfig:
    """模糊修改配置 — 一次性从配置字典读取，替代 6 处 getattr 模式。"""

    enabled: bool = True
    auto_execute_enabled: bool = False
    confirm_threshold: float = 0.85
    candidate_limit: int = 20
    max_targets: int = 5
    allow_global_scope: bool = False

    @classmethod
    def from_config_dict(cls, config: dict[str, Any]) -> FuzzyModifyConfig:
        integration = config.get("integration") if isinstance(config, dict) else None
        if not isinstance(integration, dict):
            return cls()
        return cls(
            enabled=bool(integration.get("fuzzy_modify_enabled", True)),
            auto_execute_enabled=bool(integration.get("fuzzy_modify_auto_execute_enabled", False)),
            confirm_threshold=float(integration.get("fuzzy_modify_confirm_threshold", 0.85) or 0.85),
            candidate_limit=max(1, int(integration.get("fuzzy_modify_candidate_limit", 20) or 20)),
            max_targets=max(1, int(integration.get("fuzzy_modify_max_targets", 5) or 5)),
            allow_global_scope=bool(integration.get("fuzzy_modify_allow_global_scope", False)),
        )

