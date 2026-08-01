"""S1 延迟报告机制测试（ZG-3 补强，对标 Linux SOFTLOCKUP_DELAY_REPORT）。

周期号方案：touch(delay=True) 设置 _delay_report_until = _check_period_no + 1，
仅对下一个检测周期生效，连续 delay 不会永久屏蔽（design 2.4.1）。
"""


import time


from src.core.watchdog.event_loop_monitor import EventLoopMonitor
from src.core.watchdog.types import BlockSeverity




def _simulate_severe_block(monitor: EventLoopMonitor) -> None:
    """模拟事件循环被阻塞：touch 时间戳设为过去（超过严重阈值）。"""
    monitor._last_touch_time = time.monotonic() - 10.0


def test_touch_delay_sets_flag(monitor):
    """tasks 5.2.1: touch(delay=True) 设置 _delay_report_until = 周期号 + 1。"""
    monitor._check_period_no = 5
    monitor.touch(delay=True)
    assert monitor._delay_report_until == 6


def test_touch_no_delay_no_flag(monitor):
    """tasks 5.2.2: touch(delay=False) 不修改延迟标志。"""
    monitor._check_period_no = 5
    monitor._delay_report_until = 0
    monitor.touch(delay=False)
    assert monitor._delay_report_until == 0


def test_delay_report_skips_report(monitor, reported):
    """tasks 5.2.3: 延迟标志生效时，严重阻塞不触发上报。"""
    # 周期 1：严重阻塞，连续计数 1（未达阈值 2，不上报）
    _simulate_severe_block(monitor)
    monitor._detect_once()
    assert monitor._consecutive_severe_count == 1
    assert reported == []

    # 慢路径标记延迟报告（_check_period_no=1 → until=2）
    monitor.touch(delay=True)

    # 周期 2：延迟报告生效，跳过上报（计数保持 2）
    _simulate_severe_block(monitor)
    monitor._detect_once()
    assert monitor._consecutive_severe_count == 2
    assert reported == []  # 跳过上报


def test_delay_report_auto_clear(monitor, reported):
    """tasks 5.2.4: 延迟标志仅生效 1 个周期后自动清除。"""
    _simulate_severe_block(monitor)
    monitor._detect_once()  # 周期 1，count=1
    monitor.touch(delay=True)  # until=2
    _simulate_severe_block(monitor)
    monitor._detect_once()  # 周期 2：delay 生效，跳过
    assert monitor._delay_report_until == 0  # 已清除
    assert reported == []

    # 周期 3：无 delay，计数 3 ≥ 2 → 上报
    _simulate_severe_block(monitor)
    monitor._detect_once()
    assert len(reported) == 1


def test_consecutive_delay_no_permanent_block(monitor, reported):
    """tasks 5.2.5: 连续 delay 每周期跳过，任一周期不 delay 则正常判定。"""
    # 每轮：先标记 delay（覆盖下一周期），再检测（该周期跳过上报）
    for _ in range(3):
        monitor.touch(delay=True)  # until = 当前周期号 + 1
        _simulate_severe_block(monitor)
        monitor._detect_once()  # delay 生效，跳过上报，计数累积
    assert reported == []  # 3 轮 delay 全部跳过

    # 无 delay 周期：正常判定 → 计数已达阈值 → 上报
    _simulate_severe_block(monitor)
    monitor._detect_once()
    assert len(reported) == 1


def test_delay_does_not_affect_mild_lag(monitor, reported):
    """tasks 5.2.6: delay 标志对轻度卡顿判定无影响。"""
    monitor.touch(delay=True)  # until = 0 + 1 = 1
    monitor._last_touch_time = time.monotonic() - 0.4  # mild(0.3) ≤ 0.4 < severe(0.5)
    monitor._detect_once()  # 周期 1：consume 生效 + mild 判定照常
    assert monitor._block_severity == BlockSeverity.MILD_LAG
    assert monitor._total_mild_lag_count == 1
    assert reported == []


def test_touch_backward_compatible(monitor):
    """tasks 5.2.1 兼容: touch() 无参数行为与补强前一致。"""
    monitor._delay_report_until = 0
    old_touch = monitor._last_touch_time
    monitor.touch()  # 无参数
    assert monitor._last_touch_time >= old_touch
    assert monitor._delay_report_until == 0  # 不设置标志
