"""WebUI 测试基础设施 — conftest.py"""

from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from src.webui.app import create_app
from src.webui.core import get_token_manager


@pytest.fixture(autouse=True)
def _register_webui_ports():
    """注册 WebUI 所需 Port（anti_crawler 模块 import 时即读配置；agent/auth 路由按需读取）。"""
    from src.core.adapters.agent_config_port import set_agent_config_provider
    from src.core.app_config_port_registry import (
        reset_app_config_port,
        set_app_config_port,
    )
    from src.core.bot_config_port_registry import (
        reset_bot_config_port,
        set_bot_config_port,
    )

    set_app_config_port(
        SimpleNamespace(
            get_webui_anti_crawler_mode=lambda: "off",
            get_webui_allowed_ips=lambda: [],
            get_webui_trusted_proxies=lambda: [],
            get_webui_trust_xff=lambda: False,
            get_webui_secure_cookie=lambda: False,
            get_webui_mode=lambda: "development",
            get_a_memorix_full_config=lambda: {},
        )
    )
    set_bot_config_port(
        SimpleNamespace(
            get_bot_platform=lambda: "aiocqhttp",
            get_bot_primary_account=lambda: "",
            get_bot_platforms=lambda: [],
            get_bot_nickname=lambda: "MaiBot",
            get_bot_qq_account=lambda platform: 0,
        )
    )
    set_agent_config_provider(
        SimpleNamespace(
            get_agent=lambda agent_id: None,
            list_agents=lambda: [],
            get_default_agent=lambda: None,
            has_agent=lambda agent_id: False,
            reload=lambda: None,
            reload_agent=lambda agent_id: False,
            load=lambda: None,
        )
    )
    yield
    reset_app_config_port()
    reset_bot_config_port()


@pytest.fixture
def app():
    return create_app(enable_static=False)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    token_manager = get_token_manager()
    token = token_manager.get_token()
    client.cookies.set("maibot_session", token)
    return client


def assert_api_success(response, expected_code: int = 200):
    assert response.status_code == expected_code, f"状态码 {response.status_code}: {response.text}"
    data = response.json()
    if "code" in data:
        assert data["code"] == 0, f"业务错误: {data}"
    if "error_code" in data:
        pytest.fail(f"错误响应: {data}")


def assert_api_error(response, expected_error_code: str, expected_status: int = None):
    if expected_status:
        assert response.status_code == expected_status, f"状态码 {response.status_code}: {response.text}"
    data = response.json()
    assert "error_code" in data, f"非错误响应: {data}"
    assert data["error_code"] == expected_error_code, f"错误码不匹配: {data}"
