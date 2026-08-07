"""Expression 路由未认证访问测试 — 只读端点未认证应返回 401。"""


class TestExpressionAuth:
    """Expression 未认证访问测试。"""

    def test_unauth_get_expression_list(self, client):
        """未认证访问 GET /expression/list → 401。"""
        resp = client.get("/api/webui/expression/list")
        assert resp.status_code == 401

    def test_unauth_get_expression_detail(self, client):
        """未认证访问 GET /expression/{id} → 401。"""
        resp = client.get("/api/webui/expression/1")
        assert resp.status_code == 401

    def test_unauth_get_expression_stats(self, client):
        """未认证访问 GET /expression/stats/summary → 401。"""
        resp = client.get("/api/webui/expression/stats/summary")
        assert resp.status_code == 401

    def test_unauth_get_expression_groups(self, client):
        """未认证访问 GET /expression/groups → 401。"""
        resp = client.get("/api/webui/expression/groups")
        assert resp.status_code == 401

    def test_unauth_get_review_stats(self, client):
        """未认证访问 GET /expression/review/stats → 401。"""
        resp = client.get("/api/webui/expression/review/stats")
        assert resp.status_code == 401

    def test_unauth_get_review_list(self, client):
        """未认证访问 GET /expression/review/list → 401。"""
        resp = client.get("/api/webui/expression/review/list")
        assert resp.status_code == 401