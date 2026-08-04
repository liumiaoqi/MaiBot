"""ZG-7 T4/T7/T8/T9/T10 测试 — TaintedMask 核心 + 订阅广播 + 动作执行。"""

import asyncio

import pytest

from src.core.tainted_mask.taint_action import TaintAction
from src.core.tainted_mask.taint_flag import TaintFlag
from src.core.tainted_mask.tainted_mask import TaintedMask
from src.core.tainted_mask.types import TaintNotifyEvent


class _FakeStateMachine:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def trigger_health_level_change(self, level: str) -> None:
        self.calls.append(level)


def _make_mask(**kwargs: object) -> TaintedMask:
    return TaintedMask(time_func=lambda: 100.0, **kwargs)


class TestBasic:
    def test_get_taint_initial_zero(self) -> None:
        """初始位图为 0（spec §2.1.1 规则 4）。"""
        assert _make_mask().get_taint() == 0

    def test_get_taint_preset_mask(self) -> None:
        """预置掩码正确。"""
        assert _make_mask(preset_mask=0x20).get_taint() == 0x20

    def test_preset_mask_invalid(self) -> None:
        """preset_mask > 0xFF 校验拒绝。"""
        with pytest.raises(ValueError, match="preset_mask 超范围"):
            _make_mask(preset_mask=0x100)

    def test_add_taint_sets_bit(self) -> None:
        mask = _make_mask()
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert mask.get_taint() == 0x20

    def test_add_taint_irreversible(self) -> None:
        """置位后任何操作该位仍为 1（spec §2.1.1 规则 1）。"""
        mask = _make_mask()
        mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        mask.add_taint(TaintFlag.TAINT_WARN)
        mask.test_taint(TaintFlag.TAINT_PORT_BYPASS)
        assert mask.get_taint() & TaintFlag.TAINT_PORT_BYPASS.value != 0

    def test_add_taint_invalid_flag(self) -> None:
        """非法标志值抛 ValueError（spec §2.1.3 异常场景 1）。"""
        mask = _make_mask()
        with pytest.raises(ValueError, match="非法污染标志"):
            mask.add_taint("TAINT_WARN")  # type: ignore[arg-type]

    def test_no_clear_api(self) -> None:
        """无 clear/remove/reset 方法（spec §2.1.1 规则 5 禁止项）。"""
        mask = _make_mask()
        for name in ("clear_taint", "remove_taint", "reset_taint", "clear"):
            assert not hasattr(mask, name)

    def test_test_taint(self) -> None:
        mask = _make_mask()
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert mask.test_taint(TaintFlag.TAINT_WARN) is True
        assert mask.test_taint(TaintFlag.TAINT_TEST_MODE) is False


class TestIdempotent:
    def test_add_taint_idempotent(self) -> None:
        """重复 add_taint 不改变位图值（spec §2.1.1 规则 2）。"""
        mask = _make_mask()
        mask.add_taint(TaintFlag.TAINT_WARN)
        mask.add_taint(TaintFlag.TAINT_WARN)
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert mask.get_taint() == 0x20

    def test_idempotent_no_repeat_action(self) -> None:
        """幂等置位不重复触发 on_taint 动作与广播（spec §2.1.1 规则 2 修正版）。"""
        mask = _make_mask(on_taint={TaintFlag.TAINT_WARN: TaintAction.WARN})
        events: list[TaintNotifyEvent] = []
        mask.subscribe(lambda e: events.append(e))
        mask.add_taint(TaintFlag.TAINT_WARN)
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert len(events) == 1  # 广播只一次

    def test_first_ts_not_overwritten(self) -> None:
        """首次时间戳不覆盖（spec §2.1.1 规则 3）。"""
        mask = _make_mask()
        mask.add_taint(TaintFlag.TAINT_WARN)
        first_ts = mask.get_taint_records()[TaintFlag.TAINT_WARN.bit_position].first_ts
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert mask.get_taint_records()[TaintFlag.TAINT_WARN.bit_position].first_ts == first_ts

    def test_add_taint_records_stack(self) -> None:
        """首次调用栈记录。"""
        mask = _make_mask()
        mask.add_taint(TaintFlag.TAINT_WARN)
        record = mask.get_taint_records()[TaintFlag.TAINT_WARN.bit_position]
        assert "test_add_taint_records_stack" in record.first_stack
        assert len(record.first_stack) <= 500


