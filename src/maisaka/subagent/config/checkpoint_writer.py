"""Checkpoint-Writer 子智能体配置模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class CheckpointWriterConfig(BaseModel):
    """Checkpoint-Writer 子智能体配置。

    采用 Fork Agent 模式冻结父级 LLM 请求前缀，
    命中 DeepSeek 前缀缓存，生成11-section结构化会话快照。
    """

    enabled: bool = Field(default=True, description="是否启用 Checkpoint-Writer")
    fork_enabled: bool = Field(default=True, description="是否启用 Fork Agent 模式")
    token_threshold: int = Field(default=0, ge=0, description="触发阈值（0=自动计算）")
    max_consecutive_failures: int = Field(default=3, ge=1, description="最大连续失败次数")
    section_10_token_cap: int = Field(default=3000, ge=100, description="§10设计决策Token上限")
    section_11_token_cap: int = Field(default=800, ge=50, description="§11开放笔记Token上限")
    lifecycle: str = Field(default="ephemeral", description="生命周期模式")
    no_tool_allowlist: bool = Field(default=True, description="禁止设置 tool_allowlist（Fork模式要求schema与父级对齐）")

    @model_validator(mode="after")
    def _validate_no_tool_allowlist(self) -> "CheckpointWriterConfig":
        if not self.no_tool_allowlist:
            raise ValueError(
                "Checkpoint-Writer 禁止设置 tool_allowlist，"
                "Fork Agent 模式要求工具 schema 与父级对齐。"
                "如需自定义工具，请设置 no_tool_allowlist=False 并确保与父级一致。"
            )
        return self