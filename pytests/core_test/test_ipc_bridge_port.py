"""ZG-14：IpcBridgePort Protocol / registry / adapter / EventBus 行为不变性测试。"""

import pytest

from src.core.adapters.ipc_bridge_port import IpcBridgePortAdapter
from src.core.protocols import IpcBridgePort
from src.core.ipc_bridge_port_registry import (
    __service_descriptor__,
    get_ipc_bridge_port,
    reset_ipc_bridge_port,
    set_ipc_bridge_port,
)
from src.core.startup.types import StartupPhase


class _FakePRM:
    """轻量 mock PluginRuntimeManager。"""

    def __init__(self, running: bool = True, bridge_result=None):
        self._started = running
        self._bridge_result = bridge_result or (True, None)
        self.bridge_calls: list[tuple] = []

    @property
    def is_running(self) -> bool:
        return self._started

    async def bridge_event(
        self, event_type_value: str, message_dict=None, extra_args=None, **kwargs
    ):
        # 记录 kwargs 以区分"未传 extra_args"与"显式传 None"（CX 审核 P2-1）
        self.bridge_calls.append((event_type_value, message_dict, extra_args, kwargs))
        return self._bridge_result


# ── T6.1 Protocol 测试 ────────────────────────────────────────


def test_ipc_bridge_port_runtime_checkable():
    """IpcBridgePort @runtime_checkable 生效：isinstance(适配器, IpcBridgePort) → True。"""
    prm = _FakePRM()
    adapter = IpcBridgePortAdapter(prm)
    assert isinstance(adapter, IpcBridgePort)


def test_ipc_bridge_port_minimal_interface():
    """Protocol 仅包含 bridge_event 和 is_running 两个成员（CX 审核 P2-2）。"""
    members = {name for name in dir(IpcBridgePort) if not name.startswith("_")}
    assert members == {"bridge_event", "is_running"}


# ── T6.2 Registry 测试 ────────────────────────────────────────


def test_registry_initial_none():
    """初始状态 get_ipc_bridge_port() 返回 None。"""
    reset_ipc_bridge_port()
    assert get_ipc_bridge_port() is None


def test_registry_set_get():
    """set 后 get 返回已注入实例。"""
    reset_ipc_bridge_port()
    prm = _FakePRM()
    adapter = IpcBridgePortAdapter(prm)
    set_ipc_bridge_port(adapter)
    assert get_ipc_bridge_port() is adapter


def test_registry_reset():
    """reset 后 get 返回 None。"""
    reset_ipc_bridge_port()
    prm = _FakePRM()
    set_ipc_bridge_port(IpcBridgePortAdapter(prm))
    reset_ipc_bridge_port()
    assert get_ipc_bridge_port() is None


def test_service_descriptor_fields():
    """__service_descriptor__ 字段值正确。"""
    assert __service_descriptor__["name"] == "ipc_bridge_port"
    assert __service_descriptor__["phase"] == StartupPhase.SUBSYSTEMS
    assert __service_descriptor__["order"] == 1
    assert __service_descriptor__["critical"] is False
    assert __service_descriptor__["protocol"] is IpcBridgePort
    assert __service_descriptor__["register_fn"] is set_ipc_bridge_port
    assert __service_descriptor__["depends_on"] == ("plugin_runtime",)


# ── T6.3 Adapter 测试 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_adapter_is_running_delegates():
    """is_running 委托到 prm.is_running。"""
    prm_running = _FakePRM(running=True)
    prm_stopped = _FakePRM(running=False)
    assert IpcBridgePortAdapter(prm_running).is_running is True
    assert IpcBridgePortAdapter(prm_stopped).is_running is False


@pytest.mark.asyncio
async def test_adapter_bridge_event_delegates():
    """bridge_event 委托到 prm.bridge_event，参数和返回值透传。"""
    result = (False, {"key": "value"})
    prm = _FakePRM(bridge_result=result)
    adapter = IpcBridgePortAdapter(prm)
    got = await adapter.bridge_event("on_message_send", {"msg": "hi"})
    assert got == result
    assert len(prm.bridge_calls) == 1
    assert prm.bridge_calls[0][0] == "on_message_send"
    assert prm.bridge_calls[0][1] == {"msg": "hi"}


@pytest.mark.asyncio
async def test_adapter_no_extra_args():
    """适配器不传递 extra_args（CX 审核 P2-1：断言 kwargs 为空而非 None 默认值）。"""
    prm = _FakePRM()
    adapter = IpcBridgePortAdapter(prm)
    await adapter.bridge_event("test", None)
    # kwargs 为空 = 未传 extra_args（extra_args 位置是 None 默认值，不足以区分）
    assert prm.bridge_calls[0][3] == {}


# ── T6.4 EventBus 行为不变性测试 ──────────────────────────────


@pytest.mark.asyncio
async def test_bridge_port_none_skips():
    """端口未注入时跳过桥接，continue_flag 和 message 不变。"""
    reset_ipc_bridge_port()
    from src.core.event_bus import EventBus
    eb = EventBus()
    flag, msg = await eb._bridge_to_ipc_runtime("test_event", True, None)
    assert flag is True
    assert msg is None


@pytest.mark.asyncio
async def test_bridge_port_not_running_skips():
    """端口已注入但 is_running=False 时跳过桥接。"""
    reset_ipc_bridge_port()
    prm = _FakePRM(running=False)
    set_ipc_bridge_port(IpcBridgePortAdapter(prm))
    from src.core.event_bus import EventBus
    eb = EventBus()
    flag, msg = await eb._bridge_to_ipc_runtime("test_event", True, None)
    assert flag is True
    assert len(prm.bridge_calls) == 0


