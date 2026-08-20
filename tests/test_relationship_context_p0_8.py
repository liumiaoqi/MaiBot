"""P0-8 验收：关系上报上下文替身端口断言测试。

对应 tasks.md 8.2：验证
1. _load_row 失败 → error_escalation_port.report 收到含 agent_id+user_id 的上下文消息
2. _save_snapshot 失败 → error_escalation_port.report 收到含 agent_id+user_id 的上下文消息
3. _on_relationship_upgrade 回调失败 → error_escalation_port.report 收到含 snapshot 上下文
4. _get_growth_rate 失败 → error_escalation_port.report 收到含 agent_id 的上下文
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.error_escalation.types import ErrorLevel


@pytest.fixture
def mock_error_port():
    """替身 error_escalation_port，捕获 report 调用。"""
    from src.core.error_escalation_port_registry import set_error_escalation_port

    port = MagicMock()
    port.report = MagicMock()
    set_error_escalation_port(port)
    yield port
    # 还原：设回 None 让后续测试不受影响
    set_error_escalation_port(None)


def test_load_row_failure_reports_agent_user_context(mock_error_port) -> None:
    """_load_row 异常 → report 消息含 agent_id 和 user_id。"""
    from src.maisaka.relationship.manager import RelationshipManager

    with patch("src.maisaka.relationship.manager.get_db_session") as mock_session:
        mock_session.side_effect = RuntimeError("db down")
        RelationshipManager._load_row("agent-x", "user-y")

    mock_error_port.report.assert_called_once()
    call_args = mock_error_port.report.call_args
    msg = call_args.args[1]
    assert "agent-x" in msg, f"上报消息应含 agent_id: {msg}"
    assert "user-y" in msg, f"上报消息应含 user_id: {msg}"
    assert call_args.args[0] == ErrorLevel.WARNING


def test_save_snapshot_failure_reports_agent_user_context(mock_error_port) -> None:
    """_save_snapshot 异常 → report 消息含 agent_id 和 user_id。"""
    from src.maisaka.relationship.level import RelationshipLevel, RelationshipSnapshot
    from src.maisaka.relationship.manager import RelationshipManager

    snapshot = RelationshipSnapshot(
        agent_id="agent-a",
        user_id="user-b",
        score=100.0,
        level=RelationshipLevel.ACQUAINTANCE,
    )

    with patch("src.maisaka.relationship.manager.get_db_session") as mock_session:
        mock_session.side_effect = RuntimeError("db down")
        RelationshipManager._save_snapshot("agent-a", "user-b", snapshot)

    mock_error_port.report.assert_called_once()
    call_args = mock_error_port.report.call_args
    msg = call_args.args[1]
    assert "agent-a" in msg, f"上报消息应含 agent_id: {msg}"
    assert "user-b" in msg, f"上报消息应含 user_id: {msg}"


def test_upgrade_callback_failure_reports_snapshot_context(mock_error_port) -> None:
    """_on_relationship_upgrade 回调异常 → report 消息含 snapshot.agent_id 和 user_id。"""
    from src.maisaka.relationship.level import RelationshipLevel, RelationshipSnapshot
    from src.maisaka.relationship.manager import RelationshipManager

    snapshot = RelationshipSnapshot(
        agent_id="agent-up",
        user_id="user-up",
        score=500.0,
        level=RelationshipLevel.FAMILIAR,
    )

    manager = RelationshipManager()
    # 设置会抛异常的回调
    manager.set_emotion_trigger_callback(MagicMock(side_effect=RuntimeError("callback boom")))

    manager._on_relationship_upgrade(snapshot, RelationshipLevel.ACQUAINTANCE)

    mock_error_port.report.assert_called_once()
    call_args = mock_error_port.report.call_args
    msg = call_args.args[1]
    assert "agent-up" in msg, f"上报消息应含 snapshot.agent_id: {msg}"
    assert "user-up" in msg, f"上报消息应含 snapshot.user_id: {msg}"


def test_get_growth_rate_failure_reports_agent_context(mock_error_port) -> None:
    """_get_growth_rate 异常 → report 消息含 agent_id。"""
    from src.maisaka.relationship.manager import RelationshipManager

    with patch(
        "src.core.adapters.agent_config_port.get_agent_config_provider"
    ) as mock_provider:
        mock_provider.side_effect = RuntimeError("provider down")
        RelationshipManager._get_growth_rate("agent-g")

    mock_error_port.report.assert_called_once()
    call_args = mock_error_port.report.call_args
    msg = call_args.args[1]
    assert "agent-g" in msg, f"上报消息应含 agent_id: {msg}"