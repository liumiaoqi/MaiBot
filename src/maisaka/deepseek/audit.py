"""参数演变审计日志。"""

from __future__ import annotations

import time
from enum import Enum

from pydantic import BaseModel, Field


class EvolutionTrigger(str, Enum):
    """演变触发类型。"""

    AUTO_COST = "auto_cost"
    AUTO_CACHE = "auto_cache"
    AUTO_FREQUENCY = "auto_frequency"
    MANUAL = "manual"


class ParameterEvolutionAuditLog(BaseModel):
    """参数演变审计日志。"""

    log_id: str = Field(default="", description="日志ID")
    agent_id: str = Field(default="", description="智能体ID")
    parameter_name: str = Field(default="", description="参数名称")
    old_value: float = Field(default=0.0, description="旧值")
    new_value: float = Field(default=0.0, description="新值")
    trigger: EvolutionTrigger = Field(default=EvolutionTrigger.AUTO_COST, description="触发类型")
    reason: str = Field(default="", description="演变原因")
    timestamp: float = Field(default=0.0, description="时间戳")

    def to_dict(self) -> dict:
        return self.model_dump()