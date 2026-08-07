"""Memory 路由未认证访问测试 — 只读端点未认证应返回 401。"""


class TestMemoryAuth:
    """Memory 未认证访问测试。"""

    def test_unauth_get_memory_graph(self, client):
        """未认证访问 GET /memory/graph → 401。"""
        resp = client.get("/api/webui/memory/graph")
        assert resp.status_code == 401

    def test_unauth_search_memory_graph(self, client):
        """未认证访问 GET /memory/graph/search → 401。"""
        resp = client.get(
            "/api/webui/memory/graph/search", params={"query": "测试"}
        )
        assert resp.status_code == 401

    def test_unauth_get_memory_timeline(self, client):
        """未认证访问 GET /memory/timeline → 401。"""
        resp = client.get(
            "/api/webui/memory/timeline", params={"chat_id": "test_chat"}
        )
        assert resp.status_code == 401

    def test_unauth_query_memory_aggregate(self, client):
        """未认证访问 GET /memory/query/aggregate → 401。"""
        resp = client.get("/api/webui/memory/query/aggregate")
        assert resp.status_code == 401

    def test_unauth_get_memory_config(self, client):
        """未认证访问 GET /memory/config → 401。"""
        resp = client.get("/api/webui/memory/config")
        assert resp.status_code == 401

    def test_unauth_list_memory_delete_operations(self, client):
        """未认证访问 GET /memory/delete/operations → 401。"""
        resp = client.get("/api/webui/memory/delete/operations")
        assert resp.status_code == 401

    def test_unauth_list_memory_profiles(self, client):
        """未认证访问 GET /memory/profiles → 401。"""
        resp = client.get("/api/webui/memory/profiles")
        assert resp.status_code == 401