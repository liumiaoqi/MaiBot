"""看门狗数据模型 — 枚举 + 不可变快照。"""


from dataclasses import dataclass
from enum import Enum


class BlockSeverity(str, Enum):
    """事件循环阻塞等级。"""

    NORMAL = "normal"
    MILD_LAG = "mild_lag"
    SEVERE_BLOCK = "severe_block"


class DetectionSource(str, Enum):
    """Runner 无响应检测来源。"""

    HEARTBEAT = "heartbeat"
    PROCESS_POLL = "process_poll"
    REGISTRY = "registry"


class FaultReason(str, Enum):
    """故障上报原因。"""

    LOOP_BLOCKED = "loop_blocked"
    RUNNER_UNRESPONSIVE = "runner_unresponsive"


@dataclass(frozen=True)
class WatchdogStatus:
    """事件循环检测状态快照，供 WebUI 内省。

    frozen 保证快照不可变，查询时返回副本。
    last_touch_time / last_check_time 为 time.monotonic() 时钟值。
    """

    block_severity: BlockSeverity
    last_touch_time: float
    last_check_time: float
    consecutive_severe_count: int
    cooldown_until: float
    total_mild_lag_count: int
    total_severe_report_count: int
    check_period_no: int


@dataclass(frozen=True)
class RunnerBridgeStatus:
    """Runner 桥接状态快照。

    每个注册的 Runner 维护一份，桥接事件时更新，查询时返回副本。
    """

    runner_id: str
    component_id: str
    last_detection_source: DetectionSource
    last_consecutive_failures: int
    cooldown_until: float
    total_report_count: int
    last_report_time: float
    is_recovering: bool


@dataclass(frozen=True)
class FaultReportEvent:
    """故障上报事件载体，含审计信息供追溯。

    detail ≤ 500 字符，不含敏感数据。
    """

    component_id: str
    reason: FaultReason
    detail: str
    report_time: float
    check_period_no: int

    def __post_init__(self) -> None:
        if len(self.detail) > 500:
            raise ValueError(
                f"FaultReportEvent.detail 长度 {len(self.detail)} 超过 500 字符上限"
            )