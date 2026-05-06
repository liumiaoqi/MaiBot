"""
legacy_migration.py

旧配置兼容层。
仅保留当前仍需要的“解析前结构修复”，避免老配置在 `from_dict` 前直接失败。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import os


ENABLE_LEGACY_MIGRATION: bool = True


@dataclass
class MigrationResult:
    data: dict[str, Any]
    migrated: bool
    reason: str = ""


def _as_dict(x: Any) -> Optional[dict[str, Any]]:
    return x if isinstance(x, dict) else None


def _as_list(x: Any) -> Optional[list[Any]]:
    return x if isinstance(x, list) else None


def _parse_host_env(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None

    normalized_value = value.strip()
    return normalized_value or None


def _parse_port_env(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None

    try:
        normalized_value = int(str(value).strip())
    except (TypeError, ValueError):
        return None

    if normalized_value <= 0 or normalized_value > 65535:
        return None
    return normalized_value


def _migrate_env_value(section: dict[str, Any], key: str, parsed_env_value: Any, default_value: Any) -> bool:
    if parsed_env_value is None:
        return False

    current_value = section.get(key)
    if current_value == parsed_env_value:
        return False
    if key in section and current_value != default_value:
        return False

    section[key] = parsed_env_value
    return True


def _parse_triplet_target(s: str) -> Optional[dict[str, str]]:
    """
    解析 "platform:id:type" -> {platform, item_id, rule_type}
    """
    if not isinstance(s, str):
        return None

    parts = s.split(":", 2)
    if len(parts) != 3:
        return None

    platform, item_id, rule_type = parts
    if rule_type not in ("group", "private"):
        return None
    return {"platform": platform, "item_id": item_id, "rule_type": rule_type}


def _parse_expression_group_target(s: str) -> Optional[dict[str, str]]:
    """
    解析表达互通组目标，兼容旧版 "*" 全局共享标记。
    """
    if not isinstance(s, str):
        return None

    normalized_value = s.strip()
    if normalized_value == "*":
        return {"platform": "*", "item_id": "*", "rule_type": "group"}

    return _parse_triplet_target(normalized_value)


def _parse_enable_disable(v: Any) -> Optional[bool]:
    """
    兼容旧值 "enable"/"disable" 以及 bool。
    """
    if isinstance(v, bool):
        return v

    if isinstance(v, str):
        normalized_value = v.strip().lower()
        if normalized_value in {"enable", "true"}:
            return True
        if normalized_value in {"disable", "false"}:
            return False

    return None


def _migrate_expression_learning_list(expr: dict[str, Any]) -> bool:
    """
    将旧版 expression.learning_list 转成当前结构。
    """
    learning_list = _as_list(expr.get("learning_list"))
    if learning_list is None:
        return False
    if learning_list and all(isinstance(item, dict) for item in learning_list):
        return False

    migrated_items: list[dict[str, Any]] = []
    for row in learning_list:
        row_items = _as_list(row)
        if row_items is None or len(row_items) < 4:
            return False

        target_raw = row_items[0]
        use_expression = _parse_enable_disable(row_items[1])
        enable_learning = _parse_enable_disable(row_items[2])
        enable_jargon_learning = _parse_enable_disable(row_items[3])

        if enable_jargon_learning is None:
            # 更早期版本第 4 列是已废弃的数值阈值，这里仅做保守兼容。
            try:
                float(str(row_items[3]))
            except (TypeError, ValueError):
                pass
            else:
                enable_jargon_learning = False

        if use_expression is None or enable_learning is None or enable_jargon_learning is None:
            return False

        if target_raw == "" or target_raw is None:
            target = {"platform": "", "item_id": "", "rule_type": "group"}
        else:
            target = _parse_triplet_target(str(target_raw))
            if target is None:
                return False

        migrated_items.append(
            {
                "platform": target["platform"],
                "item_id": target["item_id"],
                "rule_type": target["rule_type"],
                "use_expression": use_expression,
                "enable_learning": enable_learning,
                "enable_jargon_learning": enable_jargon_learning,
            }
        )

    expr["learning_list"] = migrated_items
    return True


def _migrate_chat_talk_value_rules(chat: dict[str, Any]) -> bool:
    """
    将旧版 target 字段迁移为当前运行时使用的 platform/item_id/rule_type 结构。
    """
    talk_value_rules = _as_list(chat.get("talk_value_rules"))
    if talk_value_rules is None:
        return False

    migrated = False
    for rule in talk_value_rules:
        rule_item = _as_dict(rule)
        if rule_item is None or "target" not in rule_item:
            continue

        target_raw = rule_item.get("target")
        target = "" if target_raw is None else str(target_raw).strip()
        if not target:
            parsed = {"platform": "", "item_id": "", "rule_type": "group"}
        else:
            parsed = _parse_triplet_target(target)
            if parsed is None:
                continue

        rule_item["platform"] = parsed["platform"]
        rule_item["item_id"] = parsed["item_id"]
        rule_item["rule_type"] = parsed["rule_type"]
        rule_item.pop("target", None)
        migrated = True

    return migrated


def _migrate_expression_groups(expr: dict[str, Any]) -> bool:
    """
    将旧版 expression.expression_groups 转成当前结构。
    """
    raw_expression_groups = expr.get("expression_groups")
    if isinstance(raw_expression_groups, str):
        normalized_value = raw_expression_groups.strip()
        if not normalized_value:
            expr["expression_groups"] = []
            return True

        parsed = _parse_expression_group_target(normalized_value)
        if parsed is None:
            return False

        expr["expression_groups"] = [{"expression_groups": [parsed]}]
        return True

    expression_groups = _as_list(raw_expression_groups)
    if expression_groups is None:
        return False
    if expression_groups and all(isinstance(item, dict) for item in expression_groups):
        return False

    migrated_groups: list[dict[str, Any]] = []
    for group in expression_groups:
        group_items = _as_list(group)
        if group_items is None:
            return False

        targets: list[dict[str, str]] = []
        for item in group_items:
            parsed = _parse_expression_group_target(str(item))
            if parsed is None:
                return False
            targets.append(parsed)

        migrated_groups.append({"expression_groups": targets})

    expr["expression_groups"] = migrated_groups
    return True


def _migrate_target_item_list(parent: dict[str, Any], key: str) -> bool:
    """
    将 list[str] 的 "platform:id:type" 迁移为 list[TargetItem]。
    """
    raw = _as_list(parent.get(key))
    if raw is None or not raw:
        return False
    if all(isinstance(item, dict) for item in raw):
        return False

    targets: list[dict[str, str]] = []
    for item in raw:
        parsed = _parse_triplet_target(str(item))
        if parsed is None:
            return False
        targets.append(parsed)

    parent[key] = targets
    return True


def _drop_empty_keyword_rules(keyword_reaction: dict[str, Any], key: str) -> bool:
    raw = _as_list(keyword_reaction.get(key))
    if raw is None:
        return False

    cleaned_rules: list[Any] = []
    dropped_any = False
    for item in raw:
        item_dict = _as_dict(item)
        if item_dict is None:
            cleaned_rules.append(item)
            continue

        keywords = _as_list(item_dict.get("keywords")) or []
        regex = _as_list(item_dict.get("regex")) or []
        reaction = item_dict.get("reaction")
        if not keywords and not regex and (reaction is None or str(reaction).strip() == ""):
            dropped_any = True
            continue

        cleaned_rules.append(item)

    if not dropped_any:
        return False

    keyword_reaction[key] = cleaned_rules
    return True


def migrate_legacy_bind_env_to_bot_config_dict(data: dict[str, Any]) -> MigrationResult:
    """将旧版 `.env` 中的绑定地址迁移到主配置结构。"""

    migrated_any = False
    reasons: list[str] = []

    main_host_env = _parse_host_env(os.getenv("HOST"))
    main_port_env = _parse_port_env(os.getenv("PORT"))
    maim_message = _as_dict(data.get("maim_message"))
    if maim_message is None and (main_host_env is not None or main_port_env is not None):
        maim_message = {}
        data["maim_message"] = maim_message

    if maim_message is not None and _migrate_env_value(maim_message, "ws_server_host", main_host_env, "127.0.0.1"):
        migrated_any = True
        reasons.append("HOST->maim_message.ws_server_host")
    if maim_message is not None and _migrate_env_value(maim_message, "ws_server_port", main_port_env, 8000):
        migrated_any = True
        reasons.append("PORT->maim_message.ws_server_port")

    webui_host_env = _parse_host_env(os.getenv("WEBUI_HOST"))
    webui_port_env = _parse_port_env(os.getenv("WEBUI_PORT"))
    webui = _as_dict(data.get("webui"))
    if webui is None and (webui_host_env is not None or webui_port_env is not None):
        webui = {}
        data["webui"] = webui

    if webui is not None and _migrate_env_value(webui, "host", webui_host_env, "127.0.0.1"):
        migrated_any = True
        reasons.append("WEBUI_HOST->webui.host")
    if webui is not None and _migrate_env_value(webui, "port", webui_port_env, 8001):
        migrated_any = True
        reasons.append("WEBUI_PORT->webui.port")

    return MigrationResult(data=data, migrated=migrated_any, reason=",".join(reasons))


def try_migrate_legacy_bot_config_dict(data: dict[str, Any]) -> MigrationResult:
    """
    尝试修复 `bot_config.toml` 的少量旧结构，仅保留当前仍需要的兼容逻辑。
    """
    if not ENABLE_LEGACY_MIGRATION:
        return MigrationResult(data=data, migrated=False, reason="disabled")

    migrated_any = False
    reasons: list[str] = []

    bot = _as_dict(data.get("bot"))
    if bot is not None and isinstance(bot.get("qq_account"), int):
        bot["qq_account"] = str(bot["qq_account"]) if bot["qq_account"] > 0 else ""
        migrated_any = True
        reasons.append("bot.qq_account_int_to_string")

    chat = _as_dict(data.get("chat"))
    if chat is not None and _migrate_chat_talk_value_rules(chat):
        migrated_any = True
        reasons.append("chat.talk_value_rules_target")

    expr = _as_dict(data.get("expression"))
    if expr is not None:
        if _migrate_expression_learning_list(expr):
            migrated_any = True
            reasons.append("expression.learning_list")

        if _migrate_expression_groups(expr):
            migrated_any = True
            reasons.append("expression.expression_groups")

        if _migrate_target_item_list(expr, "allow_reflect"):
            migrated_any = True
            reasons.append("expression.allow_reflect")

        manual_reflect_operator_id = expr.get("manual_reflect_operator_id")
        if isinstance(manual_reflect_operator_id, str) and manual_reflect_operator_id.strip():
            parsed = _parse_triplet_target(manual_reflect_operator_id.strip())
            if parsed is not None:
                expr["manual_reflect_operator_id"] = parsed
                migrated_any = True
                reasons.append("expression.manual_reflect_operator_id")

        if isinstance(manual_reflect_operator_id, str) and not manual_reflect_operator_id.strip():
            expr.pop("manual_reflect_operator_id", None)
            migrated_any = True
            reasons.append("expression.manual_reflect_operator_id_empty")

    personality = _as_dict(data.get("personality"))
    visual = _as_dict(data.get("visual"))
    if personality is not None and "visual_style" in personality:
        personality.pop("visual_style", None)
        migrated_any = True
        reasons.append("personality.visual_style_removed")

    if visual is not None and "visual_style" in visual:
        visual.pop("visual_style", None)
        migrated_any = True
        reasons.append("visual.visual_style_removed")

    keyword_reaction = _as_dict(data.get("keyword_reaction"))
    if keyword_reaction is not None:
        if _drop_empty_keyword_rules(keyword_reaction, "keyword_rules"):
            migrated_any = True
            reasons.append("keyword_reaction.keyword_rules_empty")
        if _drop_empty_keyword_rules(keyword_reaction, "regex_rules"):
            migrated_any = True
            reasons.append("keyword_reaction.regex_rules_empty")

    reason = ",".join(reasons)
    return MigrationResult(data=data, migrated=migrated_any, reason=reason)
