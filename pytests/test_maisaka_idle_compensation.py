from collections import deque
from types import SimpleNamespace

import pytest
import time

from src.maisaka import runtime as runtime_module
from src.maisaka.runtime import (
    IDLE_COMPENSATION_MIN_AVERAGE_INTERVAL_SECONDS,
    MaisakaHeartFlowChatting,
)


def _make_runtime() -> MaisakaHeartFlowChatting:
    """构造仅包含空窗补偿相关状态的轻量 runtime，绕过重量级初始化。"""
    runtime = object.__new__(MaisakaHeartFlowChatting)
    runtime._recent_external_message_intervals = deque()
    runtime._last_external_message_received_at = None
    runtime._last_message_received_at = 0.0
    runtime.log_prefix = "[test]"
    return runtime


def _external_message() -> SimpleNamespace:
    """构造一条来自普通用户的外部消息桩。"""
    return SimpleNamespace(
        platform="qq",
        message_info=SimpleNamespace(user_info=SimpleNamespace(user_id="user-1")),
    )


def _record_series(runtime: MaisakaHeartFlowChatting, offsets: list[float]) -> None:
    """以接近当前时间的时间戳依次喂入外部消息，避免被 30 分钟窗口裁剪。"""
    base = time.time()
    message = _external_message()
    for offset in offsets:
        runtime._record_external_message_interval(message, base + offset)


def test_burst_intervals_excluded_from_interval_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    """连发（短间隔）消息不应计入平均间隔统计。"""
    monkeypatch.setattr(runtime_module, "is_bot_self", lambda *_: False)
    runtime = _make_runtime()
    # 0s/2s/10s/12s 收到消息：2s、2s 属连发抖动应被忽略，仅 8s 间隔计入
    _record_series(runtime, [0.0, 2.0, 10.0, 12.0])
    recorded = [interval for _, interval in runtime._recent_external_message_intervals]
    assert len(recorded) == 1
    assert recorded == pytest.approx([8.0])


def test_average_interval_applies_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    """统计值低于下限时，平均间隔应被抬升到下限值。"""
    monkeypatch.setattr(runtime_module, "is_bot_self", lambda *_: False)
    runtime = _make_runtime()
    # 仅一个 8s 间隔，低于下限
    _record_series(runtime, [0.0, 8.0])
    assert runtime._get_recent_average_external_message_interval() == IDLE_COMPENSATION_MIN_AVERAGE_INTERVAL_SECONDS


def test_average_interval_preserves_large_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """统计值高于下限时，平均间隔应保持原值。"""
    monkeypatch.setattr(runtime_module, "is_bot_self", lambda *_: False)
    runtime = _make_runtime()
    # 两个 60s 间隔，均高于下限
    _record_series(runtime, [0.0, 60.0, 120.0])
    assert runtime._get_recent_average_external_message_interval() == pytest.approx(60.0)


def test_idle_compensation_blocks_without_pending_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有待处理消息时，纯空窗不应触发回复。"""
    monkeypatch.setattr(runtime_module, "is_bot_self", lambda *_: False)
    runtime = _make_runtime()
    _record_series(runtime, [0.0, 60.0, 120.0])
    runtime._last_external_message_received_at = time.time() - 100000.0
    assert runtime._should_trigger_message_turn_by_idle_compensation(pending_count=0, trigger_threshold=10) is False


def test_idle_compensation_caps_silence_contribution(monkeypatch: pytest.MonkeyPatch) -> None:
    """空窗折算量封顶，需配合真实待处理消息才可能触发。"""
    monkeypatch.setattr(runtime_module, "is_bot_self", lambda *_: False)
    runtime = _make_runtime()
    _record_series(runtime, [0.0, 60.0, 120.0])  # 平均间隔 60s

    # 空窗较短：折算量不足，单条待处理消息不触发
    runtime._last_external_message_received_at = time.time() - 60.0
    assert runtime._should_trigger_message_turn_by_idle_compensation(pending_count=1, trigger_threshold=10) is False

    # 空窗极久：折算量封顶到 threshold-1，与单条消息合计恰好达阈值才触发
    runtime._last_external_message_received_at = time.time() - 100000.0
    assert runtime._should_trigger_message_turn_by_idle_compensation(pending_count=1, trigger_threshold=10) is True
