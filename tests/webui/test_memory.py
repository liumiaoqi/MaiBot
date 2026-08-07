"""Memory 路由只读集成测试 — Top 20 核心端点中的只读部分。

覆盖：graph / graph/search / timeline / query/aggregate / config / delete/operations / profiles。
全部为 GET 端点，不调用任何写操作。
"""

import pytest

from tests.webui.conftest import assert_api_success

_SKIP_REASON = "A_memorix 配置管理器未注入，待 T2.3 fixture 补全后启用"


class TestMemoryRead:
    """Memory 只读端点测试。"""

    @pytest.mark.skip(reason=_SKIP_REASON)
    def test_get_memory_graph(self, auth_client):
        """GET /memory/graph — 记忆图谱（limit 有默认值，可不传）。"""
        resp = auth_client.get("/api/webui/memory/graph")
        assert_api_success(resp)

    @pytest.mark.skip(reason=_SKIP_REASON)
    def test_get_memory_graph_with_limit(self, auth_client):
        """GET /memory/graph — 指定 limit 参数。"""
        resp = auth_client.get("/api/webui/memory/graph", params={"limit": 100})
        assert_api_success(resp)

    @pytest.mark.skip(reason=_SKIP_REASON)
    def test_search_memory_graph(self, auth_client):
        """GET /memory/graph/search — 图谱搜索（query 必填）。"""
        resp = auth_client.get(
            "/api/webui/memory/graph/search", params={"query": "测试", "limit": 10}
        )
        assert_api_success(resp)

    @pytest.mark.skip(reason=_SKIP_REASON)
    def test_get_memory_timeline(self, auth_client):
        """GET /memory/timeline — 时间线（chat_id 必填）。"""
        resp = auth_client.get(
            "/api/webui/memory/timeline", params={"chat_id": "test_chat", "limit": 10}
        )
        assert_api_success(resp)

    @pytest.mark.skip(reason=_SKIP_REASON)
    def test_query_memory_aggregate(self, auth_client):
        """GET /memory/query/aggregate — 聚合查询（全部参数有默认值）。"""
        resp = auth_client.get("/api/webui/memory/query/aggregate")
        assert_api_success(resp)

    @pytest.mark.skip(reason=_SKIP_REASON)
    def test_query_memory_aggregate_with_params(self, auth_client):
        """GET /memory/query/aggregate — 带查询参数的聚合查询。"""
        resp = auth_client.get(
            "/api/webui/memory/query/aggregate",
            params={"query": "测试", "limit": 5},
        )
        assert_api_success(resp)

    @pytest.mark.skip(reason=_SKIP_REASON)
    def test_get_memory_config(self, auth_client):
        """GET /memory/config — 记忆配置。"""
        resp = auth_client.get("/api/webui/memory/config")
        assert_api_success(resp)

    @pytest.mark.skip(reason=_SKIP_REASON)
    def test_list_memory_delete_operations(self, auth_client):
        """GET /memory/delete/operations — 删除操作列表。"""
        resp = auth_client.get("/api/webui/memory/delete/operations")
        assert_api_success(resp)

    @pytest.mark.skip(reason=_SKIP_REASON)
    def test_list_memory_delete_operations_with_params(self, auth_client):
        """GET /memory/delete/operations — 带 limit/mode 参数。"""
        resp = auth_client.get(
            "/api/webui/memory/delete/operations",
            params={"limit": 20, "mode": ""},
        )
        assert_api_success(resp)

    @pytest.mark.skip(reason=_SKIP_REASON)
    def test_list_memory_profiles(self, auth_client):
        """GET /memory/profiles — 人物画像列表。"""
        resp = auth_client.get("/api/webui/memory/profiles")
        assert_api_success(resp)

    @pytest.mark.skip(reason=_SKIP_REASON)
    def test_list_memory_profiles_with_limit(self, auth_client):
        """GET /memory/profiles — 指定 limit 参数。"""
        resp = auth_client.get(
            "/api/webui/memory/profiles", params={"limit": 20}
        )
        assert_api_success(resp)