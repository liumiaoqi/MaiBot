from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.config_upgrade_hooks import (
    BOT_CONFIG_UPGRADE_HOOKS,
    ConfigUpgradeHook,
    apply_config_upgrade_hooks,
    set_nested_config_value,
)
from src.config.official_configs import ChatConfig

import src.config.config_upgrade_hooks as hooks


def test_apply_config_upgrade_hooks_runs_when_target_version_is_crossed(monkeypatch):
    def migrate(data):
        changed = set_nested_config_value(data, ("chat", "enable"), False)
        return ["chat.enable"] if changed else []

    monkeypatch.setattr(
        hooks,
        "BOT_CONFIG_UPGRADE_HOOKS",
        (ConfigUpgradeHook(target_version="8.10.11", config_names=("bot_config.toml",), migrate=migrate),),
    )

    data = {"chat": {"enable": True}}
    result = apply_config_upgrade_hooks(data, "bot_config.toml", "8.10.10", "8.10.11")

    assert result.migrated is True
    assert result.reason == "8.10.11:chat.enable"
    assert result.data["chat"]["enable"] is False


def test_apply_config_upgrade_hooks_skips_versions_outside_upgrade_range(monkeypatch):
    def migrate(data):
        set_nested_config_value(data, ("chat", "enable"), False)
        return ["chat.enable"]

    monkeypatch.setattr(
        hooks,
        "BOT_CONFIG_UPGRADE_HOOKS",
        (ConfigUpgradeHook(target_version="8.10.11", config_names=("bot_config.toml",), migrate=migrate),),
    )

    data = {"chat": {"enable": True}}
    result = apply_config_upgrade_hooks(data, "bot_config.toml", "8.10.11", "8.10.12")

    assert result.migrated is False
    assert result.data["chat"]["enable"] is True


def test_set_nested_config_value_can_keep_existing_value():
    data = {"webui": {"port": 8001}}

    changed = set_nested_config_value(data, ("webui", "port"), 8080, force=False)

    assert changed is False
    assert data["webui"]["port"] == 8001


def test_builtin_hook_resets_group_chat_prompt_when_upgrading_from_8_10_10():
    data = {"chat": {"group_chat_prompt": "自定义旧提示词"}}

    result = apply_config_upgrade_hooks(data, "bot_config.toml", "8.10.10", "8.10.11")

    assert result.migrated is True
    assert result.reason == "8.10.11:chat.group_chat_prompt"
    assert result.data["chat"]["group_chat_prompt"] == ChatConfig().group_chat_prompt


def test_bot_config_upgrade_hooks_register_group_chat_prompt_reset():
    assert len(BOT_CONFIG_UPGRADE_HOOKS) == 1
    assert BOT_CONFIG_UPGRADE_HOOKS[0].target_version == "8.10.11"
