"""Dream 子智能体配置模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DreamConfig(BaseModel):
    """Dream 子智能体配置。

    7天周期从对话轨迹提取持久知识，写入用户画像6桶结构。
    """

    enabled: bool = Field(default=True, description="是否启用 Dream 子智能体")
    interval_days: int = Field(default=7, ge=1, description="巩固周期（天）")
    min_spawn_gap_seconds: int = Field(default=10, ge=0, description="两次派生最小间隔（秒）")
    lifecycle: str = Field(default="persistent", description="生命周期模式")
    tool_allowlist: list[str] = Field(
        default_factory=lambda: ["read", "write", "edit", "glob", "grep", "memory"],
        description="工具白名单",
    )
    max_profile_lines: int = Field(default=200, ge=10, description="画像最大行数")
    max_profile_size_kb: int = Field(default=10, ge=1, description="画像最大体积（KB）")