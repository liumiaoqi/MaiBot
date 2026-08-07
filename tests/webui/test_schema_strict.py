"""Schema 严格化测试：验证 extra='forbid' 生效，多余字段触发 400。"""

from tests.webui.conftest import assert_api_error


class TestSchemaStrict:
    """Pydantic schema extra='forbid' 契约验证。"""

    def test_expression_create_extra_field(self, auth_client):
        """POST /expression/ 多余字段 → 400。"""
        resp = auth_client.post(
            "/api/webui/expression/",
            json={"content": "test", "unexpected_field": "should_fail"},
        )
        assert resp.status_code == 422, f"多余字段应触发 422: {resp.status_code}: {resp.text}"

    def test_expression_update_extra_field(self, auth_client):
        """PATCH /expression/{id} 多余字段 → 422。"""
        resp = auth_client.patch(
            "/api/webui/expression/1",
            json={"content": "test", "unexpected_field": "should_fail"},
        )
        assert resp.status_code == 422, f"多余字段应触发 422: {resp.status_code}: {resp.text}"

    def test_person_update_extra_field(self, auth_client):
        """PATCH /person/{id} 多余字段 → 422。"""
        resp = auth_client.patch(
            "/api/webui/person/test-id",
            json={"person_name": "test", "unexpected_field": "should_fail"},
        )
        assert resp.status_code == 422, f"多余字段应触发 422: {resp.status_code}: {resp.text}"

    def test_jargon_create_extra_field(self, auth_client):
        """POST /jargon/ 多余字段 → 422。"""
        resp = auth_client.post(
            "/api/webui/jargon/",
            json={"content": "test", "unexpected_field": "should_fail"},
        )
        assert resp.status_code == 422, f"多余字段应触发 422: {resp.status_code}: {resp.text}"

    def test_memory_delete_preview_extra_field(self, auth_client):
        """POST /memory/delete/preview 多余字段 → 422。"""
        resp = auth_client.post(
            "/api/webui/memory/delete/preview",
            json={"mode": "paragraph", "selector": {}, "unexpected_field": "should_fail"},
        )
        assert resp.status_code == 422, f"多余字段应触发 422: {resp.status_code}: {resp.text}"