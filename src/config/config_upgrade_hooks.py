from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .official_configs import ChatConfig


ConfigUpgradeHookCallable = Callable[[dict[str, Any]], list[str]]


@dataclass(frozen=True)
class ConfigUpgradeHook:
    """配置升级钩子，在跨过指定版本时执行一次。"""

    target_version: str
    config_names: tuple[str, ...]
    migrate: ConfigUpgradeHookCallable


@dataclass
class ConfigUpgradeHookResult:
    data: dict[str, Any]
    migrated: bool
    reason: str = ""


def _parse_version(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _version_in_upgrade_range(old_ver: str, target_ver: str, new_ver: str) -> bool:
    old_parts = _parse_version(old_ver)
    target_parts = _parse_version(target_ver)
    new_parts = _parse_version(new_ver)
    return old_parts < target_parts <= new_parts


def set_nested_config_value(data: dict[str, Any], path: tuple[str, ...], value: Any, force: bool = True) -> bool:
    """设置嵌套配置值，返回是否实际发生变化。"""

    if not path:
        return False

    current: dict[str, Any] = data
    for key in path[:-1]:
        next_value = current.get(key)
        if not isinstance(next_value, dict):
            next_value = {}
            current[key] = next_value
        current = next_value

    leaf_key = path[-1]
    if not force and leaf_key in current:
        return False
    if current.get(leaf_key) == value:
        return False

    current[leaf_key] = value
    return True


def _reset_group_chat_prompt_to_default(data: dict[str, Any]) -> list[str]:
    default_group_chat_prompt = ChatConfig().group_chat_prompt
    changed = set_nested_config_value(data, ("chat", "group_chat_prompt"), default_group_chat_prompt)
    return ["chat.group_chat_prompt"] if changed else []


BOT_CONFIG_UPGRADE_HOOKS: tuple[ConfigUpgradeHook, ...] = (
    ConfigUpgradeHook(
        target_version="8.10.11",
        config_names=("bot_config.toml",),
        migrate=_reset_group_chat_prompt_to_default,
    ),
)
MODEL_CONFIG_UPGRADE_HOOKS: tuple[ConfigUpgradeHook, ...] = ()


def apply_config_upgrade_hooks(
    data: dict[str, Any],
    config_name: str,
    old_ver: str,
    new_ver: str,
) -> ConfigUpgradeHookResult:
    migrated_reasons: list[str] = []
    hooks = BOT_CONFIG_UPGRADE_HOOKS + MODEL_CONFIG_UPGRADE_HOOKS

    for hook in hooks:
        if config_name not in hook.config_names:
            continue
        if not _version_in_upgrade_range(old_ver, hook.target_version, new_ver):
            continue

        hook_reasons = hook.migrate(data)
        for reason in hook_reasons:
            migrated_reasons.append(f"{hook.target_version}:{reason}")

    reason = ",".join(migrated_reasons)
    return ConfigUpgradeHookResult(data=data, migrated=bool(migrated_reasons), reason=reason)
