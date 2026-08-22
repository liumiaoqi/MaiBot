"""app.py t() 字面量修正测试（T3.5/T3.9）。

验证 app.py 4 处错误报告路径使用 t() 函数调用而非 "t('...')" 字面量
（P0-A24b-1 修复）。
"""


import inspect
from unittest.mock import MagicMock, patch

import pytest


class TestAppErrorReportSource:
    """app.py 源代码 t() 调用检查。"""

    def test_no_string_literal_t_call(self):
        """app.py 源代码中不存在 "t('...')" 字面量。"""
        from src.webui import app

        source = inspect.getsource(app)
        assert '"t(\'' not in source

    def test_error_report_uses_t_function_call(self):
        """4 处错误报告路径均使用 t() 函数调用。"""
        from src.webui import app

        source = inspect.getsource(app)
        assert 't("startup.webui_anti_crawler_config_failed"' in source
        assert 't("startup.webui_robots_route_register_failed"' in source
        assert 't("startup.webui_api_routes_register_failed"' in source
        assert 't("startup.webui_access_token_failed"' in source


class TestAppErrorReportRuntime:
    """app.py 错误路径运行时行为测试。"""

    def test_robots_txt_error_reports_t_translated_string(self):
        """_setup_robots_txt 错误路径通过 t() 函数报告（非字面量）。"""
        from src.webui.app import _setup_robots_txt

        mock_port = MagicMock()
        mock_app = MagicMock()
        mock_app.get = MagicMock(side_effect=Exception("route register failed"))

        with patch(
            "src.core.error_escalation_port_registry.get_error_escalation_port",
            return_value=mock_port,
        ):
            _setup_robots_txt(mock_app)

        assert mock_port.report.called
        call_args = mock_port.report.call_args
        message = call_args[0][1]
        assert not message.startswith("t('")
        assert isinstance(message, str)
