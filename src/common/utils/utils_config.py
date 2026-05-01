from typing import Optional

import time

from src.common.logger import get_logger
from src.config.config import global_config

logger = get_logger("config_utils")


class ExpressionConfigUtils:
    @staticmethod
    def _find_expression_config_item(session_id: Optional[str] = None):
        if not global_config.expression.learning_list:
            return None

        if session_id:
            for config_item in global_config.expression.learning_list:
                if not config_item.platform and not config_item.item_id:
                    continue
                stream_id = ExpressionConfigUtils._get_stream_id(
                    config_item.platform,
                    str(config_item.item_id),
                    (config_item.rule_type == "group"),
                )
                if stream_id is None:
                    continue
                if stream_id != session_id:
                    continue
                return config_item

        for config_item in global_config.expression.learning_list:
            if not config_item.platform and not config_item.item_id:
                return config_item

        return None

    @staticmethod
    def get_expression_config_for_chat(session_id: Optional[str] = None) -> tuple[bool, bool, bool]:
        # sourcery skip: use-next
        """
        根据聊天会话 ID 获取表达配置。

        Args:
            session_id: 聊天会话 ID，格式为哈希值

        Returns:
            tuple: (是否使用表达, 是否学习表达, 是否启用 jargon 学习)
        """
        config_item = ExpressionConfigUtils._find_expression_config_item(session_id)
        if config_item is None:
            return True, True, True

        return (
            config_item.use_expression,
            config_item.enable_learning,
            config_item.enable_jargon_learning,
        )

    @staticmethod
    def _get_stream_id(platform: str, id_str: str, is_group: bool = False) -> Optional[str]:
        # sourcery skip: remove-unnecessary-cast
        """
        根据平台、ID 字符串和是否为群聊生成聊天流 ID。

        Args:
            platform: 平台名称
            id_str: 用户或群组的原始 ID 字符串
            is_group: 是否为群聊

        Returns:
            str: 生成的聊天流 ID（哈希值）
        """
        try:
            from src.common.utils.utils_session import SessionUtils

            if is_group:
                return SessionUtils.calculate_session_id(platform, group_id=str(id_str))
            else:
                return SessionUtils.calculate_session_id(platform, user_id=str(id_str))
        except Exception as e:
            logger.error(f"生成聊天流 ID 失败: {e}")
            return None


class ChatConfigUtils:
    @staticmethod
    def _resolve_is_group_chat(session_id: Optional[str]) -> Optional[bool]:
        if not session_id:
            return None

        try:
            from src.chat.message_receive.chat_manager import chat_manager

            chat_stream = chat_manager.get_session_by_session_id(session_id)
        except Exception as e:
            logger.debug(f"解析聊天流类型失败: session_id={session_id} error={e}")
            return None
        if chat_stream is None:
            return None
        return bool(chat_stream.is_group_session)

    @staticmethod
    def get_talk_value(session_id: Optional[str], is_group_chat: Optional[bool] = None) -> float:
        if is_group_chat is None:
            is_group_chat = ChatConfigUtils._resolve_is_group_chat(session_id)

        result = (
            global_config.chat.talk_value
            if is_group_chat is not False
            else global_config.chat.private_talk_value
        ) or 0.0
        if not global_config.chat.enable_talk_value_rules or not global_config.chat.talk_value_rules:
            return result
        local_time = time.localtime()
        now_min = local_time.tm_hour * 60 + local_time.tm_min

        # 优先匹配会话相关的规则
        if session_id:
            from src.common.utils.utils_session import SessionUtils

            for rule in global_config.chat.talk_value_rules:
                if not rule.platform and not rule.item_id:
                    continue  # 一起留空表示全局
                if rule.rule_type == "group":
                    rule_session_id = SessionUtils.calculate_session_id(rule.platform, group_id=str(rule.item_id))
                else:
                    rule_session_id = SessionUtils.calculate_session_id(rule.platform, user_id=str(rule.item_id))
                if rule_session_id != session_id:
                    continue  # 不匹配的会话 ID，跳过
                parsed_range = ChatConfigUtils.parse_range(rule.time)
                if not parsed_range:
                    continue  # 无法解析的时间范围，跳过
                start_min, end_min = parsed_range
                in_range: bool = False
                if start_min <= end_min:
                    in_range = start_min <= now_min <= end_min
                else:  # 跨天的时间范围
                    in_range = now_min >= start_min or now_min <= end_min
                if in_range:
                    return rule.value or 0.0  # 如果规则生效但没有设置值，返回 0.0

        # 没有匹配到会话相关的规则，继续匹配全局规则
        for rule in global_config.chat.talk_value_rules:
            if rule.platform or rule.item_id:
                continue  # 只匹配全局规则
            if is_group_chat is not None and (rule.rule_type == "group") != is_group_chat:
                continue
            parsed_range = ChatConfigUtils.parse_range(rule.time)
            if not parsed_range:
                continue  # 无法解析的时间范围，跳过
            start_min, end_min = parsed_range
            in_range: bool = False
            if start_min <= end_min:
                in_range = start_min <= now_min <= end_min
            else:  # 跨天的时间范围
                in_range = now_min >= start_min or now_min <= end_min
            if in_range:
                return rule.value or 0.0  # 如果规则生效但没有设置值，返回 0.0
        return result  # 如果没有任何规则生效，返回默认值

    @staticmethod
    def parse_range(range_str: str) -> Optional[tuple[int, int]]:
        """解析 "HH:MM-HH:MM" 到 (start_min, end_min)。"""
        try:
            start_str, end_str = [s.strip() for s in range_str.split("-")]
            sh, sm = [int(x) for x in start_str.split(":")]
            eh, em = [int(x) for x in end_str.split(":")]
            return sh * 60 + sm, eh * 60 + em
        except Exception:
            return None
