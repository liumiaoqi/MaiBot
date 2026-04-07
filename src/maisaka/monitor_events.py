"""MaiSaka 实时监控事件广播模块。

通过统一 WebSocket 将 MaiSaka 推理引擎各阶段状态实时推送给前端监控界面。
"""

from datetime import datetime
import time
from typing import Any, Dict, List, Optional

from src.common.logger import get_logger

logger = get_logger("maisaka_monitor")

MONITOR_DOMAIN = "maisaka_monitor"
MONITOR_TOPIC = "main"


def _normalize_payload_value(value: Any) -> Any:
    """将事件载荷中的任意值规范化为可序列化结构。"""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        normalized_dict: Dict[str, Any] = {}
        for key, item in value.items():
            normalized_dict[str(key)] = _normalize_payload_value(item)
        return normalized_dict
    if isinstance(value, (list, tuple, set)):
        return [_normalize_payload_value(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return _normalize_payload_value(value.model_dump())
        except Exception:
            return str(value)
    if hasattr(value, "__dict__"):
        try:
            return _normalize_payload_value(dict(value.__dict__))
        except Exception:
            return str(value)
    return str(value)


def _extract_text_content(content: Any) -> Optional[str]:
    """从消息内容中提取纯文本表示。"""

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
    """将工具调用对象列表序列化为字典列表。"""

    result: List[Dict[str, Any]] = []
    for tool_call in tool_calls:
        serialized: Dict[str, Any] = {
            "id": getattr(tool_call, "id", None) or getattr(tool_call, "call_id", ""),
            "name": getattr(tool_call, "func_name", None) or getattr(tool_call, "name", "unknown"),
        }
        args = getattr(tool_call, "args", None) or getattr(tool_call, "arguments", None)
        if isinstance(args, dict):
            serialized["arguments"] = _normalize_payload_value(args)
        elif isinstance(args, str):
            serialized["arguments_raw"] = args
        result.append(serialized)
    return result


def _serialize_tool_calls_from_dicts(tool_calls: List[Any]) -> List[Dict[str, Any]]:
    """将工具调用字典列表标准化为可传输格式。"""

    result: List[Dict[str, Any]] = []
    for tool_call in tool_calls:
        if isinstance(tool_call, dict):
            result.append({
                "id": str(tool_call.get("id", "")),
                "name": str(tool_call.get("name", tool_call.get("func_name", "unknown"))),
                "arguments": _normalize_payload_value(tool_call.get("arguments", tool_call.get("args", {}))),
            })
            continue

        result.append({
            "id": str(getattr(tool_call, "id", getattr(tool_call, "call_id", ""))),
            "name": str(getattr(tool_call, "func_name", getattr(tool_call, "name", "unknown"))),
            "arguments": _normalize_payload_value(getattr(tool_call, "args", getattr(tool_call, "arguments", {}))),
        })
    return result


def _serialize_message(message: Any) -> Dict[str, Any]:
    """将单条消息序列化为可通过 WebSocket 传输的字典。"""

    if isinstance(message, dict):
        serialized: Dict[str, Any] = {
            "role": str(message.get("role", "unknown")),
            "content": _extract_text_content(message.get("content")),
        }
        if message.get("tool_call_id"):
            serialized["tool_call_id"] = str(message["tool_call_id"])
        if message.get("tool_calls"):
            serialized["tool_calls"] = _serialize_tool_calls_from_dicts(message["tool_calls"])
        return serialized

    raw_role = getattr(message, "role", "unknown")
    role_str = raw_role.value if hasattr(raw_role, "value") else str(raw_role)

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


def _serialize_messages(messages: List[Any]) -> List[Dict[str, Any]]:
    """批量序列化消息列表。"""

    return [_serialize_message(message) for message in messages]


def _serialize_tool_results(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """标准化最终 planner 卡中的工具结果列表。"""

    serialized_tools: List[Dict[str, Any]] = []
    for tool in tools:
        serialized_tool = {
            "tool_call_id": str(tool.get("tool_call_id", "")),
            "tool_name": str(tool.get("tool_name", "")),
            "tool_args": _normalize_payload_value(tool.get("tool_args", {})),
            "success": bool(tool.get("success", False)),
            "duration_ms": float(tool.get("duration_ms", 0.0) or 0.0),
            "summary": str(tool.get("summary", "")),
        }
        detail = tool.get("detail")
        if detail is not None:
            serialized_tool["detail"] = _normalize_payload_value(detail)
        serialized_tools.append(serialized_tool)
    return serialized_tools


async def _broadcast(event: str, data: Dict[str, Any]) -> None:
    """通过统一 WebSocket 管理器向监控主题广播事件。"""

    try:
        from src.webui.routers.websocket.manager import websocket_manager

        subscription_key = f"{MONITOR_DOMAIN}:{MONITOR_TOPIC}"
        total_connections = len(websocket_manager.connections)
        subscriber_count = sum(
            1
            for connection in websocket_manager.connections.values()
            if subscription_key in connection.subscriptions
        )
        logger.info(
            f"[诊断] _broadcast: manager_id={id(websocket_manager)} "
            f"总连接={total_connections} 订阅者={subscriber_count} event={event}"
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
    """广播会话开始事件。"""

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
    """广播新消息注入事件。"""

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
    """广播推理循环开始事件。"""

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
    """广播 Timing Gate 结果事件。"""

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


async def emit_planner_finalized(
    *,
    session_id: str,
    cycle_id: int,
    request_messages: List[Any],
    selected_history_count: int,
    tool_count: int,
    planner_content: Optional[str],
    planner_tool_calls: List[Any],
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    duration_ms: float,
    tools: List[Dict[str, Any]],
    time_records: Dict[str, float],
    agent_state: str,
) -> None:
    """广播一轮 planner 结束后的最终聚合事件。"""

    await _broadcast("planner.finalized", {
        "session_id": session_id,
        "cycle_id": cycle_id,
        "timestamp": time.time(),
        "request": {
            "messages": _serialize_messages(request_messages),
            "selected_history_count": selected_history_count,
            "tool_count": tool_count,
        },
        "planner": {
            "content": planner_content,
            "tool_calls": _serialize_tool_calls_from_objects(planner_tool_calls),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "duration_ms": duration_ms,
        },
        "tools": _serialize_tool_results(tools),
        "final_state": {
            "time_records": _normalize_payload_value(time_records),
            "agent_state": agent_state,
        },
    })
