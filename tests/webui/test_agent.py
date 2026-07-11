"""Agent 路由集成测试"""


def test_list_agents(auth_client):
    resp = auth_client.get("/api/webui/agent/list")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], dict)


def test_get_agent_detail_not_found(auth_client):
    resp = auth_client.get("/api/webui/agent/99999")
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        data = resp.json()
        assert data.get("code") == 0 or data.get("error_code") == "BIZ_NOT_FOUND"


def test_batch_emotion(auth_client):
    resp = auth_client.get("/api/webui/agent/batch/emotion")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0


def test_batch_relationships(auth_client):
    resp = auth_client.get("/api/webui/agent/batch/relationships")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0


def test_unauthenticated_agent_access():
    from starlette.testclient import TestClient

    from src.webui.app import create_app

    app = create_app(enable_static=False)
    with TestClient(app) as unauth_client:
        resp = unauth_client.get("/api/webui/agent/list")
        assert resp.status_code == 401