@pytest.mark.asyncio
async def test_bridge_port_running_bridges():
    """端口已注入且 is_running=True 时正常桥接。"""
    reset_ipc_bridge_port()
    prm = _FakePRM(running=True, bridge_result=(False, {"modified": True}))
    set_ipc_bridge_port(IpcBridgePortAdapter(prm))
    from src.core.event_bus import EventBus
    eb = EventBus()
    flag, msg = await eb._bridge_to_ipc_runtime("test_event", True, None)
    assert flag is False
    assert len(prm.bridge_calls) == 1


class _FakeMessage:
    """轻量 MaiMessages mock：验证序列化边界与回写（CX 审核 P1-2）。"""

    def __init__(self, transport: dict) -> None:
        self.transport = transport
        self.updated: object = None

    def to_transport_dict(self) -> dict:
        return self.transport

    def apply_transport_update(self, modified: dict) -> "_FakeMessage":
        self.updated = modified
        return self


@pytest.mark.asyncio
async def test_bridge_continue_false_short_circuits():
    """continue_flag=False 直接返回，不调用桥接（design §2.6 场景 1，CX 审核 P1-2）。"""
    reset_ipc_bridge_port()
    prm = _FakePRM(running=True)
    set_ipc_bridge_port(IpcBridgePortAdapter(prm))
    from src.core.event_bus import EventBus

    eb = EventBus()
    msg = _FakeMessage({"text": "hi"})
    flag, m = await eb._bridge_to_ipc_runtime("test_event", False, msg)
    assert flag is False
    assert m is msg
    assert len(prm.bridge_calls) == 0


@pytest.mark.asyncio
async def test_bridge_new_continue_false_sets_flag():
    """桥接返回 new_continue=False 时 continue_flag 置 False（design §2.6 场景 4）。"""
    reset_ipc_bridge_port()
    prm = _FakePRM(running=True, bridge_result=(False, None))
    set_ipc_bridge_port(IpcBridgePortAdapter(prm))
    from src.core.event_bus import EventBus

    eb = EventBus()
    flag, msg = await eb._bridge_to_ipc_runtime("test_event", True, None)
    assert flag is False


@pytest.mark.asyncio
async def test_bridge_modified_dict_writeback():
    """modified_dict 回写 + to_transport_dict 序列化边界（design §2.6 场景 5，CX 审核 P1-2）。"""
    reset_ipc_bridge_port()
    prm = _FakePRM(running=True, bridge_result=(True, {"text": "modified"}))
    set_ipc_bridge_port(IpcBridgePortAdapter(prm))
    from src.core.event_bus import EventBus

    eb = EventBus()
    msg = _FakeMessage({"text": "hi"})
    flag, m = await eb._bridge_to_ipc_runtime("test_event", True, msg)
    assert flag is True
    assert m is msg
    # 序列化边界：传给桥接的是 to_transport_dict() 结果
    assert prm.bridge_calls[0][1] == {"text": "hi"}
    # 回写边界：modified_dict 经 _apply_ipc_message_update（apply_transport_update）
    assert msg.updated == {"text": "modified"}


@pytest.mark.asyncio
async def test_bridge_exception_swallowed():
    """桥接异常时 WARNING 日志 + 标记 TAINT_EXCEPTION_SWALLOWED，continue_flag 保持原值。"""
    from unittest.mock import patch

    reset_ipc_bridge_port()

    class FailingPRM:
        _started = True

        @property
        def is_running(self):
            return True

        async def bridge_event(self, **kw):
            raise RuntimeError("bridge boom")

    set_ipc_bridge_port(IpcBridgePortAdapter(FailingPRM()))
    from src.core.event_bus import EventBus
    eb = EventBus()
    with patch("src.core.tainted_mask.mark.mark_taint") as mock_mark:
        flag, msg = await eb._bridge_to_ipc_runtime("test_event", True, None)
    assert flag is True
    from src.core.tainted_mask.taint_flag import TaintFlag

    mock_mark.assert_any_call(TaintFlag.TAINT_EXCEPTION_SWALLOWED)  # CX 审核 P2-4


# ── T6.5 PRM 启动失败场景测试 ─────────────────────────────────


@pytest.mark.asyncio
async def test_inject_with_unstarted_prm(monkeypatch):
    """PRM 未启动时 _inject_ipc_bridge_port 安全注入（tasks §6.5，CX 审核 P1-3）。

    SUBSYSTEMS 阶段并行执行（orchestrator._run_subsystems_parallel），order 仅定创建
    顺序——即使 plugin_runtime 启动失败，_inject 仍会执行；安全性靠懒加载单例：
    未启动 PRM → is_running=False → EventBus 桥接跳过。
    """
    reset_ipc_bridge_port()
    from src.main import MainSystem

    class _UnstartedPRM:
        @property
        def is_running(self) -> bool:
            return False

        async def bridge_event(self, **kw):
            return True, None

    monkeypatch.setattr(
        "src.plugin_runtime.integration.get_plugin_runtime_manager",
        lambda: _UnstartedPRM(),
    )
    await MainSystem._inject_ipc_bridge_port()
    port = get_ipc_bridge_port()
    assert port is not None
    assert port.is_running is False


# ── T6.6 端口 reset 后降级测试 ────────────────────────────────


@pytest.mark.asyncio
async def test_reset_then_bridge_skips():
    """reset 后 EventBus 桥接降级。"""
    reset_ipc_bridge_port()
    prm = _FakePRM(running=True)
    set_ipc_bridge_port(IpcBridgePortAdapter(prm))
    reset_ipc_bridge_port()
    from src.core.event_bus import EventBus
    eb = EventBus()
    flag, msg = await eb._bridge_to_ipc_runtime("test_event", True, None)
    assert flag is True
    assert len(prm.bridge_calls) == 0
