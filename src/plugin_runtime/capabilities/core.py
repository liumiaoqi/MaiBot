from typing import Any, Dict, List

from src.common.logger import get_logger
from src.config.config import global_config

logger = get_logger("plugin_runtime.integration")


def _get_nested_config_value(source: Any, key: str, default: Any = None) -> Any:
    """从嵌套对象或字典中读取配置值。

    Args:
        source: 配置对象或字典。
        key: 以点号分隔的路径。
        default: 未命中时返回的默认值。

    Returns:
        Any: 命中的值；读取失败时返回默认值。
    """
    current = source
    try:
        for part in key.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
                continue
            if hasattr(current, part):
                current = getattr(current, part)
                continue
            raise KeyError(part)
        return current
    except Exception:
        return default


def _normalize_prompt_arg(prompt: Any) -> str | List[Dict[str, Any]]:
    """校验并规范化插件传入的提示参数。

    Args:
        prompt: 原始提示参数。

    Returns:
        str | List[Dict[str, Any]]: 规范化后的提示输入。

    Raises:
        ValueError: 提示参数缺失或结构不受支持时抛出。
    """
    if isinstance(prompt, str):
        if not prompt.strip():
            raise ValueError("缺少必要参数 prompt")
        return prompt
    if isinstance(prompt, list) and prompt:
        for index, prompt_message in enumerate(prompt, start=1):
            if not isinstance(prompt_message, dict):
                raise ValueError(f"prompt 第 {index} 项必须为字典")
        return prompt
    raise ValueError("缺少必要参数 prompt")


