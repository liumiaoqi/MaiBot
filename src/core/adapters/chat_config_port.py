"""GlobalConfigChatConfigPort — 从 global_config.chat 读取聊天配置。"""

from __future__ import annotations

from typing import Any

from src.core.types import KeywordReactionSnapshot, KeywordRuleSnapshot, ReplyStyleSnapshot, ReplyTimingSnapshot, TalkValueRuleSnapshot

_reply_timing_warned: bool = False


class GlobalConfigChatConfigPort:
    """从 global_config.chat 读取配置。涵盖 reply_style, context, mid_term_memory, personality, reply_timing, keyword_reaction。"""

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

    def get_personality(self) -> str:
        from src.config.config import global_config
        return global_config.personality.personality

    def get_reply_style_text(self) -> str:
        from src.config.config import global_config
        return global_config.personality.reply_style

    def get_multiple_reply_style(self) -> list[str]:
        from src.config.config import global_config
        return list(global_config.personality.multiple_reply_style)

    def get_multiple_reply_probability(self) -> float:
        from src.config.config import global_config
        return global_config.personality.multiple_probability

    def get_reply_timing_config(self) -> ReplyTimingSnapshot:
        import warnings
        from src.config.config import global_config
        global _reply_timing_warned
        if not _reply_timing_warned:
            warnings.warn(
                "reply_timing config will be replaced by vitality system",
                DeprecationWarning,
                stacklevel=2,
            )
            _reply_timing_warned = True
        rt = global_config.chat.reply_timing
        return ReplyTimingSnapshot(
            reply_trigger_mode=rt.reply_trigger_mode,
            planner_interrupt_max_consecutive_count=rt.planner_interrupt_max_consecutive_count,
            max_consecutive_wait_count=rt.max_consecutive_wait_count,
            talk_value=rt.talk_value,
            private_talk_value=rt.private_talk_value,
            enable_talk_value_rules=rt.enable_talk_value_rules,
            talk_value_rules=tuple(
                TalkValueRuleSnapshot(
                    platform=rule.platform,
                    item_id=rule.item_id,
                    rule_type=rule.rule_type,
                    time=rule.time,
                    value=rule.value,
                )
                for rule in rt.talk_value_rules
            ),
            mentioned_bot_reply=rt.mentioned_bot_reply,
            inevitable_at_reply=rt.inevitable_at_reply,
        )

    def get_keyword_reaction(self) -> KeywordReactionSnapshot:
        from src.config.config import global_config
        kr = global_config.keyword_reaction
        return KeywordReactionSnapshot(
            keyword_rules=tuple(
                KeywordRuleSnapshot(
                    keywords=tuple(rule.keywords),
                    regex=tuple(rule.regex),
                    reaction=rule.reaction,
                )
                for rule in kr.keyword_rules
            ),
            regex_rules=tuple(
                KeywordRuleSnapshot(
                    keywords=tuple(rule.keywords),
                    regex=tuple(rule.regex),
                    reaction=rule.reaction,
                )
                for rule in kr.regex_rules
            ),
        )

