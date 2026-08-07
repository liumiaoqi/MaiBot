"""Expression 路由只读集成测试。

覆盖：list / {id} / stats/summary / groups / review/stats / review/list。
全部为 GET 端点，不调用任何写操作。

注：任务描述中的 GET /expression/stats 实际端点为 /expression/stats/summary。
"""

import pytest

from tests.webui.conftest import assert_api_success

_SKIP_REASON = "A_memorix 配置管理器未注入，待 T2.3 fixture 补全后启用"


class TestExpressionRead:
    """Expression 只读端点测试。"""

    def test_get_expression_list(self, auth_client):
        """GET /expression/list — 表达式列表（全部参数有默认值）。"""
        resp = auth_client.get("/api/webui/expression/list")
        assert_api_success(resp)

    def test_get_expression_list_with_pagination(self, auth_client):
        """GET /expression/list — 带分页参数。"""
        resp = auth_client.get(
            "/api/webui/expression/list",
            params={"page": 1, "page_size": 10},
        )
        assert_api_success(resp)

    @pytest.mark.skip(reason=_SKIP_REASON)
    def test_get_expression_detail(self, auth_client):
        """GET /expression/{id} — 表达式详情（用任意有效 id=1）。"""
        resp = auth_client.get("/api/webui/expression/1")
        assert_api_success(resp)

    def test_get_expression_stats(self, auth_client):
        """GET /expression/stats/summary — 统计（include_legacy 有默认值）。"""
        resp = auth_client.get("/api/webui/expression/stats/summary")
        assert_api_success(resp)

    @pytest.mark.skip(reason=_SKIP_REASON)
    def test_get_expression_groups(self, auth_client):
        """GET /expression/groups — 分组（include_legacy 有默认值）。"""
        resp = auth_client.get("/api/webui/expression/groups")
        assert_api_success(resp)

    def test_get_review_stats(self, auth_client):
        """GET /expression/review/stats — 审核统计。"""
        resp = auth_client.get("/api/webui/expression/review/stats")
        assert_api_success(resp)

    def test_get_review_list(self, auth_client):
        """GET /expression/review/list — 审核列表（全部参数有默认值）。"""
        resp = auth_client.get("/api/webui/expression/review/list")
        assert_api_success(resp)

    def test_get_review_list_with_params(self, auth_client):
        """GET /expression/review/list — 带分页和筛选参数。"""
        resp = auth_client.get(
            "/api/webui/expression/review/list",
            params={"page": 1, "page_size": 10, "filter_type": "unchecked"},
        )
        assert_api_success(resp)