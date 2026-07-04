"""时间上下文构建器。

构建时间上下文：当前时间、星期、时段、农历、节气。
上下文构建耗时 <5ms。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from .lunar import get_lunar_info, get_solar_terms_near

logger = logging.getLogger(__name__)


@dataclass
class TimeContext:
    """时间上下文。"""

    current_time: str = ""
    weekday: str = ""
    time_period: str = ""
    time_period_label: str = ""
    lunar_description: str = ""
    solar_term_description: str = ""
    active_coefficient: float = 0.8

    def to_prompt_text(self) -> str:
        """生成注入提示词的时间上下文文本。"""
        parts = [f"当前时间：{self.current_time}（{self.weekday}）"]
        parts.append(f"时段：{self.time_period_label}")

        if self.lunar_description:
            parts.append(f"农历：{self.lunar_description}")
        if self.solar_term_description:
            parts.append(f"节气：{self.solar_term_description}")

        return "；".join(parts)


_WEEKDAY_NAMES = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

_TIME_PERIODS: list[tuple[int, int, str, str]] = [
    (5, 8, "morning", "早晨"),
    (8, 12, "forenoon", "上午"),
    (12, 14, "noon", "中午"),
    (14, 17, "afternoon", "下午"),
    (17, 19, "evening", "傍晚"),
    (19, 23, "night", "晚上"),
    (23, 24, "late_night", "深夜"),
    (0, 5, "late_night", "深夜"),
]


class TimeContextBuilder:
    """时间上下文构建器。"""

    def __init__(self) -> None:
        self._cache: Optional[tuple[date, TimeContext]] = None

    def build(
        self,
        target_datetime: datetime | None = None,
        morning_active: float = 0.5,
        afternoon_active: float = 0.8,
        evening_active: float = 0.8,
        night_active: float = 0.3,
    ) -> TimeContext:
        """构建时间上下文。

        Args:
            target_datetime: 目标时间，默认为当前时间。
            morning_active: 早晨活跃系数。
            afternoon_active: 下午活跃系数。
            evening_active: 傍晚活跃系数。
            night_active: 深夜活跃系数。

        Returns:
            TimeContext: 时间上下文。
        """
        start = time.perf_counter()

        if target_datetime is None:
            target_datetime = datetime.now()

        target_date = target_datetime.date()

        if self._cache is not None and self._cache[0] == target_date:
            return self._cache[1]

        current_time = target_datetime.strftime("%Y-%m-%d %H:%M:%S")
        weekday = _WEEKDAY_NAMES[target_datetime.weekday()]

        hour = target_datetime.hour
        time_period = "night"
        time_period_label = "晚上"
        active_coefficient = 0.5

        for start_h, end_h, period, label in _TIME_PERIODS:
            if start_h <= hour < end_h:
                time_period = period
                time_period_label = label
                break

        active_map = {
            "morning": morning_active,
            "forenoon": morning_active,
            "noon": afternoon_active,
            "afternoon": afternoon_active,
            "evening": evening_active,
            "night": night_active,
            "late_night": night_active,
        }
        active_coefficient = active_map.get(time_period, 0.5)

        lunar_desc = ""
        lunar_info = get_lunar_info(target_date)
        if lunar_info:
            parts = []
            if lunar_info.year_gan_zhi:
                parts.append(lunar_info.year_gan_zhi + "年")
            if lunar_info.lunar_month_name:
                leap = "闰" if lunar_info.is_leap_month else ""
                parts.append(leap + lunar_info.lunar_month_name)
            if lunar_info.lunar_day_name:
                parts.append(lunar_info.lunar_day_name)
            lunar_desc = "".join(parts)

        solar_term_desc = ""
        near_terms = get_solar_terms_near(target_date, days=3)
        if near_terms:
            term_labels = []
            for t in near_terms:
                if t.is_today:
                    term_labels.append(f"今天是{t.name}")
                else:
                    delta = (t.date - target_date).days
                    if delta > 0:
                        term_labels.append(f"{delta}天后是{t.name}")
                    elif delta < 0:
                        term_labels.append(f"{-delta}天前是{t.name}")
            solar_term_desc = "；".join(term_labels)

        ctx = TimeContext(
            current_time=current_time,
            weekday=weekday,
            time_period=time_period,
            time_period_label=time_period_label,
            lunar_description=lunar_desc,
            solar_term_description=solar_term_desc,
            active_coefficient=active_coefficient,
        )

        self._cache = (target_date, ctx)

        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms > 5:
            logger.warning("时间上下文构建耗时 %.1fms (目标<5ms)", elapsed_ms)

        return ctx