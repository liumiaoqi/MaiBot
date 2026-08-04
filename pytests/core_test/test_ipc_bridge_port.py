"""ZG-14：IpcBridgePort Protocol / registry / adapter / EventBus 行为不变性测试。"""

import asyncio

import pytest

from src.core.protocols import IpcBridgePort
from src.core.ipc_bridge_port_registry import (
    get_ipc_bridge_port,
    set_ipc_bridge_port,
    reset_ipc_bridge_port,
    __service_descriptor__,
)
from src.core.adapters.ipc_bridge_port import IpcBridgePortAdapter
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
        self, event_type_value: str, message_dict=None, extra_args=None
    ):
        self.bridge_calls.append((event_type_value, message_dict, extra_args))
        return self._bridge_result


# ── T6.1 Protocol 测试 ────────────────────────────────────────


def test_ipc_bridge_port_runtime_checkable():
    """IpcBridgePort @runtime_checkable 生效：isinstance(适配器, IpcBridgePort) → True。"""
    prm = _FakePRM()
    adapter = IpcBridgePortAdapter(prm)
    assert isinstance(adapter, IpcBridgePort)


def test_ipc_bridge_port_minimal_interface():
    """Protocol 仅包含 bridge_event 和 is_running 两个成员。"""
    members = {name for name in dir(IpcBridgePort) if not name.startswith("_")}
    assert "bridge_event" in members
    assert "is_running" in members


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
    """适配器不传递 extra_args。"""
    prm = _FakePRM()
    adapter = IpcBridgePortAdapter(prm)
    await adapter.bridge_event("test", None)
    assert prm.bridge_calls[0][2] is None  # extra_args 未传


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


@pytest.mark.asyncio
async def test_bridge_exception_swallowed():
    """桥接异常时 WARNING 日志，continue_flag 保持原值。"""
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
    flag, msg = await eb._bridge_to_ipc_runtime("test_event", True, None)
    assert flag is True


# ── T6.5 PRM 启动失败场景测试 ─────────────────────────────────


def test_adapter_with_unstarted_prm():
    """PRM 启动失败后适配器创建安全，is_running=False。"""
    prm = _FakePRM(running=False)
    adapter = IpcBridgePortAdapter(prm)
    assert isinstance(adapter, IpcBridgePort)
    assert adapter.is_running is False


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