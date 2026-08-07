"""ZG-14 Phase 4 回归测试 — Top 5 降级型文件渐进改造。

验证：fallback 触发时 ErrorEscalationPort.report 被调用且原返回值不变；
registry 未注册时改造路径不抛异常。
"""

from unittest.mock import MagicMock

from src.core.error_escalation.coverage import get_coverage
from src.core.error_escalation.types import ErrorLevel
from src.core.error_escalation_port_registry import (
    reset_error_escalation_port,
    set_error_escalation_port,
)


def _assert_report(port: MagicMock, level: ErrorLevel, message: str) -> None:
    port.report.assert_called_once()
    assert port.report.call_args.args[0] is level
    assert message in port.report.call_args.args[1]
    assert isinstance(port.report.call_args.kwargs["exception"], Exception)


def test_coverage_interface() -> None:
    """覆盖率接口输出与 Phase 4 实际改造数一致。"""
    coverage = get_coverage()
    assert coverage == {
        "reformed_files": 142,
        "reformed_sites": 1207,
        "total_sites": 1494,
    }


def test_runner_main_fallback_reports_and_keeps_default(tmp_path) -> None:
    """runner_main 降级路径上报 CRITICAL 且返回原默认空字典。"""
    from src.plugin_runtime.runner.runner_main import PluginRunner

    port = MagicMock()
    set_error_escalation_port(port)
    config_path = tmp_path / "config.toml"
    config_path.write_bytes(b"invalid = [")

    result = PluginRunner._load_plugin_config(str(tmp_path))

    assert result == {}
    _assert_report(port, ErrorLevel.CRITICAL, "读取插件配置失败")
    reset_error_escalation_port()


async def test_orchestrator_fallback_reports_and_keeps_default(
    monkeypatch,
) -> None:
    """orchestrator 降级路径上报 ERROR 且返回原默认 ("", 0.0)。

    注：orchestrator 的 database_manager 坏 import 已修复为
    `src.common.database.database.get_db_session`（contextmanager）——
    测试 patch get_db_session 注入 db 故障，验证 report 被调 + fallback 不变。
    """
    import contextlib

    import src.common.database.database as database_mod
    from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

    @contextlib.contextmanager
    def _db_down():
        raise RuntimeError("db down")
        yield  # pragma: no cover

    monkeypatch.setattr(database_mod, "get_db_session", _db_down)
    port = MagicMock()
    set_error_escalation_port(port)
    orchestrator = object.__new__(AgentOrchestrator)
    orchestrator._session_id = "test_session"

    result = await orchestrator._load_thought_summary("agent_id")

    assert result == ("", 0.0)
    _assert_report(port, ErrorLevel.ERROR, "读取思考摘要失败")
    reset_error_escalation_port()


async def test_data_capability_fallback_reports_and_keeps_default(
    monkeypatch,
) -> None:
    """data.py 插件能力降级路径上报 ERROR 且返回原错误字典。"""
    import src.common.database.database_model as db_models
    from src.plugin_runtime.capabilities.data import RuntimeDataCapabilityMixin

    async def _db_count(*args, **kwargs) -> None:
        raise RuntimeError("db down")

    # data.py 用 getattr(db_models, model_name) 动态取模型，User 非真实类——
    # 直接挂到模块（raising=False 允许不存在属性）
    monkeypatch.setattr(db_models, "User", type("User", (), {}), raising=False)
    monkeypatch.setattr("src.services.database_service.db_count", _db_count)
    port = MagicMock()
    set_error_escalation_port(port)
    capability = RuntimeDataCapabilityMixin()

    result = await capability._cap_database_count(
        "plugin_id",
        "database.count",
        {"model_name": "User"},
    )

    assert result == {"success": False, "error": "db down"}
    _assert_report(port, ErrorLevel.ERROR, "数据库计数失败")
    reset_error_escalation_port()


def test_unregistered_port_path_does_not_raise(tmp_path) -> None:
    """registry 未注册时改造路径不抛异常，fallback 原样执行。"""
    from src.plugin_runtime.runner.runner_main import PluginRunner

    reset_error_escalation_port()
    config_path = tmp_path / "config.toml"
    config_path.write_bytes(b"invalid = [")
    assert PluginRunner._load_plugin_config(str(tmp_path)) == {}
