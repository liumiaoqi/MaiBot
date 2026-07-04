"""子智能体调度系统。"""

from .agents.compaction import CompactionAgent, CompactionLevel, CompactionResult, CompactionSummary
from .agents.dream import DreamAgent, DreamResult
from .config.compaction import CompactionConfig
from .config.dream import DreamConfig
from .interactive_gate import AskRequest, AskResponse, InteractiveGate
from .lifecycle import SubAgentLifecycleManager
from .models import (
    SubAgentHandle,
    SubAgentLifecycle,
    SubAgentSpec,
    SubAgentState,
    SubAgentStatus,
    SubAgentType,
    TriggerType,
    generate_subagent_id,
)
from .registry import SubAgentRegistry
from .scheduler import ConcurrencyLimitExceededError, SpawnTimeoutError, SubAgentScheduler

__all__ = [
    "AskRequest",
    "AskResponse",
    "CompactionAgent",
    "CompactionConfig",
    "CompactionLevel",
    "CompactionResult",
    "CompactionSummary",
    "ConcurrencyLimitExceededError",
    "DreamAgent",
    "DreamConfig",
    "DreamResult",
    "InteractiveGate",
    "SpawnTimeoutError",
    "SubAgentHandle",
    "SubAgentLifecycle",
    "SubAgentLifecycleManager",
    "SubAgentScheduler",
    "SubAgentSpec",
    "SubAgentState",
    "SubAgentStatus",
    "SubAgentRegistry",
    "SubAgentType",
    "TriggerType",
    "generate_subagent_id",
]
