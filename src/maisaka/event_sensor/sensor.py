"""群事件解析与感知。

监听群事件（红包、戳一戳、入退群），解析事件类型并传递给对应智能体。
未知事件类型记录调试日志并跳过。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class GroupEventType(str, Enum):
    """群事件类型。"""

    RED_PACKET = "red_packet"
    POKE = "poke"
    MEMBER_JOIN = "member_join"
    MEMBER_LEAVE = "member_leave"
    MEMBER_KICK = "member_kick"
    ADMIN_SET = "admin_set"
    ADMIN_UNSET = "admin_unset"
    LUCKY_DRAW = "lucky_draw"
    UNKNOWN = "unknown"


@dataclass
class GroupEvent:
    """群事件。"""

    event_type: GroupEventType
    group_id: str
    user_id: str = ""
    target_user_id: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    @property
    def event_label(self) -> str:
        labels = {
            GroupEventType.RED_PACKET: "红包",
            GroupEventType.POKE: "戳一戳",
            GroupEventType.MEMBER_JOIN: "入群",
            GroupEventType.MEMBER_LEAVE: "退群",
            GroupEventType.MEMBER_KICK: "被踢",
            GroupEventType.ADMIN_SET: "设为管理",
            GroupEventType.ADMIN_UNSET: "取消管理",
            GroupEventType.LUCKY_DRAW: "抽奖",
            GroupEventType.UNKNOWN: "未知事件",
        }
        return labels.get(self.event_type, "未知事件")


class GroupEventSensor:
    """群事件传感器，解析原始事件数据。"""

    _EVENT_TYPE_MAP: dict[str, GroupEventType] = {
        "red_packet": GroupEventType.RED_PACKET,
        "hongbao": GroupEventType.RED_PACKET,
        "poke": GroupEventType.POKE,
        "nudge": GroupEventType.POKE,
        "member_join": GroupEventType.MEMBER_JOIN,
        "group_increase": GroupEventType.MEMBER_JOIN,
        "member_leave": GroupEventType.MEMBER_LEAVE,
        "group_decrease": GroupEventType.MEMBER_LEAVE,
        "member_kick": GroupEventType.MEMBER_KICK,
        "admin_set": GroupEventType.ADMIN_SET,
        "admin_unset": GroupEventType.ADMIN_UNSET,
        "lucky_draw": GroupEventType.LUCKY_DRAW,
    }

    def parse_event(self, raw_event: dict[str, Any]) -> GroupEvent | None:
        """解析原始事件数据。

        Args:
            raw_event: 原始事件数据。

        Returns:
            GroupEvent 或 None（解析失败时）。
        """
        event_type_str = raw_event.get("event_type", "")
        event_type = self._EVENT_TYPE_MAP.get(event_type_str)

        if event_type is None:
            event_type = self._guess_event_type(raw_event)
            if event_type == GroupEventType.UNKNOWN:
                logger.debug(
                    "未知群事件类型: %s, 数据: %s",
                    event_type_str,
                    str(raw_event)[:200],
                )
                return None

        group_id = str(raw_event.get("group_id", ""))
        if not group_id:
            logger.debug("群事件缺少group_id，跳过")
            return None

        import time

        return GroupEvent(
            event_type=event_type,
            group_id=group_id,
            user_id=str(raw_event.get("user_id", "")),
            target_user_id=str(raw_event.get("target_user_id", "")),
            raw_data=raw_event,
            timestamp=raw_event.get("timestamp", time.time()),
        )

    def _guess_event_type(self, raw_event: dict[str, Any]) -> GroupEventType:
        """尝试从原始数据猜测事件类型。"""
        data_str = str(raw_event).lower()

        if any(kw in data_str for kw in ["红包", "hongbao", "red_packet", "redbag"]):
            return GroupEventType.RED_PACKET
        if any(kw in data_str for kw in ["戳一戳", "poke", "nudge"]):
            return GroupEventType.POKE
        if any(kw in data_str for kw in ["入群", "join", "increase"]):
            return GroupEventType.MEMBER_JOIN
        if any(kw in data_str for kw in ["退群", "leave", "decrease"]):
            return GroupEventType.MEMBER_LEAVE

        return GroupEventType.UNKNOWN