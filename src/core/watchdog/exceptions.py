"""看门狗自定义异常。"""


class ServiceManagerPortNotReadyError(Exception):
    """启动看门狗时 ServiceManagerPort 未注册（上报目标未就绪）。"""


class WatchdogAlreadyRunningError(Exception):
    """start 时看门狗已在运行。"""


class UnknownRunnerError(Exception):
    """unregister 的 runner_id 未注册。"""

    def __init__(self, runner_id: str) -> None:
        self.runner_id = runner_id
        super().__init__(f"未注册的 Runner: {runner_id}")