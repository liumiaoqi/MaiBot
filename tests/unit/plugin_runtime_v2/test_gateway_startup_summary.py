"""GatewayStartupSummaryAdapter 单元测试。"""


from src.plugin_runtime_v2.host.gateway_startup_summary import (
    GatewayStartupSummaryAdapter,
)


class TestGatewayStartupSummaryAdapter:
    def test_report_gateway_status_collects_entries(self):
        adapter = GatewayStartupSummaryAdapter()
        adapter.report_gateway_status(
            plugin_id="napcat-adapter",
            gateway_name="qq_gateway",
            status="registered",
            detail="send=True receive=True",
            platform="qq",
        )
        assert adapter.get_entry_count() == 1

    def test_format_summary_empty_when_no_entries(self):
        adapter = GatewayStartupSummaryAdapter()
        assert adapter.format_summary() == ""

    def test_format_summary_contains_gateway_info(self):
        adapter = GatewayStartupSummaryAdapter()
        adapter.report_gateway_status(
            plugin_id="napcat-adapter",
            gateway_name="qq_gateway",
            status="registered",
            detail="send=True receive=True",
            platform="qq",
        )
        summary = adapter.format_summary()
        assert "napcat-adapter/qq_gateway" in summary
        assert "platform=qq" in summary
        assert "已注册并绑定" in summary

    def test_format_summary_contains_all_status_types(self):
        adapter = GatewayStartupSummaryAdapter()
        adapter.report_gateway_status("p1", "g1", "registered", platform="qq")
        adapter.report_gateway_status("p2", "g2", "failed", detail="超时", platform="qq")
        adapter.report_gateway_status("p3", "g3", "scope_denied", platform="telegram")
        adapter.report_gateway_status("p4", "g4", "not_ready")
        summary = adapter.format_summary()
        assert "已注册并绑定" in summary
        assert "注册失败" in summary
        assert "scope 未授予" in summary
        assert "未就绪" in summary

    def test_duplicate_entry_overwrites(self):
        adapter = GatewayStartupSummaryAdapter()
        adapter.report_gateway_status("p1", "g1", "registered", platform="qq")
        adapter.report_gateway_status("p1", "g1", "not_ready", platform="qq")
        assert adapter.get_entry_count() == 1
        summary = adapter.format_summary()
        assert "未就绪" in summary
        assert "已注册并绑定" not in summary