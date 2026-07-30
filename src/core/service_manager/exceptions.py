"""服务管理器自定义异常。"""


class UnknownComponentError(Exception):
    """组件未纳入管理。"""


class DependencyNotReadyError(Exception):
    """启动时依赖未就绪。"""

    def __init__(self, message: str, missing_dependencies: list[str]) -> None:
        super().__init__(message)
        self.missing_dependencies = missing_dependencies


class DependencyCycleError(Exception):
    """依赖声明形成环。"""

    def __init__(self, message: str, cycle: list[str]) -> None:
        super().__init__(message)
        self.cycle = cycle


class RestartStormError(Exception):
    """组件处于"故障(需人工)"禁止自动恢复。"""


class ConfirmationRequiredError(Exception):
    """核心就绪贡献组件需二次确认。"""


class RestartInProgressError(Exception):
    """组件处于"重启中"时再次下发重启。"""