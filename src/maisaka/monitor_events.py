"""MaiSaka 实时监控事件广播模块。

通过统一 WebSocket 将 MaiSaka 推理引擎各阶段的状态实时推送给前端监控界面，
无需落盘 HTML/TXT 中间文件即可在 WebUI 中渲染完整的聊天流推理过程。
"""

from typing import Any, Dict, List, Optional

import time

from src.common.logger import get_logger

logger = get_logger("maisaka_monitor")

# WebSocket 广播使用的业务域与主题
MONITOR_DOMAIN = "maisaka_monitor"
MONITOR_TOPIC = "main"


def _serialize_message(message: Any) -> Dict[str, Any]:
    """将单条 LLM 消息序列化为可通过 WebSocket 传输的字典。

    对二进制数据（如图片）仅保留元信息，不传输原始字节以减小带宽占用。

    Args:
        message: 原始消息对象，可以是 dict 或带 role/content 属性的消息实例。

    Returns:
        Dict[str, Any]: 序列化后的消息字典。
    """
    if isinstance(message, dict):
        serialized: Dict[str, Any] = {
            "role": str(message.get("role", "unknown")),
            "content": message.get("content"),
        }
        if message.get("tool_call_id"):
            serialized["tool_call_id"] = message["tool_call_id"]
        if message.get("tool_calls"):
            serialized["tool_calls"] = _serialize_tool_calls_from_dicts(message["tool_calls"])
        return serialized

    raw_role = getattr(message, "role", "unknown")
    role_str = raw_role.value if hasattr(raw_role, "value") else str(raw_role)  # type: ignore[union-attr]

    serialized = {
        "role": role_str,
        "content": _extract_text_content(getattr(message, "content", None)),
    }

    tool_call_id = getattr(message, "tool_call_id", None)
    if tool_call_id:
        serialized["tool_call_id"] = str(tool_call_id)

    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        serialized["tool_calls"] = _serialize_tool_calls_from_objects(tool_calls)

    return serialized


def _extract_text_content(content: Any) -> Optional[str]:
    """从消息内容中提取纯文本表示。

    支持字符串、列表（多模态内容块）等格式，对图片仅保留占位信息。

    Args:
        content: 消息的原始 content 字段。

    Returns:
        Optional[str]: 提取后的文本内容。
    """
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: List[str] = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    text_parts.append(str(block.get("text", "")))
                elif block_type == "image_url":
                    text_parts.append("[图片]")
                else:
                    text_parts.append(f"[{block_type}]")
            elif isinstance(block, str):
                text_parts.append(block)
        return "\n".join(text_parts) if text_parts else None
    return str(content)


def _serialize_tool_calls_from_objects(tool_calls: List[Any]) -> List[Dict[str, Any]]:
    """将工具调用对象列表序列化为字典列表。

    Args:
        tool_calls: 工具调用对象列表（ToolCall 或类似结构）。

    Returns:
        List[Dict[str, Any]]: 序列化后的工具调用列表。
    """
    result: List[Dict[str, Any]] = []
    for tc in tool_calls:
        serialized: Dict[str, Any] = {
            "id": getattr(tc, "id", None) or getattr(tc, "tool_call_id", ""),
            "name": getattr(tc, "func_name", None) or getattr(tc, "name", "unknown"),
        }
        args = getattr(tc, "args", None) or getattr(tc, "arguments", None)
        if isinstance(args, dict):
            serialized["arguments"] = args
        elif isinstance(args, str):
            serialized["arguments_raw"] = args
        result.append(serialized)
    return result


def _serialize_tool_calls_from_dicts(tool_calls: List[Any]) -> List[Dict[str, Any]]:
    """将工具调用字典列表标准化为可传输格式。

    Args:
        tool_calls: 工具调用字典列表。

    Returns:
        List[Dict[str, Any]]: 标准化后的工具调用列表。
    """
    result: List[Dict[str, Any]] = []
    for tc in tool_calls:
        if isinstance(tc, dict):
            result.append({
                "id": tc.get("id", ""),
                "name": tc.get("name", tc.get("func_name", "unknown")),
                "arguments": tc.get("arguments", tc.get("args", {})),
            })
        else:
            result.append({
                "id": getattr(tc, "id", ""),
                "name": getattr(tc, "func_name", "unknown"),
                "arguments": getattr(tc, "args", {}),
            })
    return result


