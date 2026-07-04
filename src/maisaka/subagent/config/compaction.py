"""Compaction 子智能体配置模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompactionConfig(BaseModel):
    """Compaction 子智能体配置。

    异步压缩旧消息，替代现有的同步压缩流程。
    """

    enabled: bool = Field(default=True, description="是否启用 Compaction 子智能体")
    threshold_level_1: float = Field(default=0.4, ge=0.0, le=1.0, description="一级压缩阈值（Token占比）")
    threshold_level_2: float = Field(default=0.6, ge=0.0, le=1.0, description="二级压缩阈值（Token占比）")
    threshold_level_3: float = Field(default=0.8, ge=0.0, le=1.0, description="三级压缩阈值（Token占比）")
    tail_turns: int = Field(default=2, ge=1, description="保留最近N轮对话不压缩")
    preserve_recent_tokens_min: int = Field(default=2000, ge=0, description="保留最近Token最小数")
    preserve_recent_tokens_max: int = Field(default=8000, ge=0, description="保留最近Token最大数")
    lifecycle: str = Field(default="ephemeral", description="生命周期模式")
    tool_allowlist: list[str] = Field(
        default_factory=lambda: ["read", "write"],
        description="工具白名单",
    )
    fallback_to_sync: bool = Field(default=True, description="Compaction 失败时降级为同步压缩")