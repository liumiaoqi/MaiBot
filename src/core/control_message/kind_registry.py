"""ZG-8 控制消息优先级 — 分类与编号引擎。

对标 Linux `include/uapi/asm-generic/signal.h` 信号编号 + `include/linux/signal.h` 分类掩码宏：
- 六大类别按编号区间映射
- 同步/异步掩码（SYNCHRONOUS_MASK）、不可屏蔽掩码（UNMASKABLE_MASK）、
  标准/实时分类掩码（STANDARD_MASK / REALTIME_MASK）均为 O(1) 位运算
- 不可屏蔽白名单默认 [1,2,3]，运行时不可修改（spec §5.5.1 规则 2）
"""


from src.core.control_message.types import (

    REALTIME_MASK,
    STANDARD_MASK,
    SYNCHRONOUS_MASK,
    UNMASKABLE_MASK,
    ControlMessageCategory,
    ControlMessageKind,
)

from src.common.logger import get_logger

logger = get_logger("kind_registry")

# 默认不可屏蔽白名单（系统级强制，编号 1-3）
_DEFAULT_UNMASKABLE_WHITELIST = frozenset(
    {
        ControlMessageKind.EMERGENCY_STOP,
        ControlMessageKind.FORCE_SHUTDOWN,
        ControlMessageKind.FORCE_OFFLINE,
    }
)


class ControlMessageKindRegistry:
    """控制消息分类与编号引擎。

    提供类别判定与掩码查询；不可屏蔽白名单从 AppConfigPort 读取，
    配置冲突（spec §5.1.2 异常场景 2）时拒绝该配置项、保持默认白名单。
    """

    def __init__(self, app_config_port: object = None) -> None:
        """初始化注册表。

        Args:
            app_config_port: AppConfigPort 实例（可选；None 时用默认白名单）。
                仅用于读取不可屏蔽白名单配置，运行时不可修改。
        """
        self._unmaskable_whitelist = _DEFAULT_UNMASKABLE_WHITELIST
        if app_config_port is not None:
            try:
                configured = app_config_port.get_control_message_unmaskable_whitelist()
                parsed = frozenset(ControlMessageKind(k) for k in configured)
            except Exception:
                logger.warning("不可屏蔽白名单配置读取失败，使用默认 {1,2,3}", exc_info=True)
                parsed = frozenset()
            # 配置必须恰好覆盖默认白名单，否则拒绝该配置项保持默认（spec §5.1.2）
            if parsed == _DEFAULT_UNMASKABLE_WHITELIST:
                self._unmaskable_whitelist = parsed

    def _require_known(self, kind: object) -> ControlMessageKind:
        """校验编号合法（1-16），越界抛 CONTROL_KIND_UNKNOWN（spec §5.1.2 异常场景 1）。"""
        try:
            return ControlMessageKind(kind)
        except ValueError:
            raise ValueError(f"CONTROL_KIND_UNKNOWN: {kind}") from None

    def get_category(self, kind: object) -> ControlMessageCategory:
        """编号 → 类别映射，O(1) 区间判定（spec §5.1.1 规则 1）。"""
        known = self._require_known(kind)
        if known <= 3:
            return ControlMessageCategory.SYSTEM_FORCE
        if known <= 6:
            return ControlMessageCategory.ENGINE_FATAL
        if known <= 9:
            return ControlMessageCategory.SESSION_CONTROL
        if known <= 11:
            return ControlMessageCategory.DEBUG_TRACE
        if known <= 14:
            return ControlMessageCategory.NORMAL
        return ControlMessageCategory.REALTIME

    def is_synchronous(self, kind: object) -> bool:
        """是否同步控制消息（引擎致命，编号 4-6，spec §5.1.1 规则 2）。"""
        known = self._require_known(kind)
        return (1 << (known - 1)) & SYNCHRONOUS_MASK != 0

    def is_unmaskable(self, kind: object) -> bool:
        """是否不可屏蔽（系统级强制，编号 1-3，spec §5.1.1 规则 4）。"""
        known = self._require_known(kind)
        return (1 << (known - 1)) & UNMASKABLE_MASK != 0

    def is_standard(self, kind: object) -> bool:
        """是否标准控制消息（同类去重，编号 1-14，spec §5.1.1 规则 3）。"""
        known = self._require_known(kind)
        return (1 << (known - 1)) & STANDARD_MASK != 0

    def is_realtime(self, kind: object) -> bool:
        """是否实时控制消息（同类排队，编号 15-16，spec §5.1.1 规则 3）。"""
        known = self._require_known(kind)
        return (1 << (known - 1)) & REALTIME_MASK != 0

    def is_fatal(self, kind: object) -> bool:
        """是否致命控制消息（触发扩散，固定为 SESSION_DESTROY=9，spec §5.9.1）。"""
        known = self._require_known(kind)
        return known == ControlMessageKind.SESSION_DESTROY

    @property
    def unmaskable_whitelist(self) -> frozenset[ControlMessageKind]:
        """不可屏蔽白名单（运行时不可修改）。"""
        return self._unmaskable_whitelist