class RuntimeCoreCapabilityMixin:
    """插件运行时的核心能力混入。"""

    async def _cap_send_text(self, plugin_id: str, capability: str, args: Dict[str, Any]) -> Any:
        """向指定流发送文本消息。

        Args:
            plugin_id: 插件标识。
            capability: 能力名称。
            args: 能力调用参数。

        Returns:
            Any: 能力执行结果。
        """
        del plugin_id, capability
        from src.services import send_service as send_api

        text = str(args.get("text", ""))
        stream_id = str(args.get("stream_id", ""))
        sync_to_maisaka_history = bool(args.get("sync_to_maisaka_history", False))
        maisaka_source_kind = str(args.get("maisaka_source_kind", "plugin_send") or "plugin_send")
        if not text or not stream_id:
            return {"success": False, "error": "缺少必要参数 text 或 stream_id"}

        try:
            result = await send_api.text_to_stream(
                text=text,
                stream_id=stream_id,
                typing=bool(args.get("typing", False)),
                set_reply=bool(args.get("set_reply", False)),
                storage_message=bool(args.get("storage_message", True)),
                sync_to_maisaka_history=sync_to_maisaka_history,
                maisaka_source_kind=maisaka_source_kind,
            )
            return {"success": result}
        except Exception as exc:
            logger.error(f"[cap.send.text] 执行失败: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

    async def _cap_send_emoji(self, plugin_id: str, capability: str, args: Dict[str, Any]) -> Any:
        """向指定流发送表情图片。

        Args:
            plugin_id: 插件标识。
            capability: 能力名称。
            args: 能力调用参数。

        Returns:
            Any: 能力执行结果。
        """
        del plugin_id, capability
        from src.services import send_service as send_api

        emoji_base64 = str(args.get("emoji_base64", ""))
        stream_id = str(args.get("stream_id", ""))
        sync_to_maisaka_history = bool(args.get("sync_to_maisaka_history", False))
        maisaka_source_kind = str(args.get("maisaka_source_kind", "plugin_send") or "plugin_send")
        if not emoji_base64 or not stream_id:
            return {"success": False, "error": "缺少必要参数 emoji_base64 或 stream_id"}

        try:
            result = await send_api.emoji_to_stream(
                emoji_base64=emoji_base64,
                stream_id=stream_id,
                storage_message=bool(args.get("storage_message", True)),
                sync_to_maisaka_history=sync_to_maisaka_history,
                maisaka_source_kind=maisaka_source_kind,
            )
            return {"success": result}
        except Exception as exc:
            logger.error(f"[cap.send.emoji] 执行失败: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

    async def _cap_send_image(self, plugin_id: str, capability: str, args: Dict[str, Any]) -> Any:
        """向指定流发送图片。

        Args:
            plugin_id: 插件标识。
            capability: 能力名称。
            args: 能力调用参数。

        Returns:
            Any: 能力执行结果。
        """
        del plugin_id, capability
        from src.services import send_service as send_api

        image_base64 = str(args.get("image_base64", ""))
        stream_id = str(args.get("stream_id", ""))
        sync_to_maisaka_history = bool(args.get("sync_to_maisaka_history", False))
        maisaka_source_kind = str(args.get("maisaka_source_kind", "plugin_send") or "plugin_send")
        if not image_base64 or not stream_id:
            return {"success": False, "error": "缺少必要参数 image_base64 或 stream_id"}

        try:
            result = await send_api.image_to_stream(
                image_base64=image_base64,
                stream_id=stream_id,
                storage_message=bool(args.get("storage_message", True)),
                sync_to_maisaka_history=sync_to_maisaka_history,
                maisaka_source_kind=maisaka_source_kind,
            )
            return {"success": result}
        except Exception as exc:
            logger.error(f"[cap.send.image] 执行失败: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

    async def _cap_send_command(self, plugin_id: str, capability: str, args: Dict[str, Any]) -> Any:
        """向指定流发送命令消息。

        Args:
            plugin_id: 插件标识。
            capability: 能力名称。
            args: 能力调用参数。

        Returns:
            Any: 能力执行结果。
        """
        del plugin_id, capability
        from src.services import send_service as send_api

        command = str(args.get("command", ""))
        stream_id = str(args.get("stream_id", ""))
        sync_to_maisaka_history = bool(args.get("sync_to_maisaka_history", False))
        maisaka_source_kind = str(args.get("maisaka_source_kind", "plugin_send") or "plugin_send")
        if not command or not stream_id:
            return {"success": False, "error": "缺少必要参数 command 或 stream_id"}

        try:
            result = await send_api.custom_to_stream(
                message_type="command",
                content=command,
                stream_id=stream_id,
                storage_message=bool(args.get("storage_message", True)),
                processed_plain_text=str(args.get("processed_plain_text", "")),
                sync_to_maisaka_history=sync_to_maisaka_history,
                maisaka_source_kind=maisaka_source_kind,
            )
            return {"success": result}
        except Exception as exc:
            logger.error(f"[cap.send.command] 执行失败: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

    async def _cap_send_custom(self, plugin_id: str, capability: str, args: Dict[str, Any]) -> Any:
        """向指定流发送自定义消息。

        Args:
            plugin_id: 插件标识。
            capability: 能力名称。
            args: 能力调用参数。

        Returns:
            Any: 能力执行结果。
        """
        del plugin_id, capability
        from src.services import send_service as send_api

        message_type = str(args.get("message_type", "") or args.get("custom_type", ""))
        content = args.get("content")
        if content is None:
            content = args.get("data", "")
        stream_id = str(args.get("stream_id", ""))
        sync_to_maisaka_history = bool(args.get("sync_to_maisaka_history", False))
        maisaka_source_kind = str(args.get("maisaka_source_kind", "plugin_send") or "plugin_send")
        if not message_type or not stream_id:
            return {"success": False, "error": "缺少必要参数 message_type 或 stream_id"}

        try:
            result = await send_api.custom_to_stream(
                message_type=message_type,
                content=content,
                stream_id=stream_id,
                processed_plain_text=str(args.get("processed_plain_text", "")),
                typing=bool(args.get("typing", False)),
                storage_message=bool(args.get("storage_message", True)),
                sync_to_maisaka_history=sync_to_maisaka_history,
                maisaka_source_kind=maisaka_source_kind,
            )
            return {"success": result}
        except Exception as exc:
            logger.error(f"[cap.send.custom] 执行失败: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

    async def _cap_llm_generate(self, plugin_id: str, capability: str, args: Dict[str, Any]) -> Any:
        """执行无工具的 LLM 生成能力。

        Args:
            plugin_id: 插件标识。
            capability: 能力名称。
            args: 能力调用参数。

        Returns:
            Any: 标准化后的 LLM 响应结构。
        """
        del capability
        from src.services import llm_service as llm_api

        try:
            prompt = _normalize_prompt_arg(args.get("prompt"))
            task_name = llm_api.resolve_task_name(str(args.get("model", "") or args.get("model_name", "")))
            result = await llm_api.generate(
                llm_api.LLMServiceRequest(
                    task_name=task_name,
                    request_type=f"plugin.{plugin_id}",
                    prompt=prompt,
                    temperature=args.get("temperature"),
                    max_tokens=args.get("max_tokens"),
                )
            )
            return result.to_capability_payload()
        except Exception as exc:
            logger.error(f"[cap.llm.generate] 执行失败: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

    async def _cap_llm_generate_with_tools(self, plugin_id: str, capability: str, args: Dict[str, Any]) -> Any:
        """执行带工具的 LLM 生成能力。

        Args:
            plugin_id: 插件标识。
            capability: 能力名称。
            args: 能力调用参数。

        Returns:
            Any: 标准化后的 LLM 响应结构。
        """
        del capability
        from src.services import llm_service as llm_api

        tool_options = args.get("tools") or args.get("tool_options")
        if tool_options is not None and not isinstance(tool_options, list):
            return {"success": False, "error": "tools 必须为列表"}

        try:
            prompt = _normalize_prompt_arg(args.get("prompt"))
            task_name = llm_api.resolve_task_name(str(args.get("model", "") or args.get("model_name", "")))
            result = await llm_api.generate(
                llm_api.LLMServiceRequest(
                    task_name=task_name,
                    request_type=f"plugin.{plugin_id}",
                    prompt=prompt,
                    tool_options=tool_options,
                    temperature=args.get("temperature"),
                    max_tokens=args.get("max_tokens"),
                )
            )
            return result.to_capability_payload()
        except Exception as exc:
            logger.error(f"[cap.llm.generate_with_tools] 执行失败: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

    async def _cap_llm_get_available_models(self, plugin_id: str, capability: str, args: Dict[str, Any]) -> Any:
        """获取当前宿主可用的模型任务列表。

        Args:
            plugin_id: 插件标识。
            capability: 能力名称。
            args: 能力调用参数。

        Returns:
            Any: 可用模型列表。
        """
        del plugin_id, capability, args
        from src.services import llm_service as llm_api

        try:
            models = llm_api.get_available_models()
            return {"success": True, "models": list(models.keys())}
        except Exception as exc:
            logger.error(f"[cap.llm.get_available_models] 执行失败: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

    async def _cap_config_get(self, plugin_id: str, capability: str, args: Dict[str, Any]) -> Any:
        """读取宿主全局配置中的单个字段。

        Args:
            plugin_id: 插件标识。
            capability: 能力名称。
            args: 能力调用参数。

        Returns:
            Any: 配置读取结果。
        """
        del plugin_id, capability
        key = str(args.get("key", ""))
        default = args.get("default")
        if not key:
            return {"success": False, "value": None, "error": "缺少必要参数 key"}

        try:
            value = _get_nested_config_value(global_config, key, default)
            return {"success": True, "value": value}
        except Exception as exc:
            return {"success": False, "value": None, "error": str(exc)}

    async def _cap_config_get_plugin(self, plugin_id: str, capability: str, args: Dict[str, Any]) -> Any:
        """读取指定插件的配置。

        Args:
            plugin_id: 当前插件标识。
            capability: 能力名称。
            args: 能力调用参数。

        Returns:
            Any: 配置读取结果。
        """
        del capability
        from src.plugin_runtime.component_query import component_query_service

        plugin_name = str(args.get("plugin_name", plugin_id))
        key = str(args.get("key", ""))
        default = args.get("default")

        try:
            config = component_query_service.get_plugin_config(plugin_name)
            if config is None:
                return {"success": False, "value": default, "error": f"未找到插件 {plugin_name} 的配置"}
            if key:
                value = _get_nested_config_value(config, key, default)
                return {"success": True, "value": value}
            return {"success": True, "value": config}
        except Exception as exc:
            return {"success": False, "value": default, "error": str(exc)}

    async def _cap_config_get_all(self, plugin_id: str, capability: str, args: Dict[str, Any]) -> Any:
        """读取指定插件的全部配置。

        Args:
            plugin_id: 当前插件标识。
            capability: 能力名称。
            args: 能力调用参数。

        Returns:
            Any: 配置读取结果。
        """
        del capability
        from src.plugin_runtime.component_query import component_query_service

        plugin_name = str(args.get("plugin_name", plugin_id))
        try:
            config = component_query_service.get_plugin_config(plugin_name)
            if config is None:
                return {"success": True, "value": {}}
            return {"success": True, "value": config}
        except Exception as exc:
            return {"success": False, "value": {}, "error": str(exc)}
