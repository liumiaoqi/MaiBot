"""Agent 双写事务回滚测试（P1-4 / R1 缓解）。

验证 bind_session_agent 端点在数据库写入失败时，
内存路由器写入被回滚（unbind_session 被调用）。
"""

from unittest.mock import patch, MagicMock


class TestAgentRollback:
    """双写事务回滚验证。"""

    def test_bind_db_failure_triggers_unbind(self, auth_client):
        """DB 写入失败 → 内存路由器回滚（unbind 被调用）。"""
        mock_agent_router = MagicMock()
        mock_registry = MagicMock()
        mock_registry.has_agent.return_value = True
        mock_registry.get_agent.return_value = MagicMock(
            agent_id="test-agent", name="Test", display_name="Test"
        )

        with patch("src.webui.routers.agent._get_registry", return_value=mock_registry), \
             patch("src.webui.routers.agent._get_agent_router", return_value=mock_agent_router), \
             patch("src.webui.routers.agent._set_session_agent_binding", side_effect=Exception("模拟 DB 写入失败")):

            auth_client.put(
                "/api/webui/agent/binding/session/test-session",
                json={"agent_id": "test-agent"},
            )

            mock_agent_router.bind_session.assert_called_once_with("test-session", "test-agent")
            mock_agent_router.unbind_session.assert_called_once_with("test-session", "test-agent")

    def test_bind_success_no_unbind(self, auth_client):
        """DB 写入成功 → 不触发回滚（unbind 不被调用）。"""
        mock_agent_router = MagicMock()
        mock_registry = MagicMock()
        mock_registry.has_agent.return_value = True
        mock_registry.get_agent.return_value = MagicMock(
            agent_id="test-agent", name="Test", display_name="Test"
        )

        with patch("src.webui.routers.agent._get_registry", return_value=mock_registry), \
             patch("src.webui.routers.agent._get_agent_router", return_value=mock_agent_router), \
             patch("src.webui.routers.agent._set_session_agent_binding", return_value=None):

            auth_client.put(
                "/api/webui/agent/binding/session/test-session",
                json={"agent_id": "test-agent"},
            )

            mock_agent_router.bind_session.assert_called_once_with("test-session", "test-agent")
            mock_agent_router.unbind_session.assert_not_called()
