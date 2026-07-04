"""子智能体数据模型。

定义 SubAgentSpec（规格）、SubAgentStatus（运行状态）、SubAgentHandle（句柄）。
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SubAgentType(str, Enum):
    """子智能体类型。"""

    DREAM = "dream"
    COMPACTION = "compaction"
    CHECKPOINT_WRITER = "checkpoint_writer"


class SubAgentLifecycle(str, Enum):
    """子智能体生命周期模式。"""

    EPHEMERAL = "ephemeral"
    PERSISTENT = "persistent"


class SubAgentState(str, Enum):
    """子智能体运行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"
    DESTROYED = "destroyed"


class TriggerType(str, Enum):
    """触发类型。"""

    AUTO = "auto"
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class SubAgentSpec(BaseModel):
    """子智能体规格，描述如何派生一个子智能体。"""

    subagent_type: SubAgentType = Field(default=SubAgentType.DREAM, description="子智能体类型")
    agent_id: str = Field(default="", description="父级智能体ID")
    session_id: str = Field(default="", description="关联会话ID")
    interactive: bool = Field(default=False, description="是否需要人类交互（False=自动拒绝ask请求）")
    lifecycle: SubAgentLifecycle = Field(default=SubAgentLifecycle.EPHEMERAL, description="生命周期模式")
    tool_allowlist: list[str] = Field(default_factory=list, description="工具白名单（空=继承父级）")
    fork_context: Optional[dict[str, Any]] = Field(default=None, description="Fork上下文快照")
    trigger_type: TriggerType = Field(default=TriggerType.AUTO, description="触发类型")
    trigger_reason: str = Field(default="", description="触发原因描述")
    config: dict[str, Any] = Field(default_factory=dict, description="子智能体级配置")


class SubAgentStatus(BaseModel):
    """子智能体运行状态。"""

    subagent_id: str = Field(default="", description="子智能体实例ID")
    spec: SubAgentSpec = Field(default_factory=SubAgentSpec, description="子智能体规格")
    state: SubAgentState = Field(default=SubAgentState.PENDING, description="运行状态")
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="进度(0-1)")
    progress_description: str = Field(default="", description="进度描述")
    started_at: float = Field(default=0.0, description="启动时间戳")
    completed_at: float = Field(default=0.0, description="完成时间戳")
    error_message: str = Field(default="", description="错误信息")
    result_summary: str = Field(default="", description="结果摘要")
    input_tokens: int = Field(default=0, description="输入Token消耗")
    output_tokens: int = Field(default=0, description="输出Token消耗")
    cache_hit_tokens: int = Field(default=0, description="缓存命中Token")

    @property
    def is_terminal(self) -> bool:
        """是否处于终态。"""
        return self.state in {
            SubAgentState.COMPLETED,
            SubAgentState.FAILED,
            SubAgentState.CANCELLED,
            SubAgentState.DESTROYED,
        }

    @property
    def elapsed_seconds(self) -> float:
        """已运行时间（秒）。"""
        if self.started_at <= 0:
            return 0.0
        end = self.completed_at if self.completed_at > 0 else time.time()
        return end - self.started_at


class SubAgentHandle(BaseModel):
    """子智能体句柄，用于外部查询状态。"""

    subagent_id: str = Field(default="", description="子智能体实例ID")
    agent_id: str = Field(default="", description="父级智能体ID")
    subagent_type: SubAgentType = Field(default=SubAgentType.DREAM, description="子智能体类型")
    state: SubAgentState = Field(default=SubAgentState.PENDING, description="运行状态")
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="进度")

    @staticmethod
    def from_status(status: SubAgentStatus) -> "SubAgentHandle":
        """从运行状态创建句柄。"""
        return SubAgentHandle(
            subagent_id=status.subagent_id,
            agent_id=status.spec.agent_id,
            subagent_type=status.spec.subagent_type,
            state=status.state,
            progress=status.progress,
        )


def generate_subagent_id() -> str:
    """生成子智能体实例ID。"""
    return f"sub_{uuid.uuid4().hex[:12]}"