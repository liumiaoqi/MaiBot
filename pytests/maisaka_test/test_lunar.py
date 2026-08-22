"""lunar 单元测试。

覆盖 _compute_gan_zhi 纯函数，以及 get_lunar_info /
get_today_solar_term / get_solar_terms_near 的降级与正常路径。
测试环境未安装 zhdate/lunarcalendar，降级路径返回 None/[]。
正常路径通过 mock 第三方库验证。
"""

from datetime import date
from unittest.mock import MagicMock, patch


from src.maisaka.time_awareness.lunar import (
    LunarInfo,
    SolarTermInfo,
    _compute_gan_zhi,
    get_lunar_info,
    get_solar_terms_near,
    get_today_solar_term,
)


class TestComputeGanZhi:
    """_compute_gan_zhi 纯函数测试。"""

    def test_1984_is_jia_zi(self):
        # 1984 年是甲子年
        assert _compute_gan_zhi(1984) == "甲子"

    def test_2024_is_jia_chen(self):
        # 2024 年是甲辰年
        assert _compute_gan_zhi(2024) == "甲辰"

    def test_2025_is_yi_si(self):
        # 2025 年是乙巳年
        assert _compute_gan_zhi(2025) == "乙巳"

    def test_cycle_period_60_years(self):
        # 干支周期 60 年
        base = _compute_gan_zhi(1984)
        assert _compute_gan_zhi(1984 + 60) == base
        assert _compute_gan_zhi(1984 + 120) == base


class TestGetLunarInfoDegraded:
    """get_lunar_info 降级路径测试（zhdate 未安装）。"""

    def test_returns_none_when_zhdate_unavailable(self):
        # 测试环境未安装 zhdate，应返回 None
        result = get_lunar_info(date(2024, 1, 1))
        assert result is None

    def test_default_date_today(self):
        # 不传日期默认用今天，同样降级返回 None
        result = get_lunar_info()
        assert result is None


class TestGetLunarInfoWithMock:
    """get_lunar_info 正常路径测试（mock zhdate）。"""

    def test_returns_lunar_info_when_zhdate_available(self):
        # 构造 mock zhdate 模块
        mock_zhdate = MagicMock()
        mock_instance = MagicMock()
        mock_instance.lunar_year = 2023
        mock_instance.lunar_month = 11
        mock_instance.lunar_day = 20
        mock_instance.leap_month = False
        mock_instance.to_datetime.return_value = date(2024, 1, 1)
        mock_zhdate.ZhDate.from_datetime.return_value = mock_instance

        with patch.dict("sys.modules", {"zhdate": mock_zhdate}):
            result = get_lunar_info(date(2024, 1, 1))

        assert result is not None
        assert result.lunar_year == 2023
        assert result.lunar_month == 11
        assert result.lunar_day == 20
        assert result.is_leap_month is False
        assert result.lunar_month_name == "冬月"
        assert result.lunar_day_name == "二十"
        assert result.year_gan_zhi == _compute_gan_zhi(2023)

    def test_lunar_month_name_for_leap_month(self):
        mock_zhdate = MagicMock()
        mock_instance = MagicMock()
        mock_instance.lunar_year = 2023
        mock_instance.lunar_month = 2
        mock_instance.lunar_day = 15
        mock_instance.leap_month = True
        mock_instance.to_datetime.return_value = date(2023, 3, 1)
        mock_zhdate.ZhDate.from_datetime.return_value = mock_instance

        with patch.dict("sys.modules", {"zhdate": mock_zhdate}):
            result = get_lunar_info(date(2023, 3, 1))

        assert result is not None
        assert result.is_leap_month is True
        assert result.lunar_month_name == "二月"


class TestGetTodaySolarTermDegraded:
    """get_today_solar_term 降级路径测试。"""

    def test_returns_none_when_zhdate_unavailable(self):
        result = get_today_solar_term(date(2024, 1, 1))
        assert result is None

    def test_default_date_today(self):
        result = get_today_solar_term()
        assert result is None


class TestGetSolarTermsNearDegraded:
    """get_solar_terms_near 降级路径测试。"""

    def test_returns_empty_when_lunarcalendar_unavailable(self):
        result = get_solar_terms_near(date(2024, 1, 1), days=7)
        assert result == []

    def test_default_date_today(self):
        result = get_solar_terms_near()
        assert result == []


class TestGetSolarTermsNearWithMock:
    """get_solar_terms_near 正常路径测试（mock lunarcalendar）。"""

    def test_returns_terms_when_solar_is_term(self):
        mock_lunarcalendar = MagicMock()
        mock_solar = MagicMock()
        mock_solar.isterm = True
        mock_solar.term = "立春"
        mock_lunarcalendar.Solar.fromdate.return_value = mock_solar

        with patch.dict("sys.modules", {"lunarcalendar": mock_lunarcalendar}):
            result = get_solar_terms_near(date(2024, 2, 4), days=0)

        # days=0 只检查当天
        assert len(result) == 1
        assert result[0].name == "立春"
        assert result[0].is_today is True

    def test_returns_empty_when_no_term_nearby(self):
        mock_lunarcalendar = MagicMock()
        mock_solar = MagicMock()
        mock_solar.isterm = False
        mock_lunarcalendar.Solar.fromdate.return_value = mock_solar

        with patch.dict("sys.modules", {"lunarcalendar": mock_lunarcalendar}):
            result = get_solar_terms_near(date(2024, 6, 15), days=3)

        assert result == []


class TestLunarInfoDataclass:
    """LunarInfo 数据类测试。"""

    def test_default_values(self):
        info = LunarInfo(lunar_year=2024, lunar_month=1, lunar_day=1)
        assert info.is_leap_month is False
        assert info.lunar_month_name == ""
        assert info.year_gan_zhi == ""


class TestSolarTermInfoDataclass:
    """SolarTermInfo 数据类测试。"""

    def test_default_values(self):
        info = SolarTermInfo(name="立春", date=date(2024, 2, 4))
        assert info.is_today is False