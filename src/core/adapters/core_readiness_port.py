"""CoreReadinessPort 适配器 — 运行时核心就绪持续判定。

复用现有 CoreReadiness 三标志语义，扩展为运行时持续判定。
"""



from src.core.startup.types import CoreReadiness

_VALID_FLAGS = frozenset(
    {
        "message_pipeline_ready",
        "agent_thinking_ready",
        "reply_capability_ready",
    }
)


class CoreReadinessPortAdapter:
    """CoreReadinessPort 适配器 — 包装现有 CoreReadiness 实例。

    CoreReadiness 双重语义：
    - StartupOrchestrator._update_core_readiness() 启动时一次性置 True
    - 本适配器 update_flag() 运行时持续更新（核心组件 FAULT 时置 False）
    本适配器是 CoreReadiness 的运行时权威源。
    """

    def __init__(self, core_readiness: CoreReadiness) -> None:
        self._core_readiness = core_readiness

    def get_core_readiness(self) -> CoreReadiness:
        """返回 CoreReadiness 实例（三标志当前值）。"""
        return self._core_readiness

    def is_core_ready(self) -> bool:
        """返回核心是否就绪。"""
        return self._core_readiness.core_ready

    def update_flag(self, flag_name: str, value: bool) -> None:
        """更新单个就绪标志。

        Args:
            flag_name: 标志名，仅接受三标志名
            value: 标志值

        Raises:
            ValueError: flag_name 非法
        """
        if flag_name not in _VALID_FLAGS:
            raise ValueError(
                f"非法标志名: {flag_name}，仅接受 {sorted(_VALID_FLAGS)}"
            )
        setattr(self._core_readiness, flag_name, value)