class TestWarnCount:
    def test_warn_count_increment(self) -> None:
        """TAINT_WARN 置位时 warn_count 递增（spec §4.2 规则 2）。"""
        mask = _make_mask()
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert mask.warn_count == 1

    def test_warn_count_increments_on_idempotent(self) -> None:
        """幂等分支也递增（计数非动作，对标 atomic_inc_return）。"""
        mask = _make_mask()
        mask.add_taint(TaintFlag.TAINT_WARN)
        mask.add_taint(TaintFlag.TAINT_WARN)
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert mask.warn_count == 3

    def test_other_flags_do_not_increment(self) -> None:
        mask = _make_mask()
        mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        assert mask.warn_count == 0

    @pytest.mark.asyncio
    async def test_warn_limit_trigger(self) -> None:
        """warn_count >= warn_limit 触发降级。"""
        sm = _FakeStateMachine()
        mask = _make_mask(warn_limit=2, state_machine_port=sm)
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert sm.calls == []
        mask.add_taint(TaintFlag.TAINT_WARN)
        # 异步动作，等待事件循环调度
        for _ in range(50):
            if sm.calls:
                break
            await asyncio.sleep(0.01)
        assert sm.calls == ["fault"]

    def test_warn_limit_zero_disabled(self) -> None:
        """warn_limit=0 时不触发降级（边界）。"""
        sm = _FakeStateMachine()
        mask = _make_mask(warn_limit=0, state_machine_port=sm)
        for _ in range(10):
            mask.add_taint(TaintFlag.TAINT_WARN)
        assert sm.calls == []


class TestPrintTainted:
    def test_print_tainted_clean(self) -> None:
        """全干净输出 "Not tainted"（spec §2.4.1 规则 1）。"""
        assert _make_mask().print_tainted() == "Not tainted"

    def test_print_tainted_dirty(self) -> None:
        """有脏位输出 "Tainted: ..." 格式正确。"""
        mask = _make_mask()
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert mask.print_tainted() == "Tainted: G    W  "

    def test_print_tainted_exception_swallowed(self) -> None:
        mask = _make_mask()
        mask.add_taint(TaintFlag.TAINT_EXCEPTION_SWALLOWED)
        assert mask.print_tainted() == "Tainted: GE      "

    def test_print_tainted_all_set(self) -> None:
        """所有位置位时输出 8 个 c_true 字符。"""
        mask = _make_mask()
        for flag in TaintFlag:
            mask.add_taint(flag)
        assert mask.print_tainted() == "Tainted: PECFUWMT"

    def test_print_tainted_no_internal_detail(self) -> None:
        """不含数字位号/时间戳（spec §2.4.1 规则 5 禁止项）。"""
        mask = _make_mask()
        mask.add_taint(TaintFlag.TAINT_WARN)
        output = mask.print_tainted()
        assert "0x" not in output
        assert "." not in output

    def test_print_tainted_verbose(self) -> None:
        """verbose 仅列置位项（spec §2.4.1 规则 2）。"""
        mask = _make_mask()
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert mask.print_tainted_verbose() == ["W=TAINT_WARN"]

    def test_print_tainted_verbose_multiple(self) -> None:
        mask = _make_mask()
        mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert mask.print_tainted_verbose() == ["P=TAINT_PORT_BYPASS", "W=TAINT_WARN"]


class TestNotifier:
    def test_broadcast_on_first_taint(self) -> None:
        """首次置位广播 TaintNotifyEvent（spec §4.1 规则 1）。"""
        mask = _make_mask()
        events: list[TaintNotifyEvent] = []
        mask.subscribe(lambda e: events.append(e))
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert len(events) == 1
        assert events[0].flag is TaintFlag.TAINT_WARN
        assert events[0].current_mask == 0x20

    def test_no_broadcast_on_idempotent(self) -> None:
        """幂等置位不重复广播。"""
        mask = _make_mask()
        events: list[TaintNotifyEvent] = []
        mask.subscribe(lambda e: events.append(e))
        mask.add_taint(TaintFlag.TAINT_WARN)
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert len(events) == 1

    def test_nofail_on_subscriber_exception(self) -> None:
        """订阅者异常不阻断广播（nofail 语义）。"""
        mask = _make_mask()
        received: list[TaintNotifyEvent] = []

        def bad_handler(event: TaintNotifyEvent) -> None:
            raise RuntimeError("boom")

        def good_handler(event: TaintNotifyEvent) -> None:
            received.append(event)

        mask.subscribe(bad_handler)
        mask.subscribe(good_handler)
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert len(received) == 1

    def test_unsubscribe(self) -> None:
        mask = _make_mask()
        events: list[TaintNotifyEvent] = []
        handle = mask.subscribe(lambda e: events.append(e))
        mask.unsubscribe(handle)
        mask.add_taint(TaintFlag.TAINT_WARN)
        assert events == []


