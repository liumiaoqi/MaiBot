"""工具执行后的通用后处理工具。"""


from typing import Any, Optional

from src.common.logger import get_logger
from src.core.tooling import ToolExecutionResult, ToolInvocation


logger = get_logger("maisaka_tool_post_execution")


async def handle_tool_post_execution_effects(
    *,
    invocation: ToolInvocation,
    result: ToolExecutionResult,
    saved_record: Optional[dict[str, Any]],
    chat_stream: Any,
    log_prefix: str,
) -> None:
    """处理工具执行后的非落库副作用。"""
