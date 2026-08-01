"""资源限制数据模型 — 枚举 + 不可变快照。

对标 Linux cgroup memory controller v2 的数据结构：
- ResourceDimension: 四维度资源计量（对标 memory/CPU/IO/pids）
- PressureLevel: 压力等级（对标 vmpressure 三档）
- FourTierLimit: 四档限制（对标 memory.min/low/high/max）
- OOMAction: OOM 处置动作（对标 oom_kill 的 KILL/DegraDE）
"""


from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ResourceDimension(str, Enum):
    """资源计量维度，对应 spec §6.1 四维度。"""

    TOKEN = "token"
    MESSAGE = "message"
    CONCURRENT = "concurrent"
    MEMORY = "memory"


class PressureLevel(str, Enum):
    """资源压力等级，对应 spec §6.3，对标 vmpressure 三档。"""

    LOW = "low"
    MEDIUM = "medium"
    CRITICAL = "critical"


class OOMAction(str, Enum):
    """OOM 处置动作，对应 spec §6.4，对标 oom_kill 的动作。"""

    DEGRADE = "degrade"
    KILL = "kill"


class LimitTier(str, Enum):
    """四档判定结果，对应 spec §5.2 四档资源限制。"""

    PROTECTED = "protected"
    MIN_EXCEEDED = "min_exceeded"
    LOW_EXCEEDED = "low_exceeded"
    HIGH_EXCEEDED = "high_exceeded"
    MAX_EXCEEDED = "max_exceeded"
    UNCONFIGURED = "unconfigured"


class LimitAction(str, Enum):
    """限制判定动作。"""

    PERMIT = "permit"
    DENY = "deny"


@dataclass(frozen=True)
class ChargeResult:
    """投机充值结果，对应 spec §5.1.1 投机充值回滚。

    accepted=True 时充值成功，父链已全部累加。
    accepted=False 时充值失败，已回滚所有已充级别，overflow_node_id 指示超限节点。
    """

    accepted: bool
    overflow_node_id: Optional[str] = None
    overflow_dimension: Optional[ResourceDimension] = None


@dataclass(frozen=True)
class ResourceUsageSnapshot:
    """插件资源计量快照，对应 spec §6.1。"""

    plugin_id: str
    parent_id: Optional[str]
    token_usage: int
    message_usage: int
    concurrent_usage: int
    memory_usage: int
    under_oom_count: int
    last_update_time: float


@dataclass(frozen=True)
class OOMDecision:
    """OOM 决策结果，对应 spec §6.4。"""

    decision_id: str
    victim_plugin_id: str
    victim_group: list[str]
    action: OOMAction
    decision_time: float


@dataclass(frozen=True)
class OOMDecisionRecord:
    """完整 OOM 决策记录（环形缓冲元素），对应 spec §6.4 + spec §4.3 安全性 4。"""

    decision_id: str
    victim_plugin_id: str
    victim_group: list[str]
    action: OOMAction
    decision_time: float
    trigger_plugin_id: str
    trigger_dimension: ResourceDimension
    trigger_usage: int
    trigger_limit: int
    reap_attempts: int
    reap_success: bool


@dataclass(frozen=True)
class PressureHistoryEntry:
    """压力等级历史记录，对应 spec §6.3。"""

    level: PressureLevel
    scanned: int
    reclaimed: int
    ratio: float
    timestamp: float


@dataclass(frozen=True)
class ResourceTreeView:
    """资源计量树全貌快照，供 WebUI 内省。"""

    nodes: list[ResourceUsageSnapshot]
    topology: dict[str, Optional[str]]


@dataclass(frozen=True)
class LimitDecision:
    """四档限制判定结果。"""

    action: LimitAction
    tier: LimitTier
    trigger_oom: bool = False
    async_reclaim: bool = False
    reclaimable: bool = False


@dataclass(frozen=True)
class FourTierLimitData:
    """四档阈值配置数据（供 AppConfigPort 传递）。"""

    min_val: int = 0
    low_val: int = 0
    high_val: int = 0
    max_val: int = 0


@dataclass(frozen=True)
class ResourceLimitConfigData:
    """插件资源配置数据（供 AppConfigPort 传递）。"""

    plugin_id: str
    limits: dict[ResourceDimension, FourTierLimitData]
    oom_group: bool = False
    events_local: bool = False