"""GlobalConfigBotConfigPort — 从 global_config.bot 读取 Bot 配置。"""

from __future__ import annotations


class GlobalConfigBotConfigPort:
    """从 global_config.bot 读取配置。构造时延迟导入，避免循环依赖。"""

    def _get_bot(self):
        from src.config.config import global_config
        return global_config.bot

    def get_bot_nickname(self) -> str:
        return self._get_bot().nickname

    def get_bot_alias_names(self) -> list[str]:
        return list(self._get_bot().alias_names)

    def get_bot_qq_account(self, platform: str) -> str:
        from src.core.identity import get_bot_account
        return get_bot_account(platform)

    def get_bot_platforms(self) -> list[str]:
        return list(self._get_bot().platforms)

    def get_bot_owner_user_ids(self) -> list[str]:
        return list(self._get_bot().owner_user_ids)
