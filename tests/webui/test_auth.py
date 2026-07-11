"""Auth 路由集成测试"""

from src.webui.errors.codes import ErrorCode


def test_health_check(client):
    resp = client.get("/api/webui/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["status"] == "healthy"


def test_verify_token_invalid(client):
    resp = client.post("/api/webui/auth/verify", json={"token": "invalid_token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["valid"] is False


def test_check_auth_unauthenticated(client):
    resp = client.get("/api/webui/auth/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["authenticated"] is False


def test_check_auth_authenticated(auth_client):
    resp = auth_client.get("/api/webui/auth/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["authenticated"] is True


def test_verify_token_valid(auth_client):
    from src.webui.core import get_token_manager

    token = get_token_manager().get_token()
    resp = auth_client.post("/api/webui/auth/verify", json={"token": token})
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["valid"] is True


def test_unauthorized_access(client):
    resp = client.get("/api/webui/agent/list")
    assert resp.status_code == 401
