"""服务管理器数据模型 — 枚举 + dataclass。

所有类型均为纯数据，无业务逻辑。枚举继承 str + Enum 以兼容 JSON 序列化。
"""


from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ============================================================
# 枚举
# ============================================================


class ServiceState(str, Enum):
    """运行时生命周期状态枚举（运行时专用，与启动期 ComponentStatus 并存）。"""

    UNMANAGED = "unmanaged"
    """未纳入管理"""

    READY = "ready"
    """已就绪待启动"""

    RUNNING = "running"
    """运行中"""

    DEGRADED = "degraded"
    """降级（弱依赖故障）"""

    FAULT = "fault"
    """故障（自动恢复中）"""

    FAULT_MANUAL = "fault_manual"
    """故障需人工（重启风暴保护触发）"""

    STOPPING = "stopping"
    """停止中"""

    STOPPED = "stopped"
    """已停止"""

    RESTARTING = "restarting"
    """重启中"""


class HealthCheckMode(str, Enum):
    """健康检查模式。"""

    ACTIVE_PROBE = "active_probe"
    """主动探测：管理器定期调用 health_probe"""

    PASSIVE_HEARTBEAT = "passive_heartbeat"
    """被动心跳：组件定期上报心跳"""


class DependencyKind(str, Enum):
    """依赖关系类型。"""

    STRONG = "strong"
    """强依赖：被依赖方停止时，依赖方必须级联停止"""

    WEAK = "weak"
    """弱依赖：被依赖方停止时，依赖方降级而非停止"""


class SystemHealthLevel(str, Enum):
    """系统健康等级。"""

    HEALTHY = "healthy"
    """全部组件运行中"""

    DEGRADED = "degraded"
    """存在降级或非核心故障组件"""

    FAULT = "fault"
    """核心就绪贡献组件故障"""

    RECOVERING = "recovering"
    """存在重启中组件"""


class FaultReason(str, Enum):
    """故障原因枚举。"""

    HEALTH_CHECK_CONSECUTIVE_FAIL = "health_check_consecutive_fail"
    """健康检查连续失败"""

    STOP_TIMEOUT = "stop_timeout"
    """停止超时"""

    PROBE_EXCEPTION = "probe_exception"
    """探针异常"""

    HEARTBEAT_TIMEOUT = "heartbeat_timeout"
    """心跳超时"""

    EXTERNAL_EVENT = "external_event"
    """外部事件上报"""

    MANUAL_MARK = "manual_mark"
    """手动标记"""


class RecoveryAction(str, Enum):
    """恢复动作枚举。"""

    AUTO_RESTART = "auto_restart"
    """自动重启"""

    MANUAL_RESTART = "manual_restart"
    """需人工重启（风暴保护）"""

    NOT_RECOVERED = "not_recovered"
    """未恢复"""

    DEGRADED_RUN = "degraded_run"
    """降级运行"""


# ============================================================
# dataclass
# ============================================================


@dataclass(frozen=True)
class ServiceDescriptor:
    """组件静态描述符 — 声明组件属性和依赖，adopt 时传入。

    frozen=True：静态描述不可变。
    """

    identifier: str
    """组件唯一标识，与 StartupComponent.name 一致"""

    display_name: str
    """展示名称（WebUI 显示用）"""

    health_mode: HealthCheckMode = HealthCheckMode.ACTIVE_PROBE
    """健康检查模式"""

    check_interval_sec: int = 30
    """健康检查间隔（秒），范围 [5, 3600]"""

    core_readiness_flag: str = ""
    """核心就绪贡献标志名（空字符串表示非核心贡献组件）"""

    oom_protected: bool = False
    """是否受 OOM 保护（重启时自动重应用 ZG-9 OOM 优先级）"""

    startup_phase: int = -1
    """启动阶段（预留字段，当前不消费，未来可扩展到启动顺序管理）"""

    startup_order: int = 0
    """启动顺序（预留字段，当前不消费）"""

    def __post_init__(self) -> None:
        if not (5 <= self.check_interval_sec <= 3600):
            raise ValueError(
                f"check_interval_sec 必须在 [5, 3600] 范围内，当前值: {self.check_interval_sec}"
            )


@dataclass(frozen=True)
class ServiceStateSnapshot:
    """组件运行时状态快照 — 每次状态变更创建新实例，保证查询方看到一致快照。

    frozen=True：快照不可变。
    """

    identifier: str
    display_name: str
    state: ServiceState
    health_mode: HealthCheckMode
    last_check_time: Optional[float] = None
    """最近一次健康检查时间戳（monotonic）"""

    consecutive_failures: int = 0
    """连续健康检查失败次数"""

    recent_fault_count: int = 0
    """最近故障计数（风暴窗口内）"""

    restart_count: int = 0
    """累计重启次数"""


@dataclass(frozen=True)
class HealthCheckResult:
    """健康检查结果。"""

    alive: bool
    timestamp: float
    detail: str = ""


@dataclass(frozen=True)
class DependencyRelation:
    """依赖关系声明。"""

    dependent: str
    """依赖方组件 ID"""

    dependency: str
    """被依赖方组件 ID"""

    kind: DependencyKind = DependencyKind.STRONG
    """依赖类型"""


@dataclass(frozen=True)
class FaultRecord:
    """故障记录。"""

    component_id: str
    fault_time: float
    reason: FaultReason
    detail: str = ""
    recovery_action: RecoveryAction = RecoveryAction.NOT_RECOVERED
    recovery_duration_ms: float = 0.0
    backoff_count: int = 0


@dataclass(frozen=True)
class SystemHealthView:
    """系统健康视图 — 聚合全部组件状态。"""

    level: SystemHealthLevel
    core_ready: bool
    message_pipeline_ready: bool
    agent_thinking_ready: bool
    reply_capability_ready: bool
    component_states: list[ServiceStateSnapshot]
    degraded_components: list[str]
    generated_at: float


@dataclass(frozen=True)
class AdoptionResult:
    """接管结果。"""

    adopted_count: int
    skipped_count: int
    dangling_dependencies: list[str]


@dataclass(frozen=True)
class LifecycleActionResult:
    """生命周期操作结果。"""

    success: bool
    component_id: str
    new_state: ServiceState
    cascaded: bool
    error: str = ""