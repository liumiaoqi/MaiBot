"""get_content 内置工具。"""

from typing import Any, Optional

from src.core.tooling import ToolContentItem, ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec
from src.maisaka.favourite_storage import (
    FavouriteStorageError,
    find_content_by_id,
    read_binary_item_base64,
    read_text_item,
)

from .context import BuiltinToolRuntimeContext


def get_tool_spec() -> ToolSpec:
    """获取 get_content 工具声明。"""

    return ToolSpec(
        name="get_content",
        description="按收藏内容 id 获取任意收藏池里的内容，并返回到当前上下文中。文本会直接返回；图片会作为可引用的工具媒体返回。",
        parameters_schema={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "要获取的收藏内容 ID。",
                },
            },
            "required": ["id"],
        },
        provider_name="maisaka_builtin",
        provider_type="builtin",
    )


def _build_item_header(item: dict[str, Any], *, pool_key: str) -> str:
    return (
        f"id: {item['id']}\n"
        f"名称: {item['name']}\n"
        f"描述: {item['description']}\n"
        f"格式: {item['format']}\n"
        f"大小: {item['size']} bytes\n"
        f"收藏池: {pool_key}"
    )


def _build_structured_content(item: dict[str, Any], *, pool_key: str, pool_chat_id: str, isolated_by_chat: bool) -> dict[str, Any]:
    return {
        "pool": {
            "key": pool_key,
            "chat_id": pool_chat_id,
            "isolated_by_chat": isolated_by_chat,
        },
        "item": item,
    }


async def handle_tool(
    tool_ctx: BuiltinToolRuntimeContext,
    invocation: ToolInvocation,
    context: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    """执行 get_content 内置工具。"""

    del context
    content_id = str(invocation.arguments.get("id") or invocation.arguments.get("content_id") or "").strip()
    try:
        resolved_item = find_content_by_id(
            content_id,
            preferred_chat_id=str(tool_ctx.runtime.session_id or ""),
        )
    except FavouriteStorageError as exc:
        return tool_ctx.build_failure_result(invocation.tool_name, str(exc))

    item = resolved_item.item
    pool = resolved_item.pool
    structured_content = _build_structured_content(
        item,
        pool_key=pool.key,
        pool_chat_id=pool.chat_id,
        isolated_by_chat=pool.isolated_by_chat,
    )
    header = _build_item_header(item, pool_key=pool.key)
    content_type = str(item.get("content_type") or "").strip()

    if content_type == "image":
        try:
            image_base64 = read_binary_item_base64(resolved_item)
        except FavouriteStorageError as exc:
            return tool_ctx.build_failure_result(invocation.tool_name, str(exc), structured_content=structured_content)

        content = f"已获取收藏图片。\n{header}\n图片已作为工具媒体返回，可在后续用 tool_result:<call_id>:<item_index> 引用。"
        return ToolExecutionResult(
            tool_name=invocation.tool_name,
            success=True,
            content=content,
            structured_content=structured_content,
            content_items=[
                ToolContentItem(
                    content_type="image",
                    data=image_base64,
                    mime_type=str(item.get("format") or "image/png"),
                    name=str(item.get("name") or ""),
                    description=str(item.get("description") or ""),
                    metadata={
                        "context_key": str(item.get("id") or ""),
                        "pool": pool.key,
                    },
                )
            ],
            metadata={"record_display_prompt": f"获取收藏内容：{item['name']}"},
        )

    try:
        text = read_text_item(resolved_item)
    except FavouriteStorageError as exc:
        return tool_ctx.build_failure_result(invocation.tool_name, str(exc), structured_content=structured_content)

    structured_content["content"] = text
    return tool_ctx.build_success_result(
        invocation.tool_name,
        f"已获取收藏文本。\n{header}\n\n内容:\n{text}",
        structured_content=structured_content,
        metadata={"record_display_prompt": f"获取收藏内容：{item['name']}"},
    )
