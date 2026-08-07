"""端点资源化测试：验证旧路径返回 404，新路径可访问，purge cascade 语义。"""

import pytest


class TestEndpointResource:
    """T4 端点改名后的新旧路径验证。"""

    def test_old_v5_status_returns_404(self, auth_client):
        """旧路径 GET /memory/v5/status → 404。"""
        resp = auth_client.get("/api/webui/memory/v5/status")
        assert resp.status_code == 404, f"旧路径应 404: {resp.status_code}"

    def test_new_status_accessible(self, auth_client):
        """新路径 GET /memory/status 可访问（非 404；A_memorix 未初始化可能抛异常）。"""
        try:
            resp = auth_client.get("/api/webui/memory/status")
            assert resp.status_code != 404, f"新路径不应 404: {resp.status_code}"
        except RuntimeError as e:
            assert "A_memorix" in str(e) or "配置管理器" in str(e), f"非预期异常: {e}"

    def test_old_delete_execute_returns_404(self, auth_client):
        """旧路径 POST /memory/delete/execute → 404。"""
        resp = auth_client.post(
            "/api/webui/memory/delete/execute",
            json={"mode": "paragraph", "selector": {}},
        )
        assert resp.status_code == 404, f"旧路径应 404: {resp.status_code}"

    def test_new_episodes_delete_accessible(self, auth_client):
        """新路径 POST /memory/episodes/{id}/delete 可访问（非 404；A_memorix 可能抛异常）。"""
        try:
            resp = auth_client.post(
                "/api/webui/memory/episodes/paragraph/delete",
                json={"mode": "paragraph", "selector": {}},
            )
            assert resp.status_code != 404, f"新路径不应 404: {resp.status_code}"
        except RuntimeError as e:
            assert "A_memorix" in str(e) or "配置管理器" in str(e), f"非预期异常: {e}"

    def test_purge_without_cascade_returns_409(self, auth_client):
        """POST /memory/maintenance/purge 无 cascade → 409。"""
        resp = auth_client.post(
            "/api/webui/memory/maintenance/purge",
            json={"grace_hours": 24, "limit": 100},
        )
        assert resp.status_code == 409, f"无 cascade 应 409: {resp.status_code}: {resp.text}"

    def test_purge_with_cascade_accessible(self, auth_client):
        """POST /memory/maintenance/purge?cascade=true 可访问（非 409；A_memorix 可能抛异常）。"""
        try:
            resp = auth_client.post(
                "/api/webui/memory/maintenance/purge?cascade=true",
                json={"grace_hours": 24, "limit": 100},
            )
            assert resp.status_code != 409, f"有 cascade 不应 409: {resp.status_code}"
        except RuntimeError as e:
            assert "A_memorix" in str(e) or "配置管理器" in str(e), f"非预期异常: {e}"

    def test_episodes_delete_id_mode_mismatch(self, auth_client):
        """POST /memory/episodes/{id}/delete id 与 mode 不一致 → 400。"""
        resp = auth_client.post(
            "/api/webui/memory/episodes/wrong_mode/delete",
            json={"mode": "paragraph", "selector": {}},
        )
        assert resp.status_code == 400, f"id/mode 不一致应 400: {resp.status_code}: {resp.text}"
