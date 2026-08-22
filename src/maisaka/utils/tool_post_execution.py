"""[未接线原型] 工具执行后的通用后处理工具。

注意：handle_tool_post_execution_effects 当前零生产调用点且函数体为空（A18 P1-7）。
计划在工具执行后流程中接线调用，实现非落库副作用处理。保留作为待实现待接线的原型。
"""


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
