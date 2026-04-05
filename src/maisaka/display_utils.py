"""Maisaka 展示辅助工具。"""

from typing import Any


_REQUEST_PANEL_STYLE_MAP: dict[str, tuple[str, str]] = {
    "timing_gate": ("\u004d\u0061\u0069\u0053\u0061\u006b\u0061 \u5927\u6a21\u578b\u8bf7\u6c42 - Timing Gate \u5b50\u4ee3\u7406", "bright_magenta"),
    "replyer": ("\u004d\u0061\u0069\u0053\u0061\u006b\u0061 \u56de\u590d\u5668 Prompt", "bright_yellow"),
    "sub_agent": ("\u004d\u0061\u0069\u0053\u0061\u006b\u0061 \u5927\u6a21\u578b\u8bf7\u6c42 - \u5b50\u4ee3\u7406", "bright_blue"),
}

_DEFAULT_REQUEST_PANEL_STYLE: tuple[str, str] = (
    "\u004d\u0061\u0069\u0053\u0061\u006b\u0061 \u5927\u6a21\u578b\u8bf7\u6c42 - \u5bf9\u8bdd\u5355\u6b65",
    "cyan",
)

_ROLE_BADGE_STYLE_MAP: dict[str, str] = {
    "system": "bold white on blue",
    "user": "bold black on green",
    "assistant": "bold black on yellow",
    "tool": "bold white on magenta",
}

_ROLE_BADGE_LABEL_MAP: dict[str, str] = {
    "system": "\u7cfb\u7edf",
    "user": "\u7528\u6237",
    "assistant": "\u52a9\u624b",
    "tool": "\u5de5\u5177",
}


def format_token_count(token_count: int) -> str:
    """格式化 token 数量展示文本。"""

    if token_count >= 10_000:
        return f"{token_count / 1000:.1f}k"
    return str(token_count)


def get_request_panel_style(request_kind: str) -> tuple[str, str]:
    """返回不同请求类型对应的标题与边框颜色。"""

    normalized_kind = str(request_kind or "planner").strip().lower()
    return _REQUEST_PANEL_STYLE_MAP.get(normalized_kind, _DEFAULT_REQUEST_PANEL_STYLE)


def get_role_badge_style(role: str) -> str:
    """返回角色标签对应的 rich 样式。"""

    return _ROLE_BADGE_STYLE_MAP.get(role, "bold white on bright_black")


def get_role_badge_label(role: str) -> str:
    """返回角色标签对应的展示文案。"""

    return _ROLE_BADGE_LABEL_MAP.get(role, "\u672a\u77e5")


def format_tool_call_for_display(tool_call: Any) -> dict[str, Any]:
    """将不同来源的工具调用对象规范化为统一展示结构。"""

    if isinstance(tool_call, dict):
        function_info = tool_call.get("function", {})
        return {
            "id": tool_call.get("id"),
            "name": function_info.get("name", tool_call.get("name")),
            "arguments": function_info.get("arguments", tool_call.get("arguments")),
        }

    return {
        "id": getattr(tool_call, "call_id", getattr(tool_call, "id", None)),
        "name": getattr(tool_call, "func_name", getattr(tool_call, "name", None)),
        "arguments": getattr(tool_call, "args", getattr(tool_call, "arguments", None)),
    }


def build_tool_call_summary_lines(tool_calls: list[Any]) -> list[str]:
    """构建工具调用摘要文本。"""

    summary_lines: list[str] = []
    for tool_call in tool_calls:
        normalized_tool_call = format_tool_call_for_display(tool_call)
        tool_name = str(normalized_tool_call.get("name") or "").strip() or "unknown"
        tool_args = normalized_tool_call.get("arguments")
        if isinstance(tool_args, dict) and tool_args:
            summary_lines.append(f"- {tool_name}: {tool_args}")
        else:
            summary_lines.append(f"- {tool_name}")
    return summary_lines
