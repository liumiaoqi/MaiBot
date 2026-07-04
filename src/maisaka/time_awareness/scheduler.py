"""定时触发调度器。

支持基于时间的主动触发（早晨问候、节气祝福等）。
检测并跳过重复触发，确保每个时间规则每个周期只执行一次。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.maisaka.agent.config import TimeTriggerRule

logger = logging.getLogger(__name__)


@dataclass
class TriggerEvent:
    """触发事件。"""

    trigger_type: str
    rule_index: int
    message_template: str
    timestamp: float = field(default_factory=time.time)


class TimeTriggerScheduler:
    """定时触发调度器。"""

    def __init__(self) -> None:
        self._fired: dict[str, float] = {}
        self._max_cache_age = 86400

    def check_triggers(
        self,
        rules: list[TimeTriggerRule],
        current_hour: int | None = None,
        current_minute: int | None = None,
    ) -> list[TriggerEvent]:
        """检查是否有应该触发的时间规则。

        Args:
            rules: 时间触发规则列表。
            current_hour: 当前小时（用于测试），默认为实际时间。
            current_minute: 当前分钟（用于测试），默认为实际时间。

        Returns:
            触发事件列表。
        """
        now = datetime.now()
        hour = current_hour if current_hour is not None else now.hour
        minute = current_minute if current_minute is not None else now.minute
        today_key = now.strftime("%Y-%m-%d")

        events: list[TriggerEvent] = []

        for i, rule in enumerate(rules):
            if not rule.enabled:
                continue

            cache_key = f"{today_key}:{rule.trigger_type}:{i}"
            if cache_key in self._fired:
                continue

            if not self._is_in_time_range(rule.time_range, hour, minute):
                continue

            self._fired[cache_key] = time.time()
            events.append(TriggerEvent(
                trigger_type=rule.trigger_type,
                rule_index=i,
                message_template=rule.message_template,
            ))

        self._cleanup_cache()
        return events

    def _is_in_time_range(self, time_range: str, hour: int, minute: int) -> bool:
        """检查当前时间是否在指定范围内。

        Args:
            time_range: 时间范围字符串，如 "07:00-09:00"。
            hour: 当前小时。
            minute: 当前分钟。

        Returns:
            是否在范围内。
        """
        if not time_range or "-" not in time_range:
            return False

        try:
            parts = time_range.split("-")
            if len(parts) != 2:
                return False

            start_parts = parts[0].strip().split(":")
            end_parts = parts[1].strip().split(":")

            start_h = int(start_parts[0])
            start_m = int(start_parts[1]) if len(start_parts) > 1 else 0
            end_h = int(end_parts[0])
            end_m = int(end_parts[1]) if len(end_parts) > 1 else 0

            current_minutes = hour * 60 + minute
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m

            if start_minutes <= end_minutes:
                return start_minutes <= current_minutes <= end_minutes
            else:
                return current_minutes >= start_minutes or current_minutes <= end_minutes

        except (ValueError, IndexError):
            logger.debug("时间范围解析失败: %s", time_range)
            return False

    def _cleanup_cache(self) -> None:
        """清理过期的触发缓存。"""
        cutoff = time.time() - self._max_cache_age
        expired = [k for k, v in self._fired.items() if v < cutoff]
        for k in expired:
            del self._fired[k]

    def reset(self) -> None:
        """重置所有触发记录。"""
        self._fired.clear()