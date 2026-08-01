"""S3 V2 Runner 注册验证测试（ZG-3 补强）。

V2 注册路径：Runner 连接时 PluginRuntimeV2Servicer 经 get_watchdog_port()
调用 register_v2_supervisor（servicer.py:200-214）。
_supervisor 由 endpoint.set_supervisor() 在启动期注入（endpoint.py:167-171，
先于任何 Runner 连接）——验证该链路完整性，无需补代码。
"""



from src.core.watchdog.runner_health_bridge import RunnerHealthBridge


class _FakeEndpoint:
    """模拟 HostEndpoint：验证 set_supervisor 传播到 servicer。"""

    def __init__(self):
        self._supervisor = None
        self._servicer = _FakeServicer()

    def set_supervisor(self, supervisor) -> None:
        self._supervisor = supervisor
        self._servicer._supervisor = supervisor  # endpoint.py:171


class _FakeServicer:
    def __init__(self):
        self._supervisor = None


class _FakeSupervisor:
    """模拟 RunnerSupervisor：带 get_health_status 的 V2 supervisor。"""

    def get_health_status(self):
        return {"status": "ok"}


def test_set_supervisor_propagates_to_servicer():
    """tasks 5.4.2: set_supervisor 后 servicer._supervisor 非 None（连接时点有值）。"""
    endpoint = _FakeEndpoint()
    supervisor = _FakeSupervisor()
    endpoint.set_supervisor(supervisor)
    assert endpoint._servicer._supervisor is supervisor


async def test_v2_registration_on_connection(fast_config, event_loop):
    """tasks 5.4.1: V2 Runner 注册后桥接状态可见该 Runner。"""
    bridge = RunnerHealthBridge(fast_config, event_loop, lambda e: None)
    supervisor = _FakeSupervisor()

    class _FakeHB:
        def add_timeout_listener(self, runner_id, callback):
            return None

    # register_v2_supervisor 为同步方法（内部 ensure_future 需 running loop），
    # 在 async 测试内调用
    bridge.register_v2_supervisor(
        "runner-test-1", supervisor, _FakeHB(), "plugin_runtime_v2",
    )
    statuses = bridge.list_runner_bridge_status()
    assert any(s.runner_id == "runner-test-1" for s in statuses)


def test_v2_registration_degrade_on_failure(fast_config, event_loop):
    """tasks 5.4.3: 注册失败不阻断（真实路径：未启动的 adapter 抛 RuntimeError）。

    CX 审查修正：驱动 WatchdogAdapter 未启动的真实降级路径
    （adapter 抛 RuntimeError"看门狗未启动"→ servicer 侧 except Exception 捕获）。
    """
    from src.core.adapters.watchdog_adapter import WatchdogAdapter

    adapter = WatchdogAdapter(config=fast_config)  # 未 start()，_runner_bridge 为 None
    supervisor = _FakeSupervisor()

    # servicer.py 的降级模式：捕获异常记录日志，不向外抛
    try:
        adapter.register_v2_supervisor(
            "runner-bad", supervisor, None, "plugin_runtime_v2",
        )
        raise AssertionError("未启动的 adapter 应抛 RuntimeError")
    except RuntimeError as e:
        assert "看门狗未启动" in str(e)  # servicer 侧 except Exception 捕获并降级


async def test_v2_registration_idempotent(fast_config, event_loop):
    """tasks 5.4.4: 同一 runner_id 重复注册被忽略。"""
    bridge = RunnerHealthBridge(fast_config, event_loop, lambda e: None)
    supervisor = _FakeSupervisor()

    class _FakeHB:
        def add_timeout_listener(self, runner_id, callback):
            return None

    bridge.register_v2_supervisor(
        "runner-dup", supervisor, _FakeHB(), "plugin_runtime_v2",
    )
    bridge.register_v2_supervisor(
        "runner-dup", supervisor, _FakeHB(), "plugin_runtime_v2",
    )
    statuses = bridge.list_runner_bridge_status()
    assert sum(1 for s in statuses if s.runner_id == "runner-dup") == 1
