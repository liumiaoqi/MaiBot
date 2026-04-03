"""Maisaka 内置工具聚合入口。"""

from collections.abc import Awaitable, Callable
from typing import Dict, List, Optional

from src.config.config import global_config
from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec
from src.llm_models.payload_content.tool_option import ToolDefinitionInput

from .context import BuiltinToolRuntimeContext
from .no_reply import get_tool_spec as get_no_reply_tool_spec
from .no_reply import handle_tool as handle_no_reply_tool
from .query_jargon import get_tool_spec as get_query_jargon_tool_spec
from .query_jargon import handle_tool as handle_query_jargon_tool
from .query_memory import get_tool_spec as get_query_memory_tool_spec
from .query_memory import handle_tool as handle_query_memory_tool
from .query_person_info import get_tool_spec as get_query_person_info_tool_spec
from .query_person_info import handle_tool as handle_query_person_info_tool
from .reply import get_tool_spec as get_reply_tool_spec
from .reply import handle_tool as handle_reply_tool
from .send_emoji import get_tool_spec as get_send_emoji_tool_spec
from .send_emoji import handle_tool as handle_send_emoji_tool
from .view_complex_message import get_tool_spec as get_view_complex_message_tool_spec
from .view_complex_message import handle_tool as handle_view_complex_message_tool
from .wait import get_tool_spec as get_wait_tool_spec
from .wait import handle_tool as handle_wait_tool

BuiltinToolHandler = Callable[[ToolInvocation, Optional[ToolExecutionContext]], Awaitable[ToolExecutionResult]]


def get_builtin_tool_specs() -> List[ToolSpec]:
    """获取默认启用的内置工具声明列表。"""

    return [
        get_wait_tool_spec(),
        get_reply_tool_spec(),
        get_view_complex_message_tool_spec(),
        get_query_jargon_tool_spec(),
        get_query_memory_tool_spec(enabled=bool(global_config.maisaka.enable_memory_query_tool)),
        get_no_reply_tool_spec(),
        get_send_emoji_tool_spec(),
    ]


def get_all_builtin_tool_specs() -> List[ToolSpec]:
    """获取全部内置工具声明列表。"""

    return [
        get_wait_tool_spec(),
        get_reply_tool_spec(),
        get_view_complex_message_tool_spec(),
        get_query_jargon_tool_spec(),
        get_query_memory_tool_spec(enabled=True),
        get_query_person_info_tool_spec(),
        get_no_reply_tool_spec(),
        get_send_emoji_tool_spec(),
    ]


def get_builtin_tools() -> List[ToolDefinitionInput]:
    """获取兼容旧模型层的内置工具定义。"""

    return [tool_spec.to_llm_definition() for tool_spec in get_builtin_tool_specs()]


def build_builtin_tool_handlers(tool_ctx: BuiltinToolRuntimeContext) -> Dict[str, BuiltinToolHandler]:
    """构建内置工具处理器映射。"""

    return {
        "reply": lambda invocation, context=None: handle_reply_tool(tool_ctx, invocation, context),
        "no_reply": lambda invocation, context=None: handle_no_reply_tool(tool_ctx, invocation, context),
        "query_jargon": lambda invocation, context=None: handle_query_jargon_tool(tool_ctx, invocation, context),
        "query_memory": lambda invocation, context=None: handle_query_memory_tool(tool_ctx, invocation, context),
        "query_person_info": lambda invocation, context=None: handle_query_person_info_tool(
            tool_ctx,
            invocation,
            context,
        ),
        "wait": lambda invocation, context=None: handle_wait_tool(tool_ctx, invocation, context),
        "send_emoji": lambda invocation, context=None: handle_send_emoji_tool(tool_ctx, invocation, context),
        "view_complex_message": lambda invocation, context=None: handle_view_complex_message_tool(
            tool_ctx,
            invocation,
            context,
        ),
    }
