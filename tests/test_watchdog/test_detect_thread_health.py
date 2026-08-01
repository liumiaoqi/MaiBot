"""S2 检测线程健康检查测试（ZG-3 补强，简化版 buddy 互检）。

检测线程每次 _detect_once 完毕后刷新自身 touch 时间戳；
主循环侧 check_detect_thread_health() 检查是否超时（3 × check_interval_s）。
仅输出 WARNING，不上报不恢复（FR-S2-03）。
"""


import time






def test_detect_thread_touch_refreshed(monitor):
    """tasks 5.3.1: _detect_once() 执行后检测线程 touch 时间戳被更新。"""
    monitor.touch()
    monitor._detect_once()
    assert monitor._detect_thread_touch_time > 0
    assert abs(time.monotonic() - monitor._detect_thread_touch_time) < 1.0


def test_detect_thread_health_ok(monitor, caplog):
    """tasks 5.3.2: 检测线程正常时不输出 WARNING。"""
    monitor.start()
    try:
        monitor.touch()
        monitor._detect_once()
        monitor.check_detect_thread_health()
        assert "检测线程疑似卡住" not in caplog.text
    finally:
        monitor.stop()


def test_detect_thread_health_stuck(monitor, caplog):
    """tasks 5.3.3: 检测线程 touch 超时后输出 WARNING。"""
    monitor.start()
    try:
        monitor._detect_thread_touch_time = time.monotonic() - 60.0  # 模拟卡住
        monitor.check_detect_thread_health()
        assert "检测线程疑似卡住" in caplog.text
    finally:
        monitor.stop()


def test_detect_thread_health_not_started(monitor, caplog):
    """tasks 5.3.4: 看门狗未启动时不触发告警（FR-S2-04）。"""
    monitor.check_detect_thread_health()  # 未 start，_detect_thread is None
    assert "检测线程疑似卡住" not in caplog.text


def test_detect_thread_health_timestamp_rollback(monitor, caplog):
    """tasks 5.3.5: touch 时间戳回跳时忽略本次检查。"""
    monitor.start()
    try:
        monitor._detect_thread_touch_time = time.monotonic() + 60.0  # 未来时间
        monitor.check_detect_thread_health()
        assert "时间戳回跳" in caplog.text
        assert "检测线程疑似卡住" not in caplog.text
    finally:
        monitor.stop()


def test_detect_thread_touch_in_status(monitor):
    """tasks 5.3.6: get_status() 含 detect_thread_touch_time。"""
    monitor.touch()
    monitor._detect_once()
    status = monitor.get_status()
    assert status.detect_thread_touch_time > 0
    assert abs(time.monotonic() - status.detect_thread_touch_time) < 1.0
