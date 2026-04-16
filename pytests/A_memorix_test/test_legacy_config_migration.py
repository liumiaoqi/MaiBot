from src.config.legacy_migration import try_migrate_legacy_bot_config_dict


def test_legacy_learning_list_with_numeric_fourth_column_is_migrated():
    payload = {
        "expression": {
            "learning_list": [
                ["qq:123456:group", "enable", "disable", "0.5"],
                ["", "disable", "enable", "0.1"],
            ]
        }
    }

    result = try_migrate_legacy_bot_config_dict(payload)

    assert result.migrated is True
    assert "expression.learning_list" in result.reason
    assert result.data["expression"]["learning_list"] == [
        {
            "platform": "qq",
            "item_id": "123456",
            "rule_type": "group",
            "use_expression": True,
            "enable_learning": False,
            "enable_jargon_learning": False,
        },
        {
            "platform": "",
            "item_id": "",
            "rule_type": "group",
            "use_expression": False,
            "enable_learning": True,
            "enable_jargon_learning": False,
        },
    ]


def test_visual_multimodal_planner_is_migrated_to_planner_mode():
    payload = {"visual": {"multimodal_planner": True}}

    result = try_migrate_legacy_bot_config_dict(payload)

    assert result.migrated is True
    assert "visual.multimodal_planner_moved_to_visual.planner_mode" in result.reason
    assert result.data["visual"]["planner_mode"] == "multimodal"
    assert "multimodal_planner" not in result.data["visual"]


def test_chat_multimodal_planner_is_migrated_to_visual_planner_mode():
    payload = {"chat": {"multimodal_planner": True}}

    result = try_migrate_legacy_bot_config_dict(payload)

    assert result.migrated is True
    assert "chat.multimodal_planner_moved_to_visual.planner_mode" in result.reason
    assert result.data["visual"]["planner_mode"] == "multimodal"
    assert "multimodal_planner" not in result.data["chat"]


def test_visual_multimodal_replyer_is_migrated_to_replyer_mode():
    payload = {"visual": {"multimodal_replyer": True}}

    result = try_migrate_legacy_bot_config_dict(payload)

    assert result.migrated is True
    assert "visual.multimodal_replyer_moved_to_visual.replyer_mode" in result.reason
    assert result.data["visual"]["replyer_mode"] == "multimodal"
    assert "multimodal_replyer" not in result.data["visual"]


def test_chat_replyer_generator_type_is_migrated_to_replyer_mode():
    payload = {"chat": {"replyer_generator_type": "legacy"}}

    result = try_migrate_legacy_bot_config_dict(payload)

    assert result.migrated is True
    assert "chat.replyer_generator_type_moved_to_visual.replyer_mode" in result.reason
    assert result.data["visual"]["replyer_mode"] == "text"
    assert "replyer_generator_type" not in result.data["chat"]
