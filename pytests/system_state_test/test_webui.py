"""WebUI 生命周期端点测试（ZG-6 Task 12）。

覆盖：未授权 401（AC-SEC-02）、响应四项非空（AC-MNT-02）、
state 值为 snake_case 四态之一。
"""

import pytest
from starlette.testclient import TestClient

from src.core.adapters.core_readiness_port import CoreReadinessPortAdapter
from src.core.adapters.system_lifecycle_adapter import SystemLifecycleAdapter
from src.core.service_manager.state_aggregator import StateAggregator
from src.core.service_manager.types import (
    HealthCheckMode,
    ServiceState,
    ServiceStateSnapshot,
)
from src.core.startup.types import CoreReadiness
from src.core.system_state.state_machine import SystemStateMachine
from src.core.system_state_port_registry import (
    reset_system_lifecycle_adapter,
    set_system_lifecycle_adapter,
)
from src.webui.app import create_app
from src.webui.core import get_token_manager

VALID_STATES = {"booting", "ready", "degrading", "shutting_down"}


@pytest.fixture
def client():
    with TestClient(create_app(enable_static=False)) as c:
        yield c


@pytest.fixture
def auth_client(client):
    token = get_token_manager().get_token()
    client.cookies.set("maibot_session", token)
    return client


@pytest.fixture(autouse=True)
def _cleanup_registry():
    """每个测试后清空注册点，避免跨测试泄漏。"""
    yield
    reset_system_lifecycle_adapter()


def _register_adapter() -> SystemLifecycleAdapter:
    """注册一个带真实状态机/聚合器的适配器到注册点。"""
    snapshot = ServiceStateSnapshot(
        identifier="chat",
        display_name="chat",
        state=ServiceState.RUNNING,
        health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
    )
    aggregator = StateAggregator(component_registry={"chat": snapshot}, core_readiness_map={})
    adapter = SystemLifecycleAdapter(
        state_machine=SystemStateMachine(),
        core_readiness_port=CoreReadinessPortAdapter(CoreReadiness()),
        state_aggregator=aggregator,
    )
    set_system_lifecycle_adapter(adapter)
    return adapter


def test_lifecycle_endpoint_auth(client):
    """AC-ZG6-SEC-02: 未授权返回 401。"""
    resp = client.get("/api/webui/system/lifecycle")
    assert resp.status_code == 401


def test_lifecycle_endpoint_response(auth_client):
    """AC-ZG6-MNT-02: 响应含四项非空。"""
    adapter = _register_adapter()
    resp = auth_client.get("/api/webui/system/lifecycle")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["state"] == "booting"
    assert data["health_level"] == "healthy"
    assert data["core_readiness"] == {
        "message_pipeline_ready": False,
        "agent_thinking_ready": False,
        "reply_capability_ready": False,
    }
    assert data["transition_history"] == []
    assert data["generated_at"] > 0
    assert adapter is not None  # 确保注册真实适配器（非默认分支）


async def test_lifecycle_endpoint_state_values(auth_client):
    """state 值为 snake_case 四态之一（READY 迁移后）。"""
    adapter = _register_adapter()
    await adapter.trigger_startup_complete()
    resp = auth_client.get("/api/webui/system/lifecycle")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["state"] in VALID_STATES
    assert data["state"] == "ready"
    assert len(data["transition_history"]) == 1
    assert data["transition_history"][0]["old_state"] == "booting"
    assert data["transition_history"][0]["new_state"] == "ready"


def test_lifecycle_endpoint_unregistered_default(auth_client):
    """未注册适配器时返回 BOOTING 默认值（启动早期窗口）。"""
    resp = auth_client.get("/api/webui/system/lifecycle")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["state"] == "booting"
    assert data["transition_history"] == []
