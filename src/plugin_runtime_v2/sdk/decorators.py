"""SDK v4 装饰器 — @Tool/@Event/@Command/@HomeCard。

统一组件模型：Tool（拉取式）+ Event（推送式）。
Command = Tool 语法糖，HomeCard = Event 语法糖。
"""


from dataclasses import dataclass
from typing import Any, Callable

_VALID_WIDTHS = frozenset({"small", "medium", "large", "wide", "full"})

@dataclass(frozen=True)
class ToolDeclaration:
    """MCP Tool 声明信息，由 @Tool 装饰器产生。"""

    name: str
    description: str
    parameters_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    pattern: str | None = None


@dataclass(frozen=True)
class EventDeclaration:
    """MCP Event 声明信息，由 @Event/@HomeCard 装饰器产生。"""

    name: str
    description: str
    event_schema: dict[str, Any] | None = None
    card_metadata: dict[str, Any] | None = None


def Tool(
    *,
    name: str,
    description: str,
    parameters_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> Callable:
    """MCP Tool 装饰器 — 声明一个拉取式组件。

    被 @Tool 装饰的方法会在 LLM 工具循环中被调用。
    Host 将此 Tool 注册到 ThinkingOrgan 的工具列表，
    LLM 决定何时调用。

    Args:
        name: 工具名称，全局唯一，建议使用 plugin_id.tool_name 格式
        description: 工具描述，供 LLM 理解用途
        parameters_schema: 参数 JSON Schema，描述工具接受的参数
        output_schema: 输出 JSON Schema，描述工具返回的结果

    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        func._mcp_tool = ToolDeclaration(
            name=name,
            description=description,
            parameters_schema=parameters_schema,
            output_schema=output_schema,
        )
        return func

    return decorator


def Event(
    *,
    name: str,
    description: str,
    event_schema: dict[str, Any] | None = None,
) -> Callable:
    """MCP Event 装饰器 — 声明一个推送式组件。

    被 @Event 装饰的方法定义了 Event 的载荷结构。
    插件在运行时主动推送 Event，Host 订阅后接收。

    Args:
        name: 事件名称，全局唯一，建议使用 plugin_id.event_name 格式
        description: 事件描述
        event_schema: 事件载荷 JSON Schema

    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        func._mcp_event = EventDeclaration(
            name=name,
            description=description,
            event_schema=event_schema,
        )
        return func

    return decorator


def Command(
    *,
    name: str,
    pattern: str,
    description: str = "",
    parameters_schema: dict[str, Any] | None = None,
) -> Callable:
    """命令装饰器 — @Tool 的语法糖。

    底层实现为注册一个匹配命令模式的 Tool。
    当用户消息匹配 pattern 时，LLM 优先调用此 Tool。

    Args:
        name: 命令名称
        pattern: 命令匹配模式（正则表达式）
        description: 命令描述
        parameters_schema: 参数 JSON Schema

    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        func._mcp_tool = ToolDeclaration(
            name=name,
            description=description,
            parameters_schema=parameters_schema,
            pattern=pattern,
        )
        return func

    return decorator


def HomeCard(
    *,
    name: str,
    title: str = "",
    description: str = "",
    width: str = "medium",
) -> Callable:
    """首页卡片装饰器 — @Event 的语法糖。

    底层实现为推送 WebUI 卡片数据的 Event。
    插件调用 self.ctx.emit_card(name, data) 时，
    Runner 推送一个 Event，Host 转发到 WebUI。

    Args:
        name: 卡片标识
        title: 卡片标题
        description: 卡片描述
        width: 卡片宽度（small/medium/large/wide/full）

    Returns:
       装饰器函数
    """

    if width not in _VALID_WIDTHS:
        raise ValueError(f"HomeCard width 必须为 small/medium/large/wide/full 之一，得到: {width}")

    def decorator(func: Callable) -> Callable:
        func._mcp_event = EventDeclaration(
            name=name,
            description=description,
            card_metadata={
                "title": title,
                "width": width,
            },
        )
        return func

    return decorator