def _serialize_messages(messages: List[Any]) -> List[Dict[str, Any]]:
    """批量序列化消息列表。

    Args:
        messages: 原始消息列表。

    Returns:
        List[Dict[str, Any]]: 序列化后的消息字典列表。
    """
    return [_serialize_message(msg) for msg in messages]


async def _broadcast(event: str, data: Dict[str, Any]) -> None:
    """通过统一 WebSocket 管理器向所有订阅了 maisaka_monitor 主题的连接广播事件。

    延迟导入 websocket_manager 以避免循环依赖。

    Args:
        event: 事件名称。
        data: 事件数据。
    """
    try:
        from src.webui.routers.websocket.manager import websocket_manager

        subscription_key = f"{MONITOR_DOMAIN}:{MONITOR_TOPIC}"
        total_connections = len(websocket_manager.connections)
        subscriber_count = sum(
            1 for conn in websocket_manager.connections.values()
            if subscription_key in conn.subscriptions
        )

        # 诊断：打印 manager 对象 id 和连接状态
        logger.info(
            f"[诊断] _broadcast: manager_id={id(websocket_manager)} "
            f"总连接={total_connections} 订阅者={subscriber_count} event={event}"
        )
        if subscriber_count == 0 and total_connections > 0:
            for cid, conn in websocket_manager.connections.items():
                logger.info(
                    f"[诊断] 连接={cid[:8]}… 订阅={conn.subscriptions}"
                )

        await websocket_manager.broadcast_to_topic(
            domain=MONITOR_DOMAIN,
            topic=MONITOR_TOPIC,
            event=event,
            data=data,
        )
    except Exception as exc:
        logger.warning(f"MaiSaka 监控事件广播失败: {exc}", exc_info=True)


async def emit_session_start(session_id: str, session_name: str) -> None:
    """广播会话开始事件。

    Args:
        session_id: 聊天流 ID。
        session_name: 聊天流显示名称。
    """
    await _broadcast("session.start", {
        "session_id": session_id,
        "session_name": session_name,
        "timestamp": time.time(),
    })


async def emit_message_ingested(
    session_id: str,
    speaker_name: str,
    content: str,
    message_id: str,
    timestamp: float,
) -> None:
    """广播新消息注入事件。

    当新的用户消息被纳入 MaiSaka 推理上下文时触发。

    Args:
        session_id: 聊天流 ID。
        speaker_name: 发言者名称。
        content: 消息文本内容。
        message_id: 消息 ID。
        timestamp: 消息时间戳。
    """
    await _broadcast("message.ingested", {
        "session_id": session_id,
        "speaker_name": speaker_name,
        "content": content,
        "message_id": message_id,
        "timestamp": timestamp,
    })


async def emit_cycle_start(
    session_id: str,
    cycle_id: int,
    round_index: int,
    max_rounds: int,
    history_count: int,
) -> None:
    """广播推理循环开始事件。

    Args:
        session_id: 聊天流 ID。
        cycle_id: 循环编号。
        round_index: 当前回合索引（从 0 开始）。
        max_rounds: 最大回合数。
        history_count: 当前上下文消息数。
    """
    await _broadcast("cycle.start", {
        "session_id": session_id,
        "cycle_id": cycle_id,
        "round_index": round_index,
        "max_rounds": max_rounds,
        "history_count": history_count,
        "timestamp": time.time(),
    })


async def emit_timing_gate_result(
    session_id: str,
    cycle_id: int,
    action: str,
    content: Optional[str],
    tool_calls: List[Any],
    messages: List[Any],
    prompt_tokens: int,
    selected_history_count: int,
    duration_ms: float,
) -> None:
    """广播 Timing Gate 子代理结果事件。

    Args:
        session_id: 聊天流 ID。
        cycle_id: 循环编号。
        action: 控制决策（continue/wait/no_reply）。
        content: Timing Gate 返回的文本内容。
        tool_calls: 工具调用列表。
        messages: 发送给 Timing Gate 的消息列表。
        prompt_tokens: 输入 Token 数。
        selected_history_count: 已选上下文消息数。
        duration_ms: 执行耗时（毫秒）。
    """
    await _broadcast("timing_gate.result", {
        "session_id": session_id,
        "cycle_id": cycle_id,
        "action": action,
        "content": content,
        "tool_calls": _serialize_tool_calls_from_objects(tool_calls),
        "messages": _serialize_messages(messages),
        "prompt_tokens": prompt_tokens,
        "selected_history_count": selected_history_count,
        "duration_ms": duration_ms,
        "timestamp": time.time(),
    })


