"""
legacy_migration.py

一个“可随时拔掉”的旧配置兼容层：
- 仅在配置解析失败时尝试修复旧格式数据（7.x -> 8.x 这一类结构性变更）
- 不依赖 Pydantic / ConfigBase，仅对 dict 做最小转换
- 成功则返回(修复后的 dict, True)，失败则返回(原 dict, False)

设计目标：与现有 config 加载逻辑的接触点尽可能小，未来不需要时可一键移除。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import os

from src.common.logger import get_logger

logger = get_logger("legacy_migration")


# 方便未来快速关闭/移除
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
    解析 "platform:id:type" -> {platform,item_id,rule_type}
    返回 None 表示无法解析。
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


def _parse_quad_prompt(s: str) -> Optional[dict[str, str]]:
    """
    解析 "platform:id:type:prompt" -> {platform,item_id,rule_type,prompt}
    prompt 允许包含冒号，因此只切前三个冒号。
    """
    if not isinstance(s, str):
        return None
    parts = s.split(":", 3)
    if len(parts) != 4:
        return None
    platform, item_id, rule_type, prompt = parts
    if rule_type not in ("group", "private"):
        return None
    if not prompt:
        return None
    return {"platform": platform, "item_id": item_id, "rule_type": rule_type, "prompt": prompt}


def _parse_enable_disable(v: Any) -> Optional[bool]:
    """
    兼容旧值 "enable"/"disable" 以及 bool。
    """
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        vv = v.strip().lower()
        if vv == "enable":
            return True
        if vv == "disable":
            return False
    return None


def _migrate_expression_learning_list(expr: dict[str, Any]) -> bool:
    """
    旧：
      learning_list = [
        ["", "enable", "enable", "enable"],
        ["qq:1919810:group", "enable", "enable", "enable"],
      ]
    兼容旧旧格式：
      learning_list = [
        ["qq:1919810:group", "enable", "enable", "0.5"],
        ["", "disable", "disable", "0.1"],
      ]
    新：
      [[expression.learning_list]]
      platform="", item_id="", rule_type="group", use_expression=true, enable_learning=true, enable_jargon_learning=true
    """
    ll = _as_list(expr.get("learning_list"))
    if ll is None:
        return False

    # 如果已经是新格式（列表里是 dict），跳过
    if ll and all(isinstance(i, dict) for i in ll):
        return False

    migrated_items: list[dict[str, Any]] = []
    for row in ll:
        r = _as_list(row)
        if r is None or len(r) < 4:
            # 行结构不对，无法安全迁移
            return False

        target_raw = r[0]
        use_expression = _parse_enable_disable(r[1])
        enable_learning = _parse_enable_disable(r[2])
        enable_jargon_learning = _parse_enable_disable(r[3])
        if enable_jargon_learning is None:
            # 更早期的配置在第 4 列记录的是一个已废弃的数值权重/阈值，
            # 当前 schema 已没有对应字段。这里按保守策略兼容迁移：
            # 丢弃旧数值，并将 enable_jargon_learning 置为 False。
            try:
                float(str(r[3]))
            except (TypeError, ValueError):
                pass
            else:
                enable_jargon_learning = False
        if use_expression is None or enable_learning is None or enable_jargon_learning is None:
            return False

        # 旧格式中 target 允许为空字符串：表示全局；新结构必须有三元组字段
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


def _migrate_expression_groups(expr: dict[str, Any]) -> bool:
    """
    旧：
      expression_groups = [
        ["qq:1:group","qq:2:group"],
        ["qq:3:group"],
      ]
    新：
      expression_groups = [
        { expression_groups = [ {platform="qq", item_id="1", rule_type="group"}, ... ] },
        { expression_groups = [ ... ] },
      ]
    """
    eg = _as_list(expr.get("expression_groups"))
    if eg is None:
        return False

    # 已经是新格式（列表里是 dict 且包含 expression_groups），跳过
    if eg and all(isinstance(i, dict) for i in eg):
        return False

    migrated: list[dict[str, Any]] = []
    for group in eg:
        g = _as_list(group)
        if g is None:
            return False
        targets: list[dict[str, str]] = []
        for item in g:
            parsed = _parse_triplet_target(str(item))
            if parsed is None:
                return False
            targets.append(parsed)
        migrated.append({"expression_groups": targets})

    expr["expression_groups"] = migrated
    return True


def _migrate_target_item_list(parent: dict[str, Any], key: str) -> bool:
    """
    将 list[str] 的 "platform:id:type" 迁移为 list[{platform,item_id,rule_type}]
    用于：memory.global_memory_blacklist 等。
    """
    raw = _as_list(parent.get(key))
    if raw is None:
        return False
    if raw and all(isinstance(i, dict) for i in raw):
        return False
    targets: list[dict[str, str]] = []
    for item in raw:
        parsed = _parse_triplet_target(str(item))
        if parsed is None:
            return False
        targets.append(parsed)
    parent[key] = targets
    return True


def _migrate_extra_prompt_list(exp: dict[str, Any], key: str) -> bool:
    """
    将 list[str] 的 "platform:id:type:prompt" 迁移为 list[{platform,item_id,rule_type,prompt}]
    用于：experimental.chat_prompts
    """
    raw = _as_list(exp.get(key))
    if raw is None:
        return False
    if raw and all(isinstance(i, dict) for i in raw):
        return False
    items: list[dict[str, str]] = []
    for item in raw:
        parsed = _parse_quad_prompt(str(item))
        if parsed is None:
            return False
        items.append(parsed)
    exp[key] = items
    return True


def migrate_legacy_bind_env_to_bot_config_dict(data: dict[str, Any]) -> MigrationResult:
    """将旧版环境变量中的绑定地址迁移到主配置结构。"""

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
    if maim_message is not None and _migrate_env_value(maim_message, "ws_server_port", main_port_env, 8080):
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
    尝试对“总配置 bot_config.toml”的 dict（已 unwrap）进行旧格式修复。
    仅做我们明确知道的结构性变更；其它字段不动。
    """
    if not ENABLE_LEGACY_MIGRATION:
        return MigrationResult(data=data, migrated=False, reason="disabled")

    migrated_any = False
    reasons: list[str] = []

    expr = _as_dict(data.get("expression"))
    if expr is not None:
        if _migrate_expression_learning_list(expr):
            migrated_any = True
            reasons.append("expression.learning_list")
        if _migrate_expression_groups(expr):
            migrated_any = True
            reasons.append("expression.expression_groups")
        # allow_reflect: 旧 list[str] -> 新 list[TargetItem]
        if _migrate_target_item_list(expr, "allow_reflect"):
            migrated_any = True
            reasons.append("expression.allow_reflect")
        # manual_reflect_operator_id: 旧 str -> 新 Optional[TargetItem]
        mroi = expr.get("manual_reflect_operator_id")
        if isinstance(mroi, str) and mroi.strip():
            parsed = _parse_triplet_target(mroi.strip())
            if parsed is not None:
                expr["manual_reflect_operator_id"] = parsed
                migrated_any = True
                reasons.append("expression.manual_reflect_operator_id")

    chat = _as_dict(data.get("chat"))
    if chat is None:
        chat = {}
        data["chat"] = chat

    mem = _as_dict(data.get("memory"))
    if mem is not None:
        for removed_key in (
            "agent_timeout_seconds",
            "global_memory",
            "global_memory_blacklist",
            "max_agent_iterations",
        ):
            if removed_key in mem:
                mem.pop(removed_key, None)
                migrated_any = True
                reasons.append(f"memory.{removed_key}_removed")

    exp = _as_dict(data.get("experimental"))
    if exp is not None:
        if _migrate_extra_prompt_list(exp, "chat_prompts"):
            migrated_any = True
            reasons.append("experimental.chat_prompts")

        for key in ("private_plan_style", "group_chat_prompt", "private_chat_prompts", "chat_prompts"):
            if key in exp and key not in chat:
                chat[key] = exp[key]
                migrated_any = True
                reasons.append(f"experimental.{key}_moved_to_chat")

        data.pop("experimental", None)
        migrated_any = True
        reasons.append("experimental_removed")

    if chat is not None and "think_mode" in chat:
        chat.pop("think_mode", None)
        migrated_any = True
        reasons.append("chat.think_mode_removed")

    tool = _as_dict(data.get("tool"))
    if tool is not None:
        data.pop("tool", None)
        migrated_any = True
        reasons.append("tool_section_removed")

    # ExpressionConfig 中的 manual_reflect_operator_id:
    # 旧版本可能是 ""（字符串），新版本期望 Optional[TargetItem]。
    # 空字符串视为未配置，转换为 None/删除键以避免校验错误。
    expr = _as_dict(data.get("expression"))
    if expr is not None:
        mroi = expr.get("manual_reflect_operator_id")
        if isinstance(mroi, str) and not mroi.strip():
            expr.pop("manual_reflect_operator_id", None)
            migrated_any = True
            reasons.append("expression.manual_reflect_operator_id_empty")

    reason = ",".join(reasons)
    return MigrationResult(data=data, migrated=migrated_any, reason=reason)
