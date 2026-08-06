"""ZG-14 Phase 4 回归测试（A_memorix 域）— web_import_manager 渐进改造。

放 pytests/A_memorix_test/（per-file-ignores 豁免 TID251——测试直测
A_memorix 内部实现，项目惯例见 pyproject 注释）。

验证：fallback 触发时 ErrorEscalationPort.report 被调且原返回值不变；
registry 未注册时改造路径不抛异常。
"""

from unittest.mock import MagicMock

from src.core.error_escalation.types import ErrorLevel
from src.core.error_escalation_port_registry import (
    reset_error_escalation_port,
    set_error_escalation_port,
)


def test_web_import_manager_fallback_reports_and_keeps_default(tmp_path) -> None:
    """web_import_manager 降级路径上报 ERROR 且原返回值不变。"""
    from src.A_memorix.core.utils.web_import_manager import ImportTaskManager

    port = MagicMock()
    set_error_escalation_port(port)
    manager = object.__new__(ImportTaskManager)
    manager._manifest_cache = None
    manager._manifest_path = tmp_path / "bad_manifest.json"
    manager._manifest_path.write_text("{invalid json", encoding="utf-8")

    result = manager._load_manifest()

    assert result is None
    port.report.assert_called_once()
    assert port.report.call_args.args[0] is ErrorLevel.ERROR
    assert "加载导入清单失败" in port.report.call_args.args[1]
    assert isinstance(port.report.call_args.kwargs["exception"], Exception)
    reset_error_escalation_port()


def test_unregistered_port_path_does_not_raise(tmp_path) -> None:
    """registry 未注册时改造路径不抛异常，fallback 原样执行。"""
    from src.A_memorix.core.utils.web_import_manager import ImportTaskManager

    reset_error_escalation_port()
    manager = object.__new__(ImportTaskManager)
    manager._manifest_cache = None
    manager._manifest_path = tmp_path / "bad_manifest.json"
    manager._manifest_path.write_text("{invalid json", encoding="utf-8")

    assert manager._load_manifest() is None