async def emit_planner_request(
    session_id: str,
    cycle_id: int,
    messages: List[Any],
    tool_count: int,
    selected_history_count: int,
) -> None:
    """广播规划器请求开始事件。

    携带完整的消息列表，前端可以增量渲染新增消息。

    Args:
        session_id: 聊天流 ID。
        cycle_id: 循环编号。
        messages: 发送给规划器的完整消息列表。
        tool_count: 可用工具数量。
        selected_history_count: 已选上下文消息数。
    """
    await _broadcast("planner.request", {
        "session_id": session_id,
        "cycle_id": cycle_id,
        "messages": _serialize_messages(messages),
        "tool_count": tool_count,
        "selected_history_count": selected_history_count,
        "timestamp": time.time(),
    })


async def emit_planner_response(
    session_id: str,
    cycle_id: int,
    content: Optional[str],
    tool_calls: List[Any],
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    duration_ms: float,
) -> None:
    """广播规划器响应事件。

    Args:
        session_id: 聊天流 ID。
        cycle_id: 循环编号。
        content: 规划器返回的思考文本。
        tool_calls: 规划器返回的工具调用列表。
        prompt_tokens: 输入 Token 数。
        completion_tokens: 输出 Token 数。
        total_tokens: 总 Token 数。
        duration_ms: 执行耗时（毫秒）。
    """
    await _broadcast("planner.response", {
        "session_id": session_id,
        "cycle_id": cycle_id,
        "content": content,
        "tool_calls": _serialize_tool_calls_from_objects(tool_calls),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "duration_ms": duration_ms,
        "timestamp": time.time(),
    })


async def emit_tool_execution(
    session_id: str,
    cycle_id: int,
    tool_name: str,
    tool_args: Dict[str, Any],
    result_summary: str,
    success: bool,
    duration_ms: float,
) -> None:
    """广播工具执行结果事件。

    Args:
        session_id: 聊天流 ID。
        cycle_id: 循环编号。
        tool_name: 工具名称。
        tool_args: 工具参数。
        result_summary: 执行结果摘要。
        success: 是否成功。
        duration_ms: 执行耗时（毫秒）。
    """
    await _broadcast("tool.execution", {
        "session_id": session_id,
        "cycle_id": cycle_id,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "result_summary": result_summary,
        "success": success,
        "duration_ms": duration_ms,
        "timestamp": time.time(),
    })


async def emit_cycle_end(
    session_id: str,
    cycle_id: int,
    time_records: Dict[str, float],
    agent_state: str,
) -> None:
    """广播推理循环结束事件。

    Args:
        session_id: 聊天流 ID。
        cycle_id: 循环编号。
        time_records: 各阶段耗时记录。
        agent_state: 循环结束后的代理状态。
    """
    await _broadcast("cycle.end", {
        "session_id": session_id,
        "cycle_id": cycle_id,
        "time_records": time_records,
        "agent_state": agent_state,
        "timestamp": time.time(),
    })


async def emit_replier_request(
    session_id: str,
    messages: List[Any],
    model_name: str = "",
) -> None:
    """广播回复器请求开始事件。

    Args:
        session_id: 聊天流 ID。
        messages: 发送给回复器的消息列表。
        model_name: 使用的模型名称。
    """
    await _broadcast("replier.request", {
        "session_id": session_id,
        "messages": _serialize_messages(messages),
        "model_name": model_name,
        "timestamp": time.time(),
    })


async def emit_replier_response(
    session_id: str,
    content: Optional[str],
    reasoning: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    duration_ms: float,
    success: bool,
) -> None:
    """广播回复器响应事件。

    Args:
        session_id: 聊天流 ID。
        content: 回复器生成的文本。
        reasoning: 回复器的思考过程文本。
        model_name: 使用的模型名称。
        prompt_tokens: 输入 Token 数。
        completion_tokens: 输出 Token 数。
        total_tokens: 总 Token 数。
        duration_ms: 执行耗时（毫秒）。
        success: 是否生成成功。
    """
    await _broadcast("replier.response", {
        "session_id": session_id,
        "content": content,
        "reasoning": reasoning,
        "model_name": model_name,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "duration_ms": duration_ms,
        "success": success,
        "timestamp": time.time(),
    })
