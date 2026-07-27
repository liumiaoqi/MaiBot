"""核心身份判断工具。

提供 is_bot_self / get_bot_account / get_all_bot_accounts 等身份判断函数。
maisaka 层应从此模块导入，不直接依赖 chat 层。
"""

from src.common.logger import get_logger
from src.core.bot_config_port_registry import get_bot_config_port

__all__ = [
    "get_bot_account",
    "get_all_bot_accounts",
    "is_bot_self",
    "parse_platform_accounts",
]

logger = get_logger("core_identity")
_warned_unconfigured_platforms: set[str] = set()

def parse_platform_accounts(platforms: list[str]) -> dict[str, str]:
    """解析 platforms 列表，返回平台到账号的映射

    Args:
        platforms: 格式为 ["platform:account"] 的列表，如 ["tg:123456789", "wx:wxid123"]

    Returns:
        字典，键为平台名，值为账号
    """
    result: dict[str, str] = {}
    for platform_entry in platforms:
        if ":" in platform_entry:
            platform_name, account = platform_entry.split(":", 1)
            normalized_platform = platform_name.lower().strip()
            account_str = account.strip()
            if normalized_platform and account_str:
                result[normalized_platform] = account_str
    return result

def _get_configured_qq_account() -> str:
    port = get_bot_config_port()
    if port is None:
        return ""
    qq_account = str(port.get_bot_primary_account()).strip()
    if qq_account in {"", "0"}:
        return ""
    return qq_account

def get_bot_account(platform: str) -> str:
    """根据当前平台获取对应的机器人账号。"""
    normalized_platform = str(platform or "").strip().lower()
    if not normalized_platform:
        return ""

    port = get_bot_config_port()
    if port is None:
        return ""

    qq_account = _get_configured_qq_account()
    if normalized_platform in {"qq", "webui"}:
        return qq_account

    platforms_list = port.get_bot_platforms()
    platform_accounts = parse_platform_accounts(platforms_list)
    if normalized_platform in {"tg", "telegram"}:
        return platform_accounts.get("tg", "") or platform_accounts.get("telegram", "")

    return platform_accounts.get(normalized_platform, "")

def get_all_bot_accounts() -> dict[str, str]:
    """获取所有已配置的机器人运行时身份。"""
    port = get_bot_config_port()
    if port is None:
        return {}

    bot_accounts: dict[str, str] = {}
    qq_account = _get_configured_qq_account()
    if qq_account:
        bot_accounts["qq"] = qq_account
        bot_accounts["webui"] = qq_account

    platforms_list = port.get_bot_platforms()
    platform_accounts = parse_platform_accounts(platforms_list)

    telegram_account = platform_accounts.get("tg", "") or platform_accounts.get("telegram", "")
    if telegram_account:
        bot_accounts["telegram"] = telegram_account
        bot_accounts["tg"] = telegram_account

    for platform_name, account in platform_accounts.items():
        if platform_name in {"tg", "telegram", "qq", "webui"}:
            continue
        bot_accounts[platform_name] = account

    return bot_accounts

def is_bot_self(platform: str, user_id: str) -> bool:
    """判断给定的平台和用户ID是否是机器人自己

    这个函数统一处理所有平台（包括 QQ、Telegram、WebUI 等）的机器人识别逻辑。

    Args:
        platform: 消息平台（如 "qq", "telegram", "webui" 等）
        user_id: 用户ID

    Returns:
        bool: 如果是机器人自己则返回 True，否则返回 False
    """
    normalized_platform = str(platform or "").strip().lower()
    if not normalized_platform or not user_id:
        return False

    # 将 user_id 转为字符串进行比较
    user_id_str = str(user_id).strip()
    if not user_id_str:
        return False

    bot_account = get_bot_account(normalized_platform)
    if bot_account:
        return user_id_str == bot_account

    if normalized_platform not in _warned_unconfigured_platforms:
        _warned_unconfigured_platforms.add(normalized_platform)
        logger.warning(f"平台 {normalized_platform} 未配置机器人账号，无法判断用户 {user_id_str} 是否为机器人自己")
    return False

