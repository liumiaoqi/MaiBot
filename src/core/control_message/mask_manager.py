"""ZG-8 控制消息优先级 — 屏蔽机制引擎。

对标 Linux `sigprocmask` + `set_current_blocked`：
- 屏蔽（blocked）：消息留 pending 不投递，解除后按原顺序投递（屏蔽 ≠ 丢弃）
- 忽略（ignored）：消息直接丢弃不入队（忽略 = 永久丢弃，对标 SIG_IGN）
- 不可屏蔽强制剔除：操作时强制剔除编号 1-3（对标 sigdelsetmask(SIGKILL|SIGSTOP)）
- 两级屏蔽：系统级 ∪ 会话级
"""

import time
from dataclasses import dataclass, field


from src.core.control_message.types import (

    UNMASKABLE_MASK,
    ControlMessageEffectiveMask,
    ControlMessageKind,
    MaskOperation,
    MaskScope,
)


from src.common.logger import get_logger

logger = get_logger("core.control_message.mask_manager")


@dataclass
class _ControlMessageMask:
    """屏蔽集（可变内部结构）。"""

    scope: MaskScope
    session_id: str
    blocked_bits: int = 0
    ignored_bits: int = 0
    last_update_time: float = field(default_factory=time.monotonic)


class ControlMessageMaskManager:
    """屏蔽机制引擎 — 两级屏蔽集 + 三种操作 + 不可屏蔽强制剔除。"""

    def __init__(self, kind_registry: object = None, app_config_port: object = None) -> None:
        """初始化屏蔽管理器。

        Args:
            kind_registry: ControlMessageKindRegistry（保留参数，is_unmaskable 白名单查询）
            app_config_port: AppConfigPort（读取系统级屏蔽/忽略配置，可选）
        """
        self._kind_registry = kind_registry
        self._effective_unmaskable_mask: int = UNMASKABLE_MASK
        if kind_registry is not None and hasattr(kind_registry, "unmaskable_mask"):
            self._effective_unmaskable_mask = kind_registry.unmaskable_mask
        self._system_mask = _ControlMessageMask(scope=MaskScope.SYSTEM, session_id="")
        self._session_masks: dict[str, _ControlMessageMask] = {}
        if app_config_port is not None:
            try:
                blocked = app_config_port.get_control_message_system_blocked_kinds()
                self._system_mask.blocked_bits = self._kinds_to_bits(blocked)
            except Exception:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("系统级屏蔽集配置读取失败，使用默认空集", exc_info=True)
            try:
                ignored = app_config_port.get_control_message_system_ignored_kinds()
                self._system_mask.ignored_bits = self._kinds_to_bits(ignored)
            except Exception:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("系统级忽略集配置读取失败，使用默认空集", exc_info=True)
            self._system_mask.blocked_bits &= ~self._effective_unmaskable_mask
            self._system_mask.ignored_bits &= ~self._effective_unmaskable_mask

    @staticmethod
    def _kinds_to_bits(kinds: object) -> int:
        bits = 0
        for k in kinds or ():
            bits |= 1 << (int(k) - 1)
        return bits

    def _get_mask(self, scope: MaskScope, session_id: str) -> _ControlMessageMask:
        if scope is MaskScope.SYSTEM:
            return self._system_mask
        mask = self._session_masks.get(session_id)
        if mask is None:
            mask = _ControlMessageMask(scope=MaskScope.SESSION, session_id=session_id)
            self._session_masks[session_id] = mask
        return mask

    def set_blocked(
        self,
        how: MaskOperation,
        kinds_bits: int,
        scope: MaskScope,
        session_id: str = "",
    ) -> int:
        """屏蔽集操作（BLOCK 并集 / UNBLOCK 差集 / SETMASK 直接设置）。

        操作前后强制剔除不可屏蔽类别（编号 1-3，spec §5.4.1 规则 3/6）。

        Args:
            how: 操作类型
            kinds_bits: 涉及的类别位图
            scope: 作用域（SYSTEM / SESSION）
            session_id: 会话 ID（SESSION 作用域必填）

        Returns:
            操作后该作用域屏蔽位图
        """
        kinds_bits &= ~self._effective_unmaskable_mask
        mask = self._get_mask(scope, session_id)
        if how is MaskOperation.BLOCK:
            mask.blocked_bits |= kinds_bits
        elif how is MaskOperation.UNBLOCK:
            mask.blocked_bits &= ~kinds_bits
        elif how is MaskOperation.SETMASK:
            mask.blocked_bits = kinds_bits
        mask.blocked_bits &= ~self._effective_unmaskable_mask
        mask.last_update_time = time.monotonic()
        return mask.blocked_bits

    def set_ignored(
        self,
        kinds_bits: int,
        scope: MaskScope,
        session_id: str = "",
    ) -> int:
        """设置忽略集（覆盖式，忽略 = 永久丢弃）。

        强制剔除不可屏蔽类别（第二道防线拒绝忽略，spec §5.5.1 规则 2）。

        Args:
            kinds_bits: 涉及的类别位图
            scope: 作用域
            session_id: 会话 ID（SESSION 作用域必填）

        Returns:
            操作后该作用域忽略位图
        """
        kinds_bits &= ~self._effective_unmaskable_mask
        mask = self._get_mask(scope, session_id)
        mask.ignored_bits = kinds_bits
        mask.ignored_bits &= ~self._effective_unmaskable_mask
        mask.last_update_time = time.monotonic()
        return mask.ignored_bits

    def get_effective_mask(self, session_id: str) -> ControlMessageEffectiveMask:
        """计算会话有效屏蔽集 = 系统级 ∪ 会话级（spec §5.4.1 规则 5）。"""
        session = self._session_masks.get(session_id)
        if session is None:
            return ControlMessageEffectiveMask(
                blocked_bits=self._system_mask.blocked_bits,
                ignored_bits=self._system_mask.ignored_bits,
            )
        return ControlMessageEffectiveMask(
            blocked_bits=self._system_mask.blocked_bits | session.blocked_bits,
            ignored_bits=self._system_mask.ignored_bits | session.ignored_bits,
        )

    def clear_blocked_bit(self, kind: ControlMessageKind, session_id: str = "") -> None:
        """清除会话（或系统）屏蔽集中单类别位 — force 通道使用（spec §5.7.1 规则 1）。"""
        if session_id:
            mask = self._session_masks.get(session_id)
            if mask is not None:
                mask.blocked_bits &= ~(1 << (kind - 1))
                mask.last_update_time = time.monotonic()
        self._system_mask.blocked_bits &= ~(1 << (kind - 1))

    def clear_ignored_bit(self, kind: ControlMessageKind, session_id: str = "") -> None:
        """清除会话（或系统）忽略集中单类别位 — force 通道使用。"""
        if session_id:
            mask = self._session_masks.get(session_id)
            if mask is not None:
                mask.ignored_bits &= ~(1 << (kind - 1))
                mask.last_update_time = time.monotonic()
        self._system_mask.ignored_bits &= ~(1 << (kind - 1))

    def get_system_mask(self) -> ControlMessageEffectiveMask:
        """查询系统级屏蔽集（供状态联动/内省）。"""
        return ControlMessageEffectiveMask(
            blocked_bits=self._system_mask.blocked_bits,
            ignored_bits=self._system_mask.ignored_bits,
        )

    def drop_session_mask(self, session_id: str) -> None:
        """删除会话级屏蔽集（会话销毁清理）。"""
        self._session_masks.pop(session_id, None)
