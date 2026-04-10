from typing import Optional

from src.common.logger import get_logger
from src.config.config import global_config

logger = get_logger("common_utils")


class TempMethodsExpression:
    """用于临时存放一些方法的类"""

    @staticmethod
    def _find_expression_config_item(chat_stream_id: Optional[str] = None):
        if not global_config.expression.learning_list:
            return None

        if chat_stream_id:
            for config_item in global_config.expression.learning_list:
                if not config_item.platform and not config_item.item_id:
                    continue
                stream_id = TempMethodsExpression._get_stream_id(
                    config_item.platform,
                    str(config_item.item_id),
                    (config_item.rule_type == "group"),
                )
                if stream_id is None:
                    continue
                if stream_id != chat_stream_id:
                    continue
                return config_item

        for config_item in global_config.expression.learning_list:
            if not config_item.platform and not config_item.item_id:
                return config_item

        return None

    @staticmethod
    def get_expression_advanced_chosen_for_chat(chat_stream_id: Optional[str] = None) -> bool:
        """根据聊天流 ID 获取表达方式是否启用二次选择。"""
        config_item = TempMethodsExpression._find_expression_config_item(chat_stream_id)
        if config_item is None:
            return False
        return config_item.advanced_chosen

    @staticmethod
    def get_expression_config_for_chat(chat_stream_id: Optional[str] = None) -> tuple[bool, bool, bool]:
        """
        根据聊天流 ID 获取表达配置。

        Args:
            chat_stream_id: 聊天流 ID，格式为哈希值

        Returns:
            tuple: (是否使用表达, 是否学习表达, 是否启用 jargon 学习)
        """
        config_item = TempMethodsExpression._find_expression_config_item(chat_stream_id)
        if config_item is None:
            return True, True, True

        return (
            config_item.use_expression,
            config_item.enable_learning,
            config_item.enable_jargon_learning,
        )

    @staticmethod
    def _get_stream_id(
        platform: str,
        id_str: str,
        is_group: bool = False,
    ) -> Optional[str]:
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
