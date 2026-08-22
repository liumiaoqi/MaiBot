"""context_builder 单元测试。

覆盖 TimeContext.to_prompt_text 和 TimeContextBuilder.build 行为。
测试环境未安装 zhdate/lunarcalendar，农历/节气降级为空。
"""

from datetime import datetime


from src.maisaka.time_awareness.context_builder import (
    TimeContext,
    TimeContextBuilder,
)


class TestTimeContextPromptText:
    """TimeContext.to_prompt_text 行为测试。"""

    def test_basic_fields(self):
        ctx = TimeContext(
            current_time="2024-01-01 08:00:00",
            weekday="星期一",
            time_period_label="早晨",
        )
        text = ctx.to_prompt_text()
        assert "当前时间：2024-01-01 08:00:00（星期一）" in text
        assert "时段：早晨" in text

    def test_with_lunar_description(self):
        ctx = TimeContext(
            current_time="2024-01-01 08:00:00",
            weekday="星期一",
            time_period_label="早晨",
            lunar_description="癸卯年冬月二十",
        )
        text = ctx.to_prompt_text()
        assert "农历：癸卯年冬月二十" in text

    def test_with_solar_term_description(self):
        ctx = TimeContext(
            current_time="2024-02-04 08:00:00",
            weekday="星期日",
            time_period_label="早晨",
            solar_term_description="今天是立春",
        )
        text = ctx.to_prompt_text()
        assert "节气：今天是立春" in text

    def test_without_lunar_and_solar_term(self):
        ctx = TimeContext(
            current_time="2024-01-01 08:00:00",
            weekday="星期一",
            time_period_label="早晨",
        )
        text = ctx.to_prompt_text()
        assert "农历" not in text
        assert "节气" not in text

    def test_default_values(self):
        ctx = TimeContext()
        text = ctx.to_prompt_text()
        assert "当前时间：（）" in text
        assert "时段：" in text


class TestTimeContextBuilderBuild:
    """TimeContextBuilder.build 行为测试。"""

    def test_build_returns_time_context(self):
        builder = TimeContextBuilder()
        ctx = builder.build(target_datetime=datetime(2024, 1, 1, 8, 0, 0))
        assert isinstance(ctx, TimeContext)
        assert ctx.current_time == "2024-01-01 08:00:00"

    def test_weekday_mapping(self):
        builder = TimeContextBuilder()
        # 2024-01-01 是星期一
        ctx = builder.build(target_datetime=datetime(2024, 1, 1, 8, 0, 0))
        assert ctx.weekday == "星期一"

    def test_weekday_sunday(self):
        builder = TimeContextBuilder()
        # 2024-02-04 是星期日
        ctx = builder.build(target_datetime=datetime(2024, 2, 4, 8, 0, 0))
        assert ctx.weekday == "星期日"

    def test_time_period_morning(self):
        builder = TimeContextBuilder()
        ctx = builder.build(target_datetime=datetime(2024, 1, 1, 6, 0, 0))
        assert ctx.time_period == "morning"
        assert ctx.time_period_label == "早晨"

    def test_time_period_forenoon(self):
        builder = TimeContextBuilder()
        ctx = builder.build(target_datetime=datetime(2024, 1, 1, 10, 0, 0))
        assert ctx.time_period == "forenoon"
        assert ctx.time_period_label == "上午"

    def test_time_period_noon(self):
        builder = TimeContextBuilder()
        ctx = builder.build(target_datetime=datetime(2024, 1, 1, 13, 0, 0))
        assert ctx.time_period == "noon"
        assert ctx.time_period_label == "中午"

    def test_time_period_afternoon(self):
        builder = TimeContextBuilder()
        ctx = builder.build(target_datetime=datetime(2024, 1, 1, 15, 0, 0))
        assert ctx.time_period == "afternoon"
        assert ctx.time_period_label == "下午"

    def test_time_period_evening(self):
        builder = TimeContextBuilder()
        ctx = builder.build(target_datetime=datetime(2024, 1, 1, 18, 0, 0))
        assert ctx.time_period == "evening"
        assert ctx.time_period_label == "傍晚"

    def test_time_period_night(self):
        builder = TimeContextBuilder()
        ctx = builder.build(target_datetime=datetime(2024, 1, 1, 20, 0, 0))
        assert ctx.time_period == "night"
        assert ctx.time_period_label == "晚上"

    def test_time_period_late_night(self):
        builder = TimeContextBuilder()
        ctx = builder.build(target_datetime=datetime(2024, 1, 1, 23, 30, 0))
        assert ctx.time_period == "late_night"
        assert ctx.time_period_label == "深夜"

    def test_time_period_late_night_early_morning(self):
        builder = TimeContextBuilder()
        ctx = builder.build(target_datetime=datetime(2024, 1, 1, 2, 0, 0))
        assert ctx.time_period == "late_night"
        assert ctx.time_period_label == "深夜"

    def test_active_coefficient_morning(self):
        builder = TimeContextBuilder()
        ctx = builder.build(
            target_datetime=datetime(2024, 1, 1, 6, 0, 0),
            morning_active=0.9,
        )
        assert ctx.active_coefficient == 0.9

    def test_active_coefficient_afternoon(self):
        builder = TimeContextBuilder()
        ctx = builder.build(
            target_datetime=datetime(2024, 1, 1, 15, 0, 0),
            afternoon_active=1.2,
        )
        assert ctx.active_coefficient == 1.2

    def test_active_coefficient_evening(self):
        builder = TimeContextBuilder()
        ctx = builder.build(
            target_datetime=datetime(2024, 1, 1, 18, 0, 0),
            evening_active=1.5,
        )
        assert ctx.active_coefficient == 1.5

    def test_active_coefficient_night(self):
        builder = TimeContextBuilder()
        ctx = builder.build(
            target_datetime=datetime(2024, 1, 1, 20, 0, 0),
            night_active=0.2,
        )
        assert ctx.active_coefficient == 0.2

    def test_cache_returns_same_context_for_same_date(self):
        builder = TimeContextBuilder()
        ctx1 = builder.build(target_datetime=datetime(2024, 1, 1, 8, 0, 0))
        ctx2 = builder.build(target_datetime=datetime(2024, 1, 1, 10, 0, 0))
        # 同一天缓存命中，返回同一对象
        assert ctx1 is ctx2

    def test_cache_invalidates_on_different_date(self):
        builder = TimeContextBuilder()
        ctx1 = builder.build(target_datetime=datetime(2024, 1, 1, 8, 0, 0))
        ctx2 = builder.build(target_datetime=datetime(2024, 1, 2, 8, 0, 0))
        # 不同日期不命中缓存
        assert ctx1 is not ctx2
        assert ctx1.current_time != ctx2.current_time

    def test_default_datetime_when_none(self):
        builder = TimeContextBuilder()
        ctx = builder.build(target_datetime=None)
        assert isinstance(ctx, TimeContext)
        # 应包含当前时间
        assert ctx.current_time

    def test_lunar_description_empty_when_zhdate_unavailable(self):
        builder = TimeContextBuilder()
        ctx = builder.build(target_datetime=datetime(2024, 1, 1, 8, 0, 0))
        # zhdate 未安装，农历描述应为空
        assert ctx.lunar_description == ""

    def test_solar_term_description_empty_when_lunarcalendar_unavailable(self):
        builder = TimeContextBuilder()
        ctx = builder.build(target_datetime=datetime(2024, 1, 1, 8, 0, 0))
        # lunarcalendar 未安装，节气描述应为空
        assert ctx.solar_term_description == ""