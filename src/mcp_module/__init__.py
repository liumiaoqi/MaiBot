"""
MCP (Model Context Protocol) 客户端包。

提供 MCPManager 用于管理 MCP 服务器连接、发现工具、调用工具。

用法:
    from src.config.config import global_config
    from .manager import MCPManager

    manager = await MCPManager.from_app_config(global_config.mcp)
    if manager:
        tools = manager.get_openai_tools()       # 获取 OpenAI 格式工具列表
        result = await manager.call_tool(name, args)  # 调用工具
        await manager.close()                    # 关闭连接
"""

from .manager import MCPManager

__all__ = ["MCPManager"]
