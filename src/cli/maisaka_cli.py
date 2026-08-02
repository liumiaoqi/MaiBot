"""
MaiSaka CLI and conversation loop.
"""

from datetime import datetime
from src.common.logger import get_logger
logger = get_logger("auto.maisaka_cli")


import asyncio

from rich import box
from rich.panel import Panel
from rich.text import Text

from src.core.runtime_port_registry import get_chat_runtime_registry
from src.chat.heart_flow.heartflow_message_processor import HeartFCMessageReceiver

from src.common.data_models.session_message_data_model import SessionMessage
from src.common.data_models.mai_message_data_model import MessageInfo, UserInfo
from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
from src.core.model_config_port_registry import get_model_config_port

from .maisaka_cli_sender import CLI_PLATFORM_NAME
from .console import console
from .input_reader import InputReader


class BufferCLI:
    """Maisaka 命令行交互入口。"""

    _CLI_PLATFORM = CLI_PLATFORM_NAME
    _CLI_USER_ID = "maisaka_user"

    def __init__(self) -> None:
        self._reader = InputReader()
        self._message_receiver = HeartFCMessageReceiver()
        self._session_id: str | None = None

    @staticmethod
    def _get_current_model_name() -> str:
        """读取当前 planner 模型名。"""
        try:
            port = get_model_config_port()
            if port is None:
                return "未配置"
            task_config = port.get_task_config("planner")
            if task_config.model_list:
                return task_config.model_list[0]
        except Exception:
            logger.warning("操作异常 in maisaka_cli", exc_info=True)
        return "未配置"

    def _show_banner(self) -> None:
        """渲染启动横幅。"""
        banner = Text()
        banner.append("MaiSaka", style="bold cyan")
        banner.append(" v2.0\n", style="muted")
        banner.append(f"模型: {self._get_current_model_name()}\n", style="muted")
        banner.append("输入内容开始对话 | Ctrl+C 退出", style="muted")
        console.print(Panel(banner, box=box.DOUBLE_EDGE, border_style="cyan", padding=(1, 2)))
        console.print()

    @staticmethod
    def _build_cli_session_message(
        *,
        user_text: str,
        timestamp: datetime,
    ) -> SessionMessage:
        """构造一条供 heartflow 复用的 CLI 用户消息。"""
        message = SessionMessage(
            message_id=f"maisaka_cli_{int(timestamp.timestamp() * 1000)}",
            timestamp=timestamp,
            platform=BufferCLI._CLI_PLATFORM,
        )
        message.message_info = MessageInfo(
            user_info=UserInfo(
                user_id=BufferCLI._CLI_USER_ID,
                user_nickname="用户",
                user_cardname=None,
            ),
            group_info=None,
            additional_config={},
        )
        message.raw_message = MessageSequence([TextComponent(text=user_text)])
        message.processed_plain_text = user_text
        message.initialized = True
        return message

    async def _dispatch_input(self, user_text: str) -> None:
        """将 CLI 输入转发到 heartflow 路径。"""
        message = self._build_cli_session_message(
            user_text=user_text,
            timestamp=datetime.now(),
        )
        from src.core.session_port_registry import get_session_lifecycle_port, get_message_registry_port

        registry_port = get_message_registry_port()
        if registry_port is not None:
            registry_port.register_message(message)
        lifecycle_port = get_session_lifecycle_port()
        if lifecycle_port is not None:
            self._session_id = await lifecycle_port.get_or_create_session_id(
                platform=self._CLI_PLATFORM,
                user_id=self._CLI_USER_ID,
            )
        await self._message_receiver.process_message(message)

    async def run(self) -> None:
        """主交互循环。"""
        self._reader.start(asyncio.get_event_loop())
        self._show_banner()

        try:
            while True:
                console.print("[bold cyan]> [/bold cyan]", end="")
                raw_input = await self._reader.get_line()
                if raw_input is None:
                    console.print("\n[muted]再见[/muted]")
                    break

                user_text = raw_input.strip()
                if not user_text:
                    continue

                await self._dispatch_input(user_text)
        finally:
            if self._session_id is not None:
                runtime = get_chat_runtime_registry().remove_runtime(self._session_id)
                if runtime is not None:
                    await runtime.stop()
