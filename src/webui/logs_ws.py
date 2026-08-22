"""WebSocket 日志推送模块"""

from pathlib import Path
from typing import Dict, List, Optional, Set

import json
from collections import deque

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from src.common.logger import get_logger
from src.common.logger_color_and_mapping import MODULE_COLORS
from src.webui.core import get_token_manager
from src.webui.routers.websocket.auth import verify_ws_token
from src.webui.routers.websocket.manager import websocket_manager

logger = get_logger("webui.logs_ws")



def _resolve_module_style(module_name: str) -> Dict:
    """解析日志模块在 WebUI 中使用的颜色信息。"""
    module_name = module_name.strip()
    if not module_name:
        return {}

    parts = module_name.split(".")
    for index in range(len(parts), 0, -1):
        candidate = ".".join(parts[:index])
        module_style = MODULE_COLORS.get(candidate)
        if module_style is None:
            continue

        foreground_color, background_color, bold = module_style
        style = {
            "moduleColor": foreground_color,
            "moduleBold": bold,
        }
        if background_color:
            style["moduleBackgroundColor"] = background_color
        return style

    return {}


def _format_log_entry(raw_entry: Dict, log_id: str) -> Dict:
    """转换为前端日志查看器使用的数据结构。"""
    module_name = str(raw_entry.get("logger_name", "") or raw_entry.get("module", ""))
    formatted_log = {
        "id": log_id,
        "timestamp": raw_entry.get("timestamp", ""),
        "level": str(raw_entry.get("level", "INFO")).upper(),
        "module": module_name,
        "message": raw_entry.get("event", ""),
    }
    formatted_log.update(_resolve_module_style(module_name))
    return formatted_log


def load_recent_logs(limit: int = 100) -> List[Dict]:
    """从日志文件中加载最近的日志

    Args:
        limit: 返回的最大日志条数

    Returns:
        日志列表
    """
    logs = []
    log_dir = Path("logs")

    if not log_dir.exists():
        return logs

    # 获取所有日志文件,按修改时间排序
    log_files = sorted(log_dir.glob("app_*.log.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)

    # 用于生成唯一 ID 的计数器
    log_counter = 0

    # 从最新的文件开始读取
    for log_file in log_files:
        if len(logs) >= limit:
            break

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                # 流式读取最后 limit 行，避免大日志文件 OOM（A24b P1-6）
                recent_lines = deque(f, maxlen=limit)
                # 从文件末尾开始读取
                for line in reversed(recent_lines):
                    if len(logs) >= limit:
                        break
                    try:
                        log_entry = json.loads(line.strip())
                        # 转换为前端期望的格式
                        # 使用时间戳 + 计数器生成唯一 ID
                        timestamp_id = (
                            log_entry.get("timestamp", "0").replace("-", "").replace(" ", "").replace(":", "")
                        )
                        formatted_log = _format_log_entry(log_entry, f"{timestamp_id}_{log_counter}")
                        logs.append(formatted_log)
                        log_counter += 1
                    except (json.JSONDecodeError, KeyError) as exc:
                        # P0-5: 日志行解析失败出声（debug 防刷屏，跳过脏行）（ZG-31）
                        logger.debug("logs_ws 行解析失败，跳过: %s", exc)
                        continue
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "读取日志文件失败", exception=e)
            logger.error(f"读取日志文件失败 {log_file}: {e}")
            continue

    # 反转列表，使其按时间顺序排列（旧到新）
    return list(reversed(logs))



async def broadcast_log(log_data: Dict):
    """广播日志到所有连接的 WebSocket 客户端

    Args:
        log_data: 日志数据字典
    """
    module_name = str(log_data.get("module", ""))
    enriched_log_data = dict(log_data)
    enriched_log_data.update(_resolve_module_style(module_name))
    await websocket_manager.broadcast_to_topic(
        domain="logs",
        topic="main",
        event="entry",
        data={"entry": enriched_log_data},
    )
