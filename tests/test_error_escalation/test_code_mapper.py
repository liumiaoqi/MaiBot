"""ZG-14 Phase 5 — 错误码 → ErrorLevel 映射测试（code_mapper + LLM 接线）。

验证（survey 0805 §5.3 / 任务验收）：
- 永久性错误码 → ERROR：400/401/403/404（+ ZG-12 定稿全量永久表）
- 暂时性错误码 → WARN：429/500/502/503/504（+ ZG-12 定稿全量暂时表）
- 超时/连接类异常 → WARN
- 未收录错误码/未知异常 → WARN 兜底（spec §5.6.3 异常场景 1）
- LLM 调用错误路径接线：_report_http_error_to_escalation 按映射上报
"""

from unittest.mock import MagicMock

from src.core.error_escalation.code_mapper import classify_exception, classify_http_status
from src.core.error_escalation.types import ErrorLevel
from src.core.error_escalation_port_registry import (
    reset_error_escalation_port,
    set_error_escalation_port,
)
from src.llm_models.error_classifier import PERMANENT_ERROR_CODES, TRANSIENT_ERROR_CODES
from src.llm_models.exceptions import (
    EmptyResponseException,
    LLMTaskTimeoutError,
    NetworkConnectionError,
    ReqAbortException,
    RespNotOkException,
    RespParseException,
)


class TestClassifyHttpStatus:
    """HTTP 状态码 → ErrorLevel 映射表（ZG-12 定稿 + 任务验收点）。"""

    def test_permanent_codes_map_to_error(self) -> None:
        """永久性错误码 → ERROR（任务验收：400/401/403/404 + 全量表）。"""
        for code in PERMANENT_ERROR_CODES:
            assert classify_http_status(code) is ErrorLevel.ERROR, f"status {code} 应为 ERROR"
        for code in (400, 401, 403, 404):
            assert classify_http_status(code) is ErrorLevel.ERROR

    def test_transient_codes_map_to_warn(self) -> None:
        """暂时性错误码 → WARN（任务验收：429/500/502/503/504 + 全量表）。"""
        for code in TRANSIENT_ERROR_CODES:
            assert classify_http_status(code) is ErrorLevel.WARN, f"status {code} 应为 WARN"
        for code in (429, 500, 502, 503, 504):
            assert classify_http_status(code) is ErrorLevel.WARN

    def test_unknown_code_falls_back_warn(self) -> None:
        """未收录错误码 → WARN 兜底（spec §5.6.3 异常场景 1 同款）。"""
        for code in (418, 451, 501, 509, 999, 200, 0):
            assert classify_http_status(code) is ErrorLevel.WARN

    def test_sets_are_disjoint(self) -> None:
        """永久/暂时表互斥（错误码定稿一致性）。"""
        assert PERMANENT_ERROR_CODES.isdisjoint(TRANSIENT_ERROR_CODES)


class TestClassifyException:
    """异常类型粗分 → ErrorLevel（survey :764「ZG-16 可先用异常类型粗分」）。"""

    def test_status_code_exception_delegates_to_http_mapping(self) -> None:
        """携带 status_code 的异常委托 classify_http_status（永久→ERROR）。"""
        assert classify_exception(RespNotOkException(401)) is ErrorLevel.ERROR
        assert classify_exception(RespNotOkException(404)) is ErrorLevel.ERROR
        assert classify_exception(RespNotOkException(400)) is ErrorLevel.ERROR

    def test_status_code_exception_transient_warn(self) -> None:
        """携带 status_code 的异常委托 classify_http_status（暂时→WARN）。"""
        assert classify_exception(RespNotOkException(429)) is ErrorLevel.WARN
        assert classify_exception(RespNotOkException(503)) is ErrorLevel.WARN
        assert classify_exception(RespNotOkException(500)) is ErrorLevel.WARN

    def test_timeout_exception_warn(self) -> None:
        """超时类异常 → WARN（任务验收：超时→WARN）。"""
        assert classify_exception(TimeoutError("timeout")) is ErrorLevel.WARN
        assert classify_exception(LLMTaskTimeoutError("task", "model", 30.0)) is ErrorLevel.WARN

    def test_connection_exception_warn(self) -> None:
        """连接类异常 → WARN（任务验收：连接类→WARN）。"""
        assert classify_exception(ConnectionError("reset")) is ErrorLevel.WARN
        assert classify_exception(ConnectionResetError("reset")) is ErrorLevel.WARN
        assert classify_exception(NetworkConnectionError("net down")) is ErrorLevel.WARN

    def test_retryable_response_exception_warn(self) -> None:
        """空响应/解析失败/请求中断（调用方按可重试处理）→ WARN。"""
        assert classify_exception(EmptyResponseException()) is ErrorLevel.WARN
        assert classify_exception(RespParseException()) is ErrorLevel.WARN
        assert classify_exception(ReqAbortException("aborted")) is ErrorLevel.WARN

    def test_unknown_exception_falls_back_warn(self) -> None:
        """未知异常类型 → WARN 兜底（不低估也不过度升级）。"""
        assert classify_exception(ValueError("boom")) is ErrorLevel.WARN
        assert classify_exception(RuntimeError("boom")) is ErrorLevel.WARN


class TestLLMHttpErrorWiring:
    """LLM 调用错误路径接线：_report_http_error_to_escalation 按映射上报。"""

    def _call(self, status_code: int) -> tuple[MagicMock, MagicMock]:
        from src.llm_models.utils_model import _report_http_error_to_escalation

        port = MagicMock()
        set_error_escalation_port(port)
        exc = RespNotOkException(status_code, f"http {status_code}")
        try:
            _report_http_error_to_escalation(status_code, "模型调用失败", exc)
        finally:
            reset_error_escalation_port()
        return port, exc

    def test_permanent_code_reports_error(self) -> None:
        """永久性错误码接线 → report(ERROR)。"""
        port, exc = self._call(401)
        port.report.assert_called_once()
        assert port.report.call_args.args[0] is ErrorLevel.ERROR
        assert port.report.call_args.kwargs["exception"] is exc

    def test_transient_code_reports_warn(self) -> None:
        """暂时性错误码接线 → report(WARN)。"""
        port, _ = self._call(429)
        port.report.assert_called_once()
        assert port.report.call_args.args[0] is ErrorLevel.WARN

    def test_unregistered_port_skips_silently(self) -> None:
        """port 未注册时静默跳过，不抛异常（registry 兜底）。"""
        from src.llm_models.utils_model import _report_http_error_to_escalation

        reset_error_escalation_port()
        _report_http_error_to_escalation(401, "模型调用失败", RespNotOkException(401))
