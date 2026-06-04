"""browser_content 内置工具。"""

from typing import Any, Optional

from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec
from src.maisaka.favourite_storage import FavouriteStorageError, browse_current_pool

from .context import BuiltinToolRuntimeContext


def get_tool_spec() -> ToolSpec:
    """获取 browser_content 工具声明。"""

    return ToolSpec(
        name="browser_content",
        description=(
            "分页浏览麦麦收藏池内容列表。开启聊天隔离时只浏览当前 chat 的收藏池；"
            "未开启聊天隔离时浏览共享收藏池。可以按名称和描述搜索。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "page": {
                    "type": "integer",
                    "description": "页码，从 1 开始。默认 1。",
                    "minimum": 1,
                    "default": 1,
                },
                "page_size": {
                    "type": "integer",
                    "description": "每页数量，默认 10，最大 50。",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 10,
                },
                "query": {
                    "type": "string",
                    "description": "按名称和描述搜索的关键词。留空表示浏览全部。",
                    "default": "",
                },
            },
        },
        provider_name="maisaka_builtin",
        provider_type="builtin",
    )


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def _build_list_content(result: dict[str, Any]) -> str:
    pool = result["pool"]
    items = list(result["items"])
    lines = [
        "收藏内容列表",
        f"收藏池: {pool['key']}",
        f"隔离模式: {'按聊天隔离' if pool['isolated_by_chat'] else '共享'}",
        f"页码: {result['page']}/{result['total_pages']}",
        f"每页: {result['page_size']}",
        f"匹配数量: {result['total']}",
    ]
    if result["query"]:
        lines.append(f"搜索: {result['query']}")
    if not items:
        lines.append("当前没有匹配的收藏内容。")
        return "\n".join(lines)

    start_number = (int(result["page"]) - 1) * int(result["page_size"]) + 1
    for offset, item in enumerate(items):
        description = " ".join(str(item.get("description") or "").split())
        if len(description) > 120:
            description = f"{description[:120]}..."
        lines.append(
            f"{start_number + offset}. id={item['id']} 名称={item['name']} "
            f"格式={item['format']} 大小={_format_size(int(item['size']))} 描述={description}"
        )
    return "\n".join(lines)


async def handle_tool(
    tool_ctx: BuiltinToolRuntimeContext,
    invocation: ToolInvocation,
    context: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    """执行 browser_content 内置工具。"""

    del context
    arguments = dict(invocation.arguments or {})
    page = _coerce_positive_int(arguments.get("page"), 1)
    page_size = min(50, _coerce_positive_int(arguments.get("page_size"), 10))
    query = str(arguments.get("query") or arguments.get("keyword") or "").strip()

    try:
        result = browse_current_pool(
            chat_id=str(tool_ctx.runtime.session_id or ""),
            query=query,
            page=page,
            page_size=page_size,
        )
    except FavouriteStorageError as exc:
        return tool_ctx.build_failure_result(invocation.tool_name, str(exc))

    content = _build_list_content(result)
    return tool_ctx.build_success_result(
        invocation.tool_name,
        content,
        structured_content=result,
        metadata={"record_display_prompt": content},
    )
