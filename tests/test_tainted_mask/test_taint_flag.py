"""ZG-7 T2 测试 — TaintFlag 8 位枚举。"""

from src.core.tainted_mask.taint_flag import TAINT_FLAGS_COUNT, TAINT_FLAGS_MAX, TaintFlag


class TestTaintFlag:
    def test_flag_count(self) -> None:
        """TaintFlag 含 8 个成员（spec §2.2.1 规则 1）。"""
        assert len(TaintFlag) == 8
        assert TAINT_FLAGS_COUNT == 8

    def test_flag_values(self) -> None:
        """值 = 1 << 位号（TAINT_PORT_BYPASS=1, ..., TAINT_TEST_MODE=128）。"""
        expected = {
            TaintFlag.TAINT_PORT_BYPASS: 1,
            TaintFlag.TAINT_EXCEPTION_SWALLOWED: 2,
            TaintFlag.TAINT_CONFIG_OVERRIDE: 4,
            TaintFlag.TAINT_COMPAT_FALLBACK: 8,
            TaintFlag.TAINT_UNVOTED_MUTATION: 16,
            TaintFlag.TAINT_WARN: 32,
            TaintFlag.TAINT_MONKEY_PATCH: 64,
            TaintFlag.TAINT_TEST_MODE: 128,
        }
        for flag, value in expected.items():
            assert flag.value == value
        assert TAINT_FLAGS_MAX == 0xFF

    def test_c_true_c_false(self) -> None:
        """字符映射与 spec §2.4.1 规则 3 一致。"""
        expected = {
            TaintFlag.TAINT_PORT_BYPASS: ("P", "G"),
            TaintFlag.TAINT_EXCEPTION_SWALLOWED: ("E", " "),
            TaintFlag.TAINT_CONFIG_OVERRIDE: ("C", " "),
            TaintFlag.TAINT_COMPAT_FALLBACK: ("F", " "),
            TaintFlag.TAINT_UNVOTED_MUTATION: ("U", " "),
            TaintFlag.TAINT_WARN: ("W", " "),
            TaintFlag.TAINT_MONKEY_PATCH: ("M", " "),
            TaintFlag.TAINT_TEST_MODE: ("T", " "),
        }
        for flag, (c_true, c_false) in expected.items():
            assert flag.c_true == c_true
            assert flag.c_false == c_false

    def test_bit_position(self) -> None:
        """位号 0~7。"""
        expected = {
            TaintFlag.TAINT_PORT_BYPASS: 0,
            TaintFlag.TAINT_EXCEPTION_SWALLOWED: 1,
            TaintFlag.TAINT_CONFIG_OVERRIDE: 2,
            TaintFlag.TAINT_COMPAT_FALLBACK: 3,
            TaintFlag.TAINT_UNVOTED_MUTATION: 4,
            TaintFlag.TAINT_WARN: 5,
            TaintFlag.TAINT_MONKEY_PATCH: 6,
            TaintFlag.TAINT_TEST_MODE: 7,
        }
        for flag, position in expected.items():
            assert flag.bit_position == position

    def test_description(self) -> None:
        """中文描述非空。"""
        for flag in TaintFlag:
            assert flag.description, f"{flag.name} 描述为空"

    def test_no_hardware_flags(self) -> None:
        """禁止硬件类标志（spec §2.2.1 规则 4）。"""
        names = {flag.name for flag in TaintFlag}
        for forbidden in ("TAINT_DIE", "TAINT_MACHINE_CHECK", "TAINT_CPU_OUT_OF_SPEC", "TAINT_BAD_PAGE"):
            assert forbidden not in names
