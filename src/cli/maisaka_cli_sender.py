"""Maisaka CLI 展示适配。"""

from rich.markdown import Markdown
from rich.panel import Panel

from src.common.logger import get_logger

from src.core.bot_config_port_registry import get_bot_config_port

from .console import console

CLI_PLATFORM_NAME = "maisaka_cli"

logger = get_logger("maisaka_cli_sender")


def render_cli_message(content: str, *, title: str = "") -> None:
    """将 CLI 私聊实例的消息展示到终端。"""
    preview_text = content.strip() or "..."
    console.print(
        Panel(
            Markdown(preview_text),
            title=title or get_bot_config_port().get_bot_nickname().strip() or "MaiSaka",
            border_style="magenta",
            padding=(1, 2),
        )
    )
    logger.info(f"[CLI] 已将消息输出到终端: content={preview_text!r}")
