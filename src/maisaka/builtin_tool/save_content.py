"""save_content 内置工具。"""

from typing import Any, Optional

from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec
from src.maisaka.favourite_storage import FavouriteStorageError, save_image_content, save_text_content

from .context import BuiltinToolRuntimeContext
from .send_image import _collect_message_images, _normalize_image_index


def get_tool_spec() -> ToolSpec:
    """获取 save_content 工具声明。"""

    return ToolSpec(
        name="save_content",
        description=(
            "保存麦麦收藏内容。当你认为某段文本或图片符合你的人设、让你喜爱、与你有关，"
            "或这个内容有助于后续聊天中使用时，可以调用本工具保存。需要指定文件名和简略描述。"
            "可以保存一段文本，也可以按 send_image 相同方式用 msg_id/media_index/index 选择图片保存。"
            "如果收藏池中已有同名内容，会返回重名错误。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "要保存的文件名。文本未带扩展名时会补 .txt，图片未带扩展名时会按图片格式补扩展名。",
                },
                "description": {
                    "type": "string",
                    "description": "对收藏内容的简略描述，便于后续浏览和搜索。",
                },
                "content_type": {
                    "type": "string",
                    "enum": ["text", "image"],
                    "description": "保存类型。省略时，如果提供 msg_id 或 media_index 则按图片保存，否则按文本保存。",
                },
                "content": {
                    "type": "string",
                    "description": "要保存的文本内容。保存图片时不要填写。",
                    "default": "",
                },
                "msg_id": {
                    "type": "string",
                    "description": "包含图片的上下文消息编号，也可以是工具返回媒体索引 tool_result:<call_id>:<item_index>。",
                    "default": "",
                },
                "media_index": {
                    "type": "string",
                    "description": "工具返回媒体索引，例如 tool_result:call_x:1；与 msg_id 二选一。",
                    "default": "",
                },
                "index": {
                    "type": "integer",
                    "description": "同一消息中的图片序号，从 0 开始。",
                    "default": 0,
                },
            },
            "required": ["filename", "description"],
        },
        provider_name="maisaka_builtin",
        provider_type="builtin",
    )


def _resolve_save_content_type(arguments: dict[str, Any]) -> str:
    raw_content_type = str(arguments.get("content_type") or "").strip().lower()
    if raw_content_type in {"text", "image"}:
        return raw_content_type

    if str(arguments.get("media_index") or "").strip() or str(arguments.get("msg_id") or "").strip():
        return "image"
    return "text"


def _build_save_success_content(item: dict[str, Any], *, pool_key: str) -> str:
    return (
        "已保存收藏内容。\n"
        f"id: {item['id']}\n"
        f"名称: {item['name']}\n"
        f"描述: {item['description']}\n"
        f"格式: {item['format']}\n"
        f"大小: {item['size']} bytes\n"
        f"收藏池: {pool_key}"
    )


async def _save_image(
    tool_ctx: BuiltinToolRuntimeContext,
    invocation: ToolInvocation,
    arguments: dict[str, Any],
) -> ToolExecutionResult:
    target_message_id = (
        str(arguments.get("media_index") or "").strip()
        or str(arguments.get("msg_id") or "").strip()
    )
    if not target_message_id:
        return tool_ctx.build_failure_result(invocation.tool_name, "保存图片收藏需要提供 msg_id 或 media_index。")

    image_index = _normalize_image_index(arguments)
    images, error = await _collect_message_images(tool_ctx, target_message_id)
    if error is not None:
        return tool_ctx.build_failure_result(invocation.tool_name, error)
    if image_index < 0 or image_index >= len(images):
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            f"图片序号超出范围：index={image_index}，该消息共有 {len(images)} 张图片。",
        )

    try:
        save_result = save_image_content(
            chat_id=str(tool_ctx.runtime.session_id or ""),
            filename=str(arguments.get("filename") or ""),
            description=str(arguments.get("description") or ""),
            image_data=bytes(images[image_index].binary_data or b""),
            source={
                "type": "image",
                "msg_id": target_message_id,
                "index": image_index,
            },
        )
    except FavouriteStorageError as exc:
        return tool_ctx.build_failure_result(invocation.tool_name, str(exc))

    item = save_result.item
    content = _build_save_success_content(item, pool_key=save_result.pool.key)
    return tool_ctx.build_success_result(
        invocation.tool_name,
        content,
        structured_content={
            "success": True,
            "pool": {
                "key": save_result.pool.key,
                "chat_id": save_result.pool.chat_id,
                "isolated_by_chat": save_result.pool.isolated_by_chat,
            },
            "item": item,
        },
        metadata={"record_display_prompt": f"保存收藏内容：{item['name']}"},
    )


async def _save_text(
    tool_ctx: BuiltinToolRuntimeContext,
    invocation: ToolInvocation,
    arguments: dict[str, Any],
) -> ToolExecutionResult:
    text = str(arguments.get("content") or arguments.get("text") or "")
    try:
        save_result = save_text_content(
            chat_id=str(tool_ctx.runtime.session_id or ""),
            filename=str(arguments.get("filename") or ""),
            description=str(arguments.get("description") or ""),
            text=text,
        )
    except FavouriteStorageError as exc:
        return tool_ctx.build_failure_result(invocation.tool_name, str(exc))

    item = save_result.item
    content = _build_save_success_content(item, pool_key=save_result.pool.key)
    return tool_ctx.build_success_result(
        invocation.tool_name,
        content,
        structured_content={
            "success": True,
            "pool": {
                "key": save_result.pool.key,
                "chat_id": save_result.pool.chat_id,
                "isolated_by_chat": save_result.pool.isolated_by_chat,
            },
            "item": item,
        },
        metadata={"record_display_prompt": f"保存收藏内容：{item['name']}"},
    )


async def handle_tool(
    tool_ctx: BuiltinToolRuntimeContext,
    invocation: ToolInvocation,
    context: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    """执行 save_content 内置工具。"""

    del context
    arguments = dict(invocation.arguments or {})
    content_type = _resolve_save_content_type(arguments)
    if content_type == "image":
        return await _save_image(tool_ctx, invocation, arguments)
    return await _save_text(tool_ctx, invocation, arguments)
