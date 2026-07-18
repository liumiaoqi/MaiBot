"""核心身份判断工具 — 桥接 re-export。

is_bot_self / get_bot_account 当前定义在 src/chat/utils/utils.py，
但被 core/maisaka 层使用。此处 re-export 作为集中桥接点，
maisaka 应从 core.identity 导入，不直接依赖 chat 层。
后续架构演进将把函数定义物理迁移到 core 层。
"""

# ruff: noqa: TID251
from src.chat.utils.utils import get_bot_account as get_bot_account
from src.chat.utils.utils import is_bot_self as is_bot_self

__all__ = [
    "get_bot_account",
    "is_bot_self",
]