class TestActions:
    def test_warn_action_logs_warning(self) -> None:
        """WARN 动作输出 WARNING 级日志（spec §2.3.1 规则 3）。"""
        mask = _make_mask(on_taint={TaintFlag.TAINT_WARN: TaintAction.WARN})
        mask.add_taint(TaintFlag.TAINT_WARN)  # 不抛错即可（日志断言由 caplog 场景覆盖）

    @pytest.mark.asyncio
    async def test_trigger_degrade_calls_state_machine(self) -> None:
        """TRIGGER_DEGRADE 调用 trigger_health_level_change("fault")（spec §2.3.1 规则 4）。"""
        sm = _FakeStateMachine()
        mask = _make_mask(
            on_taint={TaintFlag.TAINT_PORT_BYPASS: TaintAction.TRIGGER_DEGRADE},
            state_machine_port=sm,
        )
        mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        for _ in range(50):
            if sm.calls:
                break
            await asyncio.sleep(0.01)
        assert sm.calls == ["fault"]

    @pytest.mark.asyncio
    async def test_trigger_degrade_failure_no_rollback(self) -> None:
        """动作失败不回滚污染位（spec §2.3.1 规则 5）。"""
        class BrokenStateMachine:
            async def trigger_health_level_change(self, level: str) -> None:
                raise RuntimeError("migration failed")

        mask = _make_mask(
            on_taint={TaintFlag.TAINT_PORT_BYPASS: TaintAction.TRIGGER_DEGRADE},
            state_machine_port=BrokenStateMachine(),
        )
        mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        await asyncio.sleep(0.05)  # 等待异步动作执行（含失败路径）
        # 污染位已置位（不可逆优先）
        assert mask.get_taint() & TaintFlag.TAINT_PORT_BYPASS.value != 0

    def test_trigger_degrade_fallback_when_no_port(self) -> None:
        """state_machine_port 为 None 时降级为 WARN（design §5.1）。"""
        mask = _make_mask(on_taint={TaintFlag.TAINT_PORT_BYPASS: TaintAction.TRIGGER_DEGRADE})
        mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)  # 不抛错，位已置位
        assert mask.get_taint() & TaintFlag.TAINT_PORT_BYPASS.value != 0

    def test_add_taint_no_event_loop(self) -> None:
        """无事件循环时异步操作跳过（fire-and-forget 降级，design §3.1.3）。"""
        sm = _FakeStateMachine()
        mask = _make_mask(
            on_taint={TaintFlag.TAINT_PORT_BYPASS: TaintAction.TRIGGER_DEGRADE},
            state_machine_port=sm,
        )
        # 无运行中事件循环的上下文
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)  # 跳过异步，位已置位
            assert mask.get_taint() & TaintFlag.TAINT_PORT_BYPASS.value != 0
        else:
            pytest.skip("存在事件循环，无法模拟无循环场景")


