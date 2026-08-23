"""grayscale_log 纯函数单元测试。

覆盖 format_grayscale_log 的正常、边界与 None 输入。
"""

from src.maisaka.context.grayscale_log import format_grayscale_log


class TestFormatGrayscaleLog:
    """format_grayscale_log 行为测试。"""

    def test_basic_format(self):
        result = format_grayscale_log(
            count_result=10,
            token_est=500,
            usage_prompt=480,
            overflow_ratio=0.5,
        )
        assert "[条数=10" in result
        assert "token_est=500" in result
        assert "usage_prompt=480" in result
        assert "overflow_ratio=0.500" in result
        assert result.startswith("[") and result.endswith("]")

    def test_usage_prompt_none_renders_null(self):
        result = format_grayscale_log(
            count_result=0,
            token_est=0,
            usage_prompt=None,
            overflow_ratio=0.0,
        )
        assert "usage_prompt=null" in result

    def test_overflow_ratio_three_decimal_places(self):
        result = format_grayscale_log(
            count_result=1,
            token_est=3,
            usage_prompt=2,
            overflow_ratio=0.123456,
        )
        # 保留三位小数
        assert "overflow_ratio=0.123" in result

    def test_zero_values(self):
        result = format_grayscale_log(
            count_result=0,
            token_est=0,
            usage_prompt=0,
            overflow_ratio=0.0,
        )
        assert "条数=0" in result
        assert "token_est=0" in result
        assert "usage_prompt=0" in result

    def test_large_values(self):
        result = format_grayscale_log(
            count_result=100000,
            token_est=999999,
            usage_prompt=888888,
            overflow_ratio=1.0,
        )
        assert "条数=100000" in result
        assert "token_est=999999" in result
        assert "overflow_ratio=1.000" in result

    def test_field_order_preserved(self):
        result = format_grayscale_log(
            count_result=5,
            token_est=100,
            usage_prompt=90,
            overflow_ratio=0.2,
        )
        # 固定字段顺序：条数 → token_est → usage_prompt → overflow_ratio
        pos_count = result.index("条数=")
        pos_token = result.index("token_est=")
        pos_usage = result.index("usage_prompt=")
        pos_overflow = result.index("overflow_ratio=")
        assert pos_count < pos_token < pos_usage < pos_overflow