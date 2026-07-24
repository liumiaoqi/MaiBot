"""GlobalConfigChatConfigPort — 从 global_config.chat 读取聊天配置。"""

from __future__ import annotations

from typing import Any

from src.core.types import ReplyStyleSnapshot


class GlobalConfigChatConfigPort:
    """从 global_config.chat 读取配置。不含 reply_timing 待废弃属性。"""

    def _get_chat(self):
        from src.config.config import global_config
        return global_config.chat

    def get_reply_style(self) -> ReplyStyleSnapshot:
        from src.config.config import global_config
        rs = global_config.chat.reply_style
        return ReplyStyleSnapshot(
            chat_prompts=[item.model_dump() for item in rs.chat_prompts],
            private_chat_prompts=rs.private_chat_prompts,
            group_chat_prompt=rs.group_chat_prompt,
            enable_reply_quote=rs.enable_reply_quote,
        )

    def get_max_context_size(self) -> int:
        return self._get_chat().max_context_size

    def get_max_private_context_size(self) -> int:
        return self._get_chat().max_private_context_size

    def get_self_message_special_mark(self) -> str:
        return self._get_chat().self_message_special_mark

    def get_mid_term_memory_config(self) -> dict[str, Any]:
        chat = self._get_chat()
        return {
            "mid_term_memory_length": chat.mid_term_memory_length,
            "mid_term_memory_max_token": chat.mid_term_memory_max_token,
        }
