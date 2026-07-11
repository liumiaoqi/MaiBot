"""Config 路由集成测试

注意：部分端点尚未迁移到 ApiResponse 格式，测试适配当前实际返回格式。
待阶段3迁移完成后，统一断言 data["code"] == 0。
"""


def test_get_bot_config_schema(auth_client):
    resp = auth_client.get("/api/webui/config/schema/bot")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is True or data.get("code") == 0


def test_get_model_config_schema(auth_client):
    resp = auth_client.get("/api/webui/config/schema/model")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is True or data.get("code") == 0


def test_get_bot_config(auth_client):
    resp = auth_client.get("/api/webui/config/bot")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is True or data.get("code") == 0


def test_get_model_config(auth_client):
    resp = auth_client.get("/api/webui/config/model")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is True or data.get("code") == 0


def test_get_prompts_list(auth_client):
    resp = auth_client.get("/api/webui/config/prompts")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("code") == 0


def test_get_adapter_config_path(auth_client):
    resp = auth_client.get("/api/webui/config/adapter-config/path")
    assert resp.status_code == 200


def test_unauthenticated_config_access():
    from starlette.testclient import TestClient

    from src.webui.app import create_app

    app = create_app(enable_static=False)
    with TestClient(app) as unauth_client:
        resp = unauth_client.get("/api/webui/config/bot")
        assert resp.status_code == 401
