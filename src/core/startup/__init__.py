"""启动框架 — 核心层启动生命周期管理。

本包提供启动流程的阶段化编排、组件注册、降级运行和可观测性，
不依赖任何组件具体实现。
"""

from src.core.startup.orchestrator import StartupOrchestrator
from src.core.startup.types import (
    ComponentStatus,
    CoreReadiness,
    PhaseResult,
    StartupComponent,
    StartupPhase,
    StartupResult,
)

__all__ = [
    "ComponentStatus",
    "CoreReadiness",
    "PhaseResult",
    "StartupComponent",
    "StartupOrchestrator",
    "StartupPhase",
    "StartupResult",
]
