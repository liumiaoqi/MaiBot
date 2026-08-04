"""启动框架数据模型。"""


from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Awaitable, Callable


class StartupPhase(IntEnum):
    """启动阶段枚举，按顺序执行。"""

    CONFIG_LOAD = 0
    INFRASTRUCTURE = 1
    CORE_SERVICES = 2
    SUBSYSTEMS = 3
    SESSION_RESTORE = 4
    READY = 5


class ComponentStatus(str, Enum):
    """组件初始化状态。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    DEGRADED = "degraded"


@dataclass
class StartupComponent:
    """单个启动组件。

    封装初始化逻辑和运行时状态。init_fn 无参数，通过闭包或实例属性获取依赖。

    已废弃（ZG-10 T32）：启动项声明请改用 StartupItemDesc/@startup_item。
    本类型仅保留兼容（如 PhaseResult.components 旧形态），按需从本模块导入。
    """

    name: str
    phase: StartupPhase
    order: int
    critical: bool
    init_fn: Callable[[], Awaitable[None]]
    core_readiness_flag: str = ""
    status: ComponentStatus = ComponentStatus.PENDING
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: int = 0
    error: Any = None


@dataclass
class StartupItemRuntimeState:
    """单个启动项运行时状态。"""

    name: str
    status: ComponentStatus
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: int = 0
    error: BaseException | None = None
    skip_reason: str = ""


@dataclass
class PhaseResult:
    """单个启动阶段的执行结果。"""

    phase: StartupPhase
    status: ComponentStatus = ComponentStatus.PENDING
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: int = 0
    components: list[StartupComponent] = field(default_factory=list)


@dataclass
class StartupResult:
    """启动流程最终结果。"""

    total_duration_ms: int = 0
    phases: dict[StartupPhase, PhaseResult] = field(default_factory=dict)
    failed_components: list[str] = field(default_factory=list)
    degraded_components: list[str] = field(default_factory=list)
    skipped_components: list[str] = field(default_factory=list)
    wave_info: dict[StartupPhase, list[list[str]]] = field(default_factory=dict)
    failure_chains: dict[str, str] = field(default_factory=dict)
    ready: bool = False
    core_ready: bool = False
    core_ready_time_ms: int = 0
    subsystem_status: dict[str, ComponentStatus] = field(default_factory=dict)


@dataclass
class CoreReadiness:
    """核心就绪状态判定。

    三个条件由 StartupOrchestrator 在阶段 2 完成后自动设置：
    - message_pipeline_ready ← chat_manager_adapter
    - agent_thinking_ready ← agent_registry
    - reply_capability_ready ← replyer_port
    """

    message_pipeline_ready: bool = False
    agent_thinking_ready: bool = False
    reply_capability_ready: bool = False

    @property
    def core_ready(self) -> bool:
        return self.message_pipeline_ready and self.agent_thinking_ready and self.reply_capability_ready
