"""ForwardFetchAdapter — 委托全局 ToolRegistry 调用 napcat.get_forward_msg 工具拉取合并转发节点。

适配器层，通过 get_global_tool_registry().invoke() 调用 v2 插件暴露的
napcat.get_forward_msg 工具，不直接持有插件对象（符合微内核隔离）。
"""


import json
from typing import Optional


class ForwardFetchAdapter:
    """合并转发拉取适配器 — 桥接到 napcat.get_forward_msg 插件工具。

    实现 ForwardFetchPort Protocol（duck typing，不显式继承）。
    """

    TOOL_NAME = "napcat.get_forward_msg"

    async def fetch_forward_nodes(self, forward_id: str) -> Optional[list[dict]]:
        """调用 napcat.get_forward_msg 工具拉取转发节点。

        Args:
            forward_id: 合并转发消息 id。

        Returns:
            节点列表（每节点含 user_nickname/user_id/user_cardname/message_id/content）；
            失败时返回 None。
        """
        from src.core.tooling import ToolInvocation, get_global_tool_registry

        registry = get_global_tool_registry()
        invocation = ToolInvocation(
            tool_name=self.TOOL_NAME,
            arguments={"forward_id": forward_id},
        )
        result = await registry.invoke(invocation)
        if not result.success:
            return None

        # @Tool 返回 {"success": True, "result": {"messages": [...]}} 被
        # MCPToolProvider 序列化为 JSON 字符串放入 result.content
        try:
            payload = json.loads(result.content) if result.content else None
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(payload, dict) or not payload.get("success"):
            return None

        data = payload.get("result")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            nodes = data.get("messages")
            if isinstance(nodes, list):
                return nodes
        return None