class TestDegradeOnTaintMask:
    """degrade_on_taint_mask 掩码级降级触发测试（ZG-7 P0 遗漏修复）。"""

    @pytest.mark.asyncio
    async def test_degrade_on_taint_mask_match_triggers_degrade(self) -> None:
        """掩码匹配触发 TRIGGER_DEGRADE。"""
        sm = _FakeStateMachine()
        mask = _make_mask(
            degrade_on_taint_mask=0x01,
            state_machine_port=sm,
        )
        mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        for _ in range(50):
            if sm.calls:
                break
            await asyncio.sleep(0.01)
        assert sm.calls == ["fault"]

    def test_degrade_on_taint_mask_no_match_uses_on_taint(self) -> None:
        """掩码不匹配走 on_taint 映射（WARN 动作真实执行）。"""
        from unittest.mock import patch

        sm = _FakeStateMachine()
        mask = _make_mask(
            on_taint={TaintFlag.TAINT_PORT_BYPASS: TaintAction.WARN},
            degrade_on_taint_mask=0x04,
            state_machine_port=sm,
        )
        with patch("src.core.tainted_mask.tainted_mask.logger") as mock_logger:
            mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        assert sm.calls == []
        # WARN 动作真实执行：额外 WARNING 日志
        assert mock_logger.warning.call_count == 1
        assert "WARN 动作" in mock_logger.warning.call_args[0][0]

    def test_degrade_on_taint_mask_default_zero_disabled(self) -> None:
        """默认值 0 禁用掩码级触发。"""
        sm = _FakeStateMachine()
        mask = _make_mask(state_machine_port=sm)
        mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        assert sm.calls == []

    @pytest.mark.asyncio
    async def test_degrade_on_taint_mask_priority_over_on_taint(self) -> None:
        """掩码优先于 on_taint（掩码匹配时跳过 on_taint WARN）。"""
        from unittest.mock import patch

        sm = _FakeStateMachine()
        mask = _make_mask(
            on_taint={TaintFlag.TAINT_PORT_BYPASS: TaintAction.WARN},
            degrade_on_taint_mask=0x01,
            state_machine_port=sm,
        )
        with patch("src.core.tainted_mask.tainted_mask.logger") as mock_logger:
            mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)
            for _ in range(50):
                if sm.calls:
                    break
                await asyncio.sleep(0.01)
        assert sm.calls == ["fault"]
        # WARN 被掩码级跳过：无 WARNING 日志
        assert mock_logger.warning.call_count == 0

    def test_degrade_on_taint_mask_no_override_non_matching(self) -> None:
        """掩码不覆盖非匹配标志的 on_taint 映射。"""
        sm = _FakeStateMachine()
        mask = _make_mask(
            on_taint={TaintFlag.TAINT_EXCEPTION_SWALLOWED: TaintAction.WARN},
            degrade_on_taint_mask=0x01,
            state_machine_port=sm,
        )
        mask.add_taint(TaintFlag.TAINT_EXCEPTION_SWALLOWED)
        assert sm.calls == []

    @pytest.mark.asyncio
    async def test_degrade_on_taint_mask_idempotent(self) -> None:
        """幂等性：重复置位同一标志不重复触发降级。"""
        sm = _FakeStateMachine()
        mask = _make_mask(
            degrade_on_taint_mask=0x01,
            state_machine_port=sm,
        )
        mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        for _ in range(50):
            if sm.calls:
                break
            await asyncio.sleep(0.01)
        assert sm.calls == ["fault"]

    def test_get_degrade_on_taint_mask_returns_value(self) -> None:
        """get_degrade_on_taint_mask 返回构造时传入的值。"""
        mask = _make_mask(degrade_on_taint_mask=0x03)
        assert mask.get_degrade_on_taint_mask() == 0x03

    def test_degrade_on_taint_mask_invalid_range(self) -> None:
        """超范围掩码抛 ValueError。"""
        with pytest.raises(ValueError, match="degrade_on_taint_mask 超范围"):
            _make_mask(degrade_on_taint_mask=0x100)

    def test_degrade_on_taint_mask_no_state_machine_port(self) -> None:
        """掩码级触发 + state_machine_port=None → 降级为 WARN + TAINT_ACTION_FAILED 日志。"""
        from unittest.mock import patch

        mask = _make_mask(degrade_on_taint_mask=0x01, state_machine_port=None)
        with patch("src.core.tainted_mask.tainted_mask.logger") as mock_logger:
            mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        assert mask.get_taint() & TaintFlag.TAINT_PORT_BYPASS.value != 0
        assert mock_logger.warning.call_count == 1
        assert "TAINT_ACTION_FAILED" in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_degrade_on_taint_mask_warn_limit_interaction(self) -> None:
        """掩码匹配时 warn_count 递增但不因 warn_limit 再次触发降级。"""
        sm = _FakeStateMachine()
        mask = _make_mask(
            degrade_on_taint_mask=0x20,
            warn_limit=1,
            state_machine_port=sm,
        )
        mask.add_taint(TaintFlag.TAINT_WARN)
        for _ in range(50):
            if sm.calls:
                break
            await asyncio.sleep(0.01)
        assert sm.calls == ["fault"]
        assert mask.warn_count == 1

    def test_taint_record_action_taken_reflects_mask(self) -> None:
        """掩码匹配时 TaintRecord.action_taken 为 TRIGGER_DEGRADE。"""
        mask = _make_mask(degrade_on_taint_mask=0x01)
        mask.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        record = mask.get_taint_records()[TaintFlag.TAINT_PORT_BYPASS.bit_position]
        assert record.action_taken == TaintAction.TRIGGER_DEGRADE
