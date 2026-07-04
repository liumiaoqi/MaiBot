"""农历与节气计算模块。

使用 zhdate 库进行农历转换，计算失败时降级为公历日期。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

logger = logging.getLogger(__name__)


@dataclass
class LunarInfo:
    """农历信息。"""

    lunar_year: int
    lunar_month: int
    lunar_day: int
    is_leap_month: bool = False
    lunar_month_name: str = ""
    lunar_day_name: str = ""
    year_gan_zhi: str = ""
    month_gan_zhi: str = ""
    day_gan_zhi: str = ""


@dataclass
class SolarTermInfo:
    """节气信息。"""

    name: str
    date: date
    is_today: bool = False


_LUNAR_MONTH_NAMES = [
    "正月", "二月", "三月", "四月", "五月", "六月",
    "七月", "八月", "九月", "十月", "冬月", "腊月",
]

_LUNAR_DAY_NAMES = [
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
]

_TIANGAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
_DIZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

_24_SOLAR_TERMS = [
    "小寒", "大寒", "立春", "雨水", "惊蛰", "春分",
    "清明", "谷雨", "立夏", "小满", "芒种", "夏至",
    "小暑", "大暑", "立秋", "处暑", "白露", "秋分",
    "寒露", "霜降", "立冬", "小雪", "大雪", "冬至",
]


def _compute_gan_zhi(year: int) -> str:
    """计算年干支。"""
    gan_idx = (year - 4) % 10
    zhi_idx = (year - 4) % 12
    return _TIANGAN[gan_idx] + _DIZHI[zhi_idx]


def get_lunar_info(target_date: date | None = None) -> LunarInfo | None:
    """获取指定日期的农历信息。

    Args:
        target_date: 目标日期，默认为今天。

    Returns:
        LunarInfo 或 None（计算失败时）。
    """
    if target_date is None:
        target_date = date.today()

    try:
        from zhdate import ZhDate

        zh = ZhDate.from_datetime(datetime(target_date.year, target_date.month, target_date.day))
        solar = zh.to_datetime()

        lunar_month_name = ""
        lunar_day_name = ""
        if 1 <= zh.lunar_month <= 12:
            lunar_month_name = _LUNAR_MONTH_NAMES[zh.lunar_month - 1]
        if 1 <= zh.lunar_day <= 30:
            lunar_day_name = _LUNAR_DAY_NAMES[zh.lunar_day - 1]

        return LunarInfo(
            lunar_year=zh.lunar_year,
            lunar_month=zh.lunar_month,
            lunar_day=zh.lunar_day,
            is_leap_month=getattr(zh, "leap_month", False),
            lunar_month_name=lunar_month_name,
            lunar_day_name=lunar_day_name,
            year_gan_zhi=_compute_gan_zhi(zh.lunar_year),
        )
    except ImportError:
        logger.debug("zhdate 库未安装，农历计算不可用")
        return None
    except Exception as e:
        logger.warning("农历计算失败，降级为公历: %s", e)
        return None


def get_today_solar_term(target_date: date | None = None) -> SolarTermInfo | None:
    """获取指定日期是否为节气日。

    Args:
        target_date: 目标日期，默认为今天。

    Returns:
        SolarTermInfo 或 None（非节气日或计算失败时）。
    """
    if target_date is None:
        target_date = date.today()

    try:
        from zhdate import ZhDate

        year = target_date.year
        for i, term_name in enumerate(_24_SOLAR_TERMS):
            try:
                term_date = ZhDate(year, 1, 1).to_datetime().date()
                if i > 0:
                    pass

                from lunarcalendar import Solar

                term_solar = Solar.fromdate(target_date)
                if hasattr(term_solar, 'isterm') and term_solar.isterm:
                    return SolarTermInfo(
                        name=term_name,
                        date=target_date,
                        is_today=True,
                    )
            except Exception:
                continue

    except ImportError:
        pass
    except Exception as e:
        logger.debug("节气计算失败: %s", e)

    return None


def get_solar_terms_near(target_date: date | None = None, days: int = 7) -> list[SolarTermInfo]:
    """获取指定日期附近 days 天内的节气。

    Args:
        target_date: 目标日期，默认为今天。
        days: 前后天数范围。

    Returns:
        节气列表。
    """
    if target_date is None:
        target_date = date.today()

    results: list[SolarTermInfo] = []

    try:
        from lunarcalendar import Solar

        for delta in range(-days, days + 1):
            from datetime import timedelta

            check_date = target_date + timedelta(days=delta)
            try:
                solar = Solar.fromdate(check_date)
                if hasattr(solar, 'isterm') and solar.isterm:
                    term_name = getattr(solar, 'term', '')
                    if term_name:
                        results.append(SolarTermInfo(
                            name=term_name,
                            date=check_date,
                            is_today=delta == 0,
                        ))
            except Exception:
                continue

    except ImportError:
        logger.debug("lunarcalendar 库未安装，节气计算不可用")
    except Exception as e:
        logger.debug("节气范围计算失败: %s", e)

    return results