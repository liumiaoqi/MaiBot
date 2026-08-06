"""T12 配置域测试 — ControlMessageSectionConfig 模型 + AppConfigPort 转发。"""

import pytest

from src.config.official_configs import ControlMessageSectionConfig


class TestControlMessageSectionConfig:
    def test_defaults(self) -> None:
        """默认值与 design §9.1 一致。"""
        cfg = ControlMessageSectionConfig()
        assert cfg.version == 1
        assert cfg.global_enabled is False
        assert cfg.unmaskable_whitelist == [1, 2, 3]
        assert cfg.private_queue_limit == 256
        assert cfg.shared_queue_limit == 1024
        assert cfg.unkillable_entities == ["agent:primary", "component:orchestrator", "component:message_port"]
        assert cfg.system_blocked_kinds == []
        assert cfg.system_ignored_kinds == []
        assert cfg.delivery_history_limit == 100
        assert cfg.diffuse_timeout_sec == 5.0
        assert cfg.force_caller_whitelist == [
            "watchdog",
            "service_manager",
            "system_state_machine",
            "error_escalation",  # ZG-14：FATAL 级 STOP_CORE 前扩散取消信号
        ]

    def test_custom_values(self) -> None:
        cfg = ControlMessageSectionConfig(
            global_enabled=True,
            unmaskable_whitelist=[1, 2, 3],
            private_queue_limit=128,
            system_blocked_kinds=[12],
        )
        assert cfg.global_enabled is True
        assert cfg.private_queue_limit == 128
        assert cfg.system_blocked_kinds == [12]


class TestAppConfigPortForwarding:
    @pytest.fixture(autouse=True)
    def _init_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """注入 fake config_manager（global_config 为延迟代理；不走 initialize_config，
        因其触发配置升级钩子路径，而 config_upgrade_hooks 存在既有 bug
        （_add_subagent_section_config 少传参数，与 T12 无关）。"""
        from src.config.config import Config

        class _FakeManager:
            def get_global_config(self) -> Config:
                return Config()

            def get_model_config(self) -> Config:
                return Config()

        monkeypatch.setattr("src.config.config.config_manager", _FakeManager())

    def test_forwarding_defaults(self) -> None:
        """GlobalConfigAppConfigPort 转发：未配置时返回默认值（渐进启用）。"""
        from src.core.adapters.app_config_port import GlobalConfigAppConfigPort

        port = GlobalConfigAppConfigPort()
        assert port.get_control_message_global_enabled() is False
        assert port.get_control_message_unmaskable_whitelist() == {1, 2, 3}
        assert port.get_control_message_private_queue_limit() == 256
        assert port.get_control_message_shared_queue_limit() == 1024
        assert port.get_control_message_unkillable_entities() == [
            "agent:primary",
            "component:orchestrator",
            "component:message_port",
        ]
        assert port.get_control_message_system_blocked_kinds() == set()
        assert port.get_control_message_system_ignored_kinds() == set()
        assert port.get_control_message_delivery_history_limit() == 100
        assert port.get_control_message_diffuse_timeout_sec() == 5.0
        assert port.get_control_message_force_caller_whitelist() == {
            "watchdog",
            "service_manager",
            "system_state_machine",
            "error_escalation",  # ZG-14：FATAL 级 STOP_CORE 前扩散取消信号
        }
