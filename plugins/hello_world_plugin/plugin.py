"""Hello World 示例插件 — SDK v4 版本

你的第一个 MaiCore 插件，包含问候功能、时间查询等基础示例。
"""

from __future__ import annotations

import random
import re
from datetime import datetime
from typing import Any

from src.plugin_runtime_v2.sdk import Command, HomeCard, MaiBotPlugin, Tool


class HelloWorldPlugin(MaiBotPlugin):
    """Hello World 示例插件（SDK v4）。"""

    plugin_id = "maibot-team.hello-world-plugin"
    plugin_version = "3.0.0"
    scopes = [
        "message:send:text",
        "message:send:forward",
        "message:send:hybrid",
        "database:read:self",
        "database:write:self",
    ]

    async def on_load(self) -> None:
        self._greeting = "嗨！很开心见到你！"
        self._time_format = "%Y-%m-%d %H:%M:%S"
        self._print_enabled = False
        self._fwd_messages: list[str] = []
        self._fwd_counter: int = 0

    async def on_unload(self) -> None:
        pass

    # ===== HomeCard =====

    @HomeCard(
        name="hello_world_feature_card",
        title="Hello World 功能入口",
        description="展示示例插件提供的命令和工具入口。",
        width="large",
    )
    async def home_feature_card(self) -> None:
        pass

    @HomeCard(
        name="hello_world_data_card",
        title="Hello World 示例数据",
        description="用静态示例数据演示首页数据型卡片。",
        width="medium",
    )
    async def home_data_card(self) -> None:
        pass

    # ===== Tool =====

    @Tool(
        name="compare_numbers",
        description="比较两个数的大小，返回较大的数",
        parameters_schema={
            "type": "object",
            "properties": {
                "num1": {"type": "number", "description": "第一个数字"},
                "num2": {"type": "number", "description": "第二个数字"},
            },
            "required": ["num1", "num2"],
        },
    )
    async def handle_compare_numbers(self, args: dict[str, Any]) -> dict[str, Any]:
        num1 = args.get("num1", 0)
        num2 = args.get("num2", 0)
        if num1 > num2:
            result = f"{num1} 大于 {num2}"
        elif num1 < num2:
            result = f"{num1} 小于 {num2}"
        else:
            result = f"{num1} 等于 {num2}"
        return {"name": "compare_numbers", "content": result}

    # ===== Command =====

    @Command(
        name="time",
        pattern=r"^/time$",
        description="查询当前时间",
    )
    async def handle_time(self, args: dict[str, Any]) -> dict[str, Any]:
        session_id = args.get("session_id", "")
        now = datetime.now()
        time_str = now.strftime(self._time_format)
        if session_id:
            await self.ctx.send.text(session_id, f"⏰ 当前时间：{time_str}")
        return {"success": True, "content": time_str}

    @Command(
        name="test",
        pattern=r"^/test$",
        description="测试命令",
    )
    async def handle_test(self, args: dict[str, Any]) -> dict[str, Any]:
        session_id = args.get("session_id", "")
        if session_id:
            await self.ctx.send.text(session_id, "测试正常！Bot 功能运行中 ✅")
        return {"success": True}

    @Command(
        name="send_to",
        pattern=r"^/send_to\s+(?P<target_session_id>\S+)\s+(?P<text>.+)$",
        description="向指定聊天流发送文本",
    )
    async def handle_send_to(self, args: dict[str, Any]) -> dict[str, Any]:
        session_id = args.get("session_id", "")
        raw_text = args.get("raw_text", "")
        match = re.match(r"^/send_to\s+(?P<target_session_id>\S+)\s+(?P<text>.+)$", raw_text, re.DOTALL)
        if not match:
            return {"success": False, "error": "用法：/send_to <session_id> <要发送的文本>"}

        target_session_id = match.group("target_session_id").strip()
        text = match.group("text").strip()
        if not target_session_id or not text:
            return {"success": False, "error": "参数不完整"}

        await self.ctx.send.text(target_session_id, text)
        if session_id and session_id != target_session_id:
            await self.ctx.send.text(session_id, f"已向 {target_session_id} 发送文本")
        return {"success": True}

    @Command(
        name="random_emojis",
        pattern=r"^/random_emojis$",
        description="发送随机表情包（演示 hybrid 发送）",
    )
    async def handle_random_emojis(self, args: dict[str, Any]) -> dict[str, Any]:
        session_id = args.get("session_id", "")
        if not session_id:
            return {"success": False, "error": "无 session_id"}

        emojis = [f"emoji_{random.randint(1, 100)}" for _ in range(3)]
        segments = [{"type": "text", "data": {"text": f"随机表情包：{', '.join(emojis)}"}}]
        await self.ctx.send.hybrid(session_id, segments)
        return {"success": True}


def create_plugin() -> HelloWorldPlugin:
    """创建 Hello World 示例插件实例。"""
    return HelloWorldPlugin()
