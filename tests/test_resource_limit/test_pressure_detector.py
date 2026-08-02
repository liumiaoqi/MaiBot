"""PressureDetector 单元测试 — 对应 tasks §4.3。"""


from unittest.mock import MagicMock


from src.core.resource_limit.pressure_detector import PressureDetector
from src.core.resource_limit.types import PressureLevel


class TestPressureWindow:
    """PressureWindow 基础功能。"""

    def test_window_accumulation(self):
        """窗口累计至 win_size 触发计算。"""
        pd = PressureDetector(win_size=10)
        # 累计 9 次未满
        for _ in range(9):
            result = pd.record_sample(1, 0)
            assert result is None
        # 第 10 次窗口满，触发计算
        result = pd.record_sample(1, 0)
        assert result is not None

    def test_window_not_full_no_event(self):
        """窗口未满不发布事件。"""
        pd = PressureDetector(win_size=100)
        result = pd.record_sample(1, 1)
        assert result is None


class TestPressureDetector:
    """PressureDetector 三重判定与滞回。"""

    def test_priority_override(self):
        """优先级 ≤3 强制 CRITICAL（窗口未满也触发）。"""
        pd = PressureDetector(win_size=1000)
        result = pd.record_sample(1, 1, scan_priority=2)
        assert result == PressureLevel.CRITICAL

    def test_ratio_low(self):
        """比率 < 60% → LOW。"""
        pd = PressureDetector(win_size=10)
        pd.window.set_state(0, 0, PressureLevel.LOW)
        # 10 次采样，8 成功 2 失败 → ratio=20% → LOW
        result = pd.record_sample(10, 8)
        assert result == PressureLevel.LOW or result is None  # 可能未变更

    def test_ratio_medium(self):
        """60% ≤ 比率 < 95% → MEDIUM。"""
        pd = PressureDetector(win_size=10)
        pd.window.set_state(0, 0, PressureLevel.LOW)
        # 10 次采样，3 成功 7 失败 → ratio=70% → MEDIUM
        result = pd.record_sample(10, 3)
        assert result == PressureLevel.MEDIUM

    def test_ratio_critical(self):
        """比率 ≥ 95% → CRITICAL。"""
        pd = PressureDetector(win_size=100)
        pd.window.set_state(0, 0, PressureLevel.LOW)
        # 100 次采样，2 成功 98 失败 → ratio=98% → CRITICAL
        result = pd.record_sample(100, 2)
        assert result == PressureLevel.CRITICAL

    def test_hysteresis_no_flicker(self):
        """滞回避免抖动：升级后比率波动不立即降级。"""
        pd = PressureDetector(win_size=10)
        pd.window.set_state(0, 0, PressureLevel.LOW)
        # 升级到 CRITICAL
        pd.record_sample(10, 0)  # ratio=100% → CRITICAL
        assert pd.current_level == PressureLevel.CRITICAL
        # 比率 90%（≥ 降级阈值 85%）→ 保持 CRITICAL，不降级
        result = pd.record_sample(10, 1)  # ratio=90%
        assert result is None  # 未变更
        assert pd.current_level == PressureLevel.CRITICAL

    def test_event_emit_on_change(self):
        """等级变更发布事件。"""
        mock_bus = MagicMock()
        pd = PressureDetector(event_bus=mock_bus, win_size=10)
        pd.window.set_state(0, 0, PressureLevel.LOW)
        pd.record_sample(10, 0)  # → CRITICAL
        assert mock_bus.emit_sync.called
        call_args = mock_bus.emit_sync.call_args
        assert "resource.pressure.critical" in call_args[0][0]

    def test_event_data_structure(self):
        """事件数据结构包含 level、timestamp、psi_summary。"""
        mock_bus = MagicMock()
        pd = PressureDetector(event_bus=mock_bus, win_size=10)
        pd.window.set_state(0, 0, PressureLevel.LOW)
        pd.record_sample(10, 0)
        call_args = mock_bus.emit_sync.call_args
        event_data = call_args[0][1]
        assert "level" in event_data
        assert "timestamp" in event_data
        assert "psi_summary" in event_data
        assert event_data["level"] in ("low", "medium", "critical")

    def test_psi_summary_optional(self):
        """psi_summary 为 None 时事件仍正常发布。"""
        mock_bus = MagicMock()
        pd = PressureDetector(event_bus=mock_bus, win_size=10)
        pd.window.set_state(0, 0, PressureLevel.LOW)
        pd.record_sample(10, 0)
        call_args = mock_bus.emit_sync.call_args
        event_data = call_args[0][1]
        # psi_summary 可能为 None（Windows 无 /proc/pressure）
        assert "psi_summary" in event_data

    def test_no_event_when_unchanged(self):
        """等级未变更不发布事件。"""
        mock_bus = MagicMock()
        pd = PressureDetector(event_bus=mock_bus, win_size=10)
        pd.window.set_state(0, 0, PressureLevel.LOW)
        # ratio=0% → LOW，与当前相同，不发布事件
        pd.record_sample(10, 10)
        assert not mock_bus.emit_sync.called

    def test_emit_failed_resilient(self):
        """事件总线异常不影响压力分级。"""
        mock_bus = MagicMock()
        mock_bus.emit_sync.side_effect = RuntimeError("bus error")
        pd = PressureDetector(event_bus=mock_bus, win_size=10)
        pd.window.set_state(0, 0, PressureLevel.LOW)
        # 不应抛异常
        result = pd.record_sample(10, 0)
        assert result == PressureLevel.CRITICAL