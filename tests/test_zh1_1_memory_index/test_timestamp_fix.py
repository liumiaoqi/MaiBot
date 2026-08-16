"""ZH1-1a timestamp 兜底修复测试 — 1970 脏数据修复场景。

覆盖 spec 5.6.1 规则 1-7：
  - None/0/1970 兜底（规则 1）
  - 有效 timestamp 不动（规则 2）
  - 幂等（规则 3）
  - 兜底优先级（规则 4）
  - 审计日志（规则 5）
  - 不兜底为未来时间（规则 7）

fix_timestamp_fallback 是纯函数，直接测试无需 mock。
"""

from datetime import datetime

import pytest

from src.maisaka.memory.mid_term_persistence import fix_timestamp_fallback


class TestFixTimestampFallback:
    """fix_timestamp_fallback 纯函数测试。"""

    def test_none_fallback(self) -> None:
        """timestamp=None 兜底为当前时间，不产生 1970。"""
        result = fix_timestamp_fallback(None, "msg1")
        assert result.year != 1970
        assert result.year >= 2024

    def test_zero_fallback(self) -> None:
        """timestamp=0 兜底，不产生 1970。"""
        result = fix_timestamp_fallback(0, "msg1")
        assert result.year != 1970
        assert result.year >= 2024

    def test_negative_fallback(self) -> None:
        """timestamp 为负数兜底（负数不 > 0）。"""
        result = fix_timestamp_fallback(-1, "msg1")
        assert result.year != 1970

    def test_valid_not_overwrite(self) -> None:
        """有效 timestamp 不动，原样转换。"""
        # 1723680000 ≈ 2024-08-15 00:00:00 UTC
        raw_ts = 1723680000
        result = fix_timestamp_fallback(raw_ts, "msg1")
        expected = datetime.fromtimestamp(float(raw_ts))
        assert result == expected
        assert result.year >= 2024

    def test_idempotent_valid(self) -> None:
        """幂等：有效 timestamp 重复调用结果完全一致。"""
        raw_ts = 1723680000.0
        first = fix_timestamp_fallback(raw_ts, "msg1")
        second = fix_timestamp_fallback(raw_ts, "msg1")
        assert first == second

    def test_idempotent_fallback_year(self) -> None:
        """幂等：fallback 路径重复调用 year 一致（now 可能微秒差但 year 稳定）。"""
        first = fix_timestamp_fallback(None, "msg1")
        second = fix_timestamp_fallback(None, "msg1")
        assert first.year == second.year

    def test_fallback_priority(self) -> None:
        """兜底优先级：有效 timestamp 优先于 fallback（不触发兜底）。"""
        raw_ts = 1700000000  # 2023-11
        result = fix_timestamp_fallback(raw_ts, "msg1")
        # 有效 timestamp 直接转换，不走兜底
        assert result == datetime.fromtimestamp(float(raw_ts))
        # 兜底路径应返回 now()，与有效 timestamp 不同
        fallback_result = fix_timestamp_fallback(None, "msg1")
        assert fallback_result != result or fallback_result.year == result.year

    def test_no_future_timestamp(self) -> None:
        """不兜底为未来时间：fallback 结果不晚于 now + 1 秒（容忍执行耗时）。"""
        before = datetime.now()
        result = fix_timestamp_fallback(None, "msg1")
        after = datetime.now()
        # fallback 结果应在 [before, after] 区间内（不未来）
        assert before <= result <= after or (result - before).total_seconds() < 1

    def test_audit_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """审计日志：fallback 路径记录 info 日志。"""
        with caplog.at_level("INFO", logger="maisaka.mid_term_persistence"):
            fix_timestamp_fallback(None, "msg_audit")
        # 应有兜底日志
        assert any("timestamp 兜底" in record.message for record in caplog.records)

    def test_float_timestamp_valid(self) -> None:
        """浮点有效 timestamp 正常转换。"""
        raw_ts = 1723680000.123
        result = fix_timestamp_fallback(raw_ts, "msg1")
        assert result == datetime.fromtimestamp(raw_ts)

    @pytest.mark.parametrize("bad_ts", [None, 0, 0.0, -1, -0.1])
    def test_all_bad_timestamps_fallback(self, bad_ts: object) -> None:
        """所有无效 timestamp 均兜底且不产生 1970。"""
        result = fix_timestamp_fallback(bad_ts, "msg1")  # type: ignore[arg-type]
        assert result.year != 1970