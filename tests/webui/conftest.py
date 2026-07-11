"""WebUI 测试基础设施 — conftest.py"""

import pytest
from starlette.testclient import TestClient

from src.webui.app import create_app
from src.webui.core import get_token_manager


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
