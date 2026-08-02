"""ZG-7 污染标记 — 污染标志枚举。

对标 Linux `taint_flags[20]` 表（panic.c:808-829）：
8 个污染标志（位 0~7），值 = 1 << 位号，每位配字符映射（c_true/c_false）与中文描述。
标志语义不可变（spec §2.2.1 规则 2）：已定义标志的位号与语义不可变更，新增只能追加更高位号。
"""

from enum import IntEnum

# 污染标志总数（spec §2.2.1 规则 1）
TAINT_FLAGS_COUNT = 8
# 全部标志掩码（位 0~7 全置）
TAINT_FLAGS_MAX = 0xFF


class TaintFlag(IntEnum):
    """污染标志枚举 — 值 = 1 << 位号，语义不可变。"""

    TAINT_PORT_BYPASS = 1  # 位 0
    TAINT_EXCEPTION_SWALLOWED = 2  # 位 1
    TAINT_CONFIG_OVERRIDE = 4  # 位 2
    TAINT_COMPAT_FALLBACK = 8  # 位 3
    TAINT_UNVOTED_MUTATION = 16  # 位 4
    TAINT_WARN = 32  # 位 5
    TAINT_MONKEY_PATCH = 64  # 位 6
    TAINT_TEST_MODE = 128  # 位 7

    @property
    def c_true(self) -> str:
        """置位输出字符。"""
        return _TAINT_CHAR_MAP[self][0]

    @property
    def c_false(self) -> str:
        """未置位输出字符。"""
        return _TAINT_CHAR_MAP[self][1]

    @property
    def description(self) -> str:
        """中文描述。"""
        return _TAINT_DESC_MAP[self]

    @property
    def bit_position(self) -> int:
        """位号（0~7）。"""
        return self.value.bit_length() - 1


# 字符映射表（spec §2.4.1 规则 3）：(c_true, c_false)，位 0 c_false="G" 其余空格
_TAINT_CHAR_MAP: dict[TaintFlag, tuple[str, str]] = {
    TaintFlag.TAINT_PORT_BYPASS: ("P", "G"),
    TaintFlag.TAINT_EXCEPTION_SWALLOWED: ("E", " "),
    TaintFlag.TAINT_CONFIG_OVERRIDE: ("C", " "),
    TaintFlag.TAINT_COMPAT_FALLBACK: ("F", " "),
    TaintFlag.TAINT_UNVOTED_MUTATION: ("U", " "),
    TaintFlag.TAINT_WARN: ("W", " "),
    TaintFlag.TAINT_MONKEY_PATCH: ("M", " "),
    TaintFlag.TAINT_TEST_MODE: ("T", " "),
}

# 中文描述映射（spec §2.2.1 规则 3）
_TAINT_DESC_MAP: dict[TaintFlag, str] = {
    TaintFlag.TAINT_PORT_BYPASS: "绕过 Port 直接导入核心组件",
    TaintFlag.TAINT_EXCEPTION_SWALLOWED: "异常吞没（except Exception: pass）",
    TaintFlag.TAINT_CONFIG_OVERRIDE: "配置热更新/临时覆盖",
    TaintFlag.TAINT_COMPAT_FALLBACK: "V1 兼容路径触发",
    TaintFlag.TAINT_UNVOTED_MUTATION: "绕过 Vote 的直接变更",
    TaintFlag.TAINT_WARN: "WARN 类告警累计",
    TaintFlag.TAINT_MONKEY_PATCH: "运行时热补丁/monkey patch",
    TaintFlag.TAINT_TEST_MODE: "测试模式运行",
}
