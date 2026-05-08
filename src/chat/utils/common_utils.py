from typing import Optional

from src.common.logger import get_logger
from src.common.utils.utils_config import ExpressionConfigUtils

logger = get_logger("common_utils")


class TempMethodsExpression:
    """用于临时存放一些方法的类"""

    @staticmethod
    def _find_expression_config_item(chat_stream_id: Optional[str] = None):
        return ExpressionConfigUtils._find_expression_config_item(chat_stream_id)

    @staticmethod
    def get_expression_config_for_chat(chat_stream_id: Optional[str] = None) -> tuple[bool, bool, bool]:
        """
        根据聊天流 ID 获取表达配置。

        Args:
            chat_stream_id: 聊天流 ID，格式为哈希值

        Returns:
            tuple: (是否使用表达, 是否学习表达, 是否启用 jargon 学习)
        """
        return ExpressionConfigUtils.get_expression_config_for_chat(chat_stream_id)

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
