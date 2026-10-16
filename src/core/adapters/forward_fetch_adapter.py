"""ForwardFetchAdapter — 委托全局 ToolRegistry 调用 napcat.get_forward_msg 工具拉取合并转发节点。

适配器层，通过 get_global_tool_registry().invoke() 调用 v2 插件暴露的
napcat.get_forward_msg 工具，不直接持有插件对象（符合微内核隔离）。
"""


import json
from typing import Optional

from src.common.logger import get_logger

logger = get_logger("core.adapters.forward_fetch_adapter")


class ForwardFetchAdapter:
    """合并转发拉取适配器 — 桥接到 napcat.get_forward_msg 插件工具。

    实现 ForwardFetchPort Protocol（duck typing，不显式继承）。

    ⚠️ **失败一律"出声"**（2026-10-17 `forward-fetch-speak`）：四条失败路径原先**一声不响**地
    返回 None ⇒ 调用方（`src/maisaka/context/messages.py` 的 prefetch）只看得见"没拉到"，
    排障时**分不清**是"工具没注册/没暴露"、"工具调用失败"还是"返回结构不对"。
    ⇒ 现在每条都打**具名 warning**（工具名 + 原因 + 关键上下文）；
    ⇒ ⚠️ **返回值语义不变**（仍 None / list）—— 只出声，不改调用方语义。
    """

    TOOL_NAME = "napcat.get_forward_msg"

    async def fetch_forward_nodes(self, forward_id: str) -> Optional[list[dict]]:
        """调用 napcat.get_forward_msg 工具拉取转发节点。

        Args:
            forward_id: 合并转发消息 id。

        Returns:
            节点列表（每节点含 user_nickname/user_id/user_cardname/message_id/content）；
            失败时返回 None（⚠️ 失败**会**打具名 warning，见类 docstring）。
        """
        from src.core.tooling import ToolInvocation, get_global_tool_registry

        registry = get_global_tool_registry()
        invocation = ToolInvocation(
            tool_name=self.TOOL_NAME,
            arguments={"forward_id": forward_id},
        )
        result = await registry.invoke(invocation)
        if not result.success:
            logger.warning(
                "拉取合并转发失败：工具调用未成功（工具可能未注册/未暴露） | tool=%s forward_id=%s error=%s",
                self.TOOL_NAME,
                forward_id,
                result.error_message or "<无 error_message>",
            )
            return None

        # @Tool 返回 {"success": True, "result": {"messages": [...]}} 被
        # MCPToolProvider 序列化为 JSON 字符串放入 result.content
        try:
            payload = json.loads(result.content) if result.content else None
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "拉取合并转发失败：工具返回的 content 不是合法 JSON | tool=%s forward_id=%s 异常=%s 内容片段=%.200s",
                self.TOOL_NAME,
                forward_id,
                type(exc).__name__,
                result.content,
            )
            return None
        if not isinstance(payload, dict) or not payload.get("success"):
            logger.warning(
                "拉取合并转发失败：工具返回的 payload 不是成功结构 | tool=%s forward_id=%s payload_type=%s success=%r",
                self.TOOL_NAME,
                forward_id,
                type(payload).__name__,
                payload.get("success") if isinstance(payload, dict) else None,
            )
            return None

        data = payload.get("result")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            nodes = data.get("messages")
            if isinstance(nodes, list):
                return nodes
        logger.warning(
            "拉取合并转发失败：工具返回的 result 结构不认识（既非 list，也非含 messages 的 dict）"
            " | tool=%s forward_id=%s result_type=%s keys=%s",
            self.TOOL_NAME,
            forward_id,
            type(data).__name__,
            sorted(data.keys()) if isinstance(data, dict) else None,
        )
        return None