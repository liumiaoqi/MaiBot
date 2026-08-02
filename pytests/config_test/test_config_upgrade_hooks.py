from src.config.config_upgrade_hooks import apply_config_upgrade_hooks


def test_split_chat_config_sections_upgrade_hook():
    config_data = {
        "chat": {
            "talk_value": 0.4,
            "private_talk_value": 0.8,
            "reply_trigger_mode": "frequency",
            "enable_talk_value_rules": True,
            "talk_value_rules": [
                {
                    "platform": "",
                    "item_id": "",
                    "rule_type": "group",
                    "time": "*",
                    "value": 0.5,
                }
            ],
            "enable_reply_quote": False,
            "group_chat_prompt": "group prompt",
            "private_chat_prompts": "private prompt",
            "chat_prompts": [],
            "max_context_size": 40,
        }
    }

    result = apply_config_upgrade_hooks(
        config_data,
        config_name="bot_config.toml",
        old_ver="8.14.18",
        new_ver="8.14.19",
    )

    chat_config = result.data["chat"]
    assert result.migrated is True
    assert chat_config["max_context_size"] == 40
    assert chat_config["reply_timing"]["talk_value"] == 0.4
    assert chat_config["reply_timing"]["private_talk_value"] == 0.8
    assert chat_config["reply_timing"]["reply_trigger_mode"] == "frequency"
    assert chat_config["reply_timing"]["enable_talk_value_rules"] is True
    assert chat_config["reply_timing"]["talk_value_rules"][0]["value"] == 0.5
    assert chat_config["reply_style"]["enable_reply_quote"] is False
    assert chat_config["reply_style"]["group_chat_prompt"] == "group prompt"
    assert chat_config["reply_style"]["private_chat_prompts"] == "private prompt"
    assert chat_config["reply_style"]["chat_prompts"] == []
    assert "talk_value" not in chat_config
    assert "group_chat_prompt" not in chat_config


def test_no_dead_subagent_hook():
    """8.17.0 subagent 升级钩子已移除（subagent 功能整体删除于 f63ca9bf1，
    配置模型从未存在；死钩子会在任何版本升级路径抛 TypeError——B 类 T1 修复）。"""
    from src.config.config_upgrade_hooks import BOT_CONFIG_UPGRADE_HOOKS

    for hook in BOT_CONFIG_UPGRADE_HOOKS:
        assert hook.target_version != "8.17.0", "死钩子 _add_subagent_section_config 未移除"


def test_upgrade_hooks_no_typeerror_on_empty():
    """升级钩子链对空配置不抛 TypeError（死钩子移除后升级路径畅通）。"""
    from src.config.config_upgrade_hooks import apply_config_upgrade_hooks

    result = apply_config_upgrade_hooks(
        {},
        config_name="bot_config.toml",
        old_ver="8.16.0",
        new_ver="8.18.0",
    )
    # 不抛异常即通过；subagent 钩子已删，不应产生 subagent 节
    assert "subagent" not in result.data
