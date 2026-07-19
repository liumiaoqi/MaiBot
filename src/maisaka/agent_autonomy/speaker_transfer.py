"""发言权转移 — 数据模型与配置。

统一管理共居智能体之间的发言权分配，实现临时借用和永久转移两种模式。
管家决策，Orchestrator 执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel


class SpeakerTransferType(Enum):
    TEMPORARY_BORROW = "temporary_borrow"
    PERMANENT_TRANSFER = "permanent_transfer"


class TransferDecisionSource(Enum):
    RULE = "rule"
    LLM = "llm"
    MANUAL = "manual"
    AGENT_EXIT = "agent_exit"


@dataclass(slots=True)
class TransferDecision:
    transfer_type: SpeakerTransferType | None
    target_agent_id: str
    reason: str
    decision_source: TransferDecisionSource
    display_name: str = ""


@dataclass(slots=True)
class SpeakerTransferEvent:
    from_agent_id: str
    to_agent_id: str
    transfer_type: SpeakerTransferType
    change_reason: str
    decision_source: TransferDecisionSource
    timestamp: str


class ButlerConfig(BaseModel):
    can_switch_primary: bool = False
    consecutive_silent_threshold: int = 2
    consecutive_response_threshold: int = 3
    butler_takeover_threshold: int = 2
    borrow_upgrade_threshold: int = 3