from src.config.legacy_migration import try_migrate_legacy_bot_config_dict


def test_legacy_empty_qq_account_is_migrated_to_zero():
    payload = {"bot": {"qq_account": ""}}

    result = try_migrate_legacy_bot_config_dict(payload)

    assert result.migrated is True
    assert "bot.qq_account_empty" in result.reason
    assert result.data["bot"]["qq_account"] == 0


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


def test_legacy_learning_list_with_string_bool_fourth_column_is_migrated():
    payload = {"expression": {"learning_list": [["qq::group", "enable", "enable", "true"]]}}

    result = try_migrate_legacy_bot_config_dict(payload)

    assert result.migrated is True
    assert "expression.learning_list" in result.reason
    assert result.data["expression"]["learning_list"] == [
        {
            "platform": "qq",
            "item_id": "",
            "rule_type": "group",
            "use_expression": True,
            "enable_learning": True,
            "enable_jargon_learning": True,
        }
    ]


def test_legacy_expression_groups_empty_string_is_migrated():
    payload = {"expression": {"expression_groups": ""}}

    result = try_migrate_legacy_bot_config_dict(payload)

    assert result.migrated is True
    assert "expression.expression_groups" in result.reason
    assert result.data["expression"]["expression_groups"] == []


def test_legacy_expression_groups_global_marker_is_migrated():
    payload = {"expression": {"expression_groups": [["*"]]}}

    result = try_migrate_legacy_bot_config_dict(payload)

    assert result.migrated is True
    assert "expression.expression_groups" in result.reason
    assert result.data["expression"]["expression_groups"] == [
        {
            "expression_groups": [
                {
                    "platform": "*",
                    "item_id": "*",
                    "rule_type": "group",
                }
            ]
        }
    ]


def test_empty_keyword_rules_are_dropped():
    payload = {
        "keyword_reaction": {
            "keyword_rules": [
                {"keywords": [], "reaction": ""},
                {"keywords": ["test"], "reaction": "ok"},
            ]
        }
    }

    result = try_migrate_legacy_bot_config_dict(payload)

    assert result.migrated is True
    assert "keyword_reaction.keyword_rules_empty" in result.reason
    assert result.data["keyword_reaction"]["keyword_rules"] == [{"keywords": ["test"], "reaction": "ok"}]


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
