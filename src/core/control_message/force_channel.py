"""ZG-8 控制消息优先级 — force 强制投递引擎。

对标 Linux `force_sig_info_to_task`：
- 绕过所有屏蔽/忽略/UNKILLABLE 保护，必须成功投递（spec §4.2 可靠性 2）
- 调用方白名单授权（系统核心层，spec §5.7.1 规则 2）
- 只投递系统级强制类别（编号 1-3，spec §5.7.1 规则 5）
- 清除屏蔽/忽略/UNKILLABLE + 直接入队 + 审计记录
"""

import time

from src.core.control_message.mask_manager import ControlMessageMaskManager
from src.core.control_message.two_level_pending import TwoLevelPendingManager
from src.core.control_message.types import (
    ControlMessageDeliveryResult,
    ControlMessageKind,
    DeliveryResult,
    UNMASKABLE_MASK,
)
from src.core.control_message.unkillable_guard import UnkillableGuard

# force 通道默认白名单（spec §5.7.1 规则 2：系统核心层）
_DEFAULT_FORCE_WHITELIST = frozenset({"watchdog", "service_manager", "system_state_machine"})


class ForceChannel:
    """force 强制投递引擎 — 权限 + 类别 + 清除保护 + 直接入队 + 审计。"""

    def __init__(
        self,
        mask_manager: ControlMessageMaskManager,
        unkillable_guard: UnkillableGuard,
        pending_manager: TwoLevelPendingManager,
        event_bus: object = None,
        app_config_port: object = None,
    ) -> None:
        """初始化 force 通道。

        Args:
            mask_manager: 屏蔽管理器（清除屏蔽/忽略位）
            unkillable_guard: UNKILLABLE 保护（清除标志）
            pending_manager: 两级 pending（直接入队）
            event_bus: AutonomyEventBusPort（发布 control.* 事件）
            app_config_port: AppConfigPort（force_caller_whitelist 配置，可选）
        """
        self._mask_manager = mask_manager
        self._unkillable_guard = unkillable_guard
        self._pending_manager = pending_manager
        self._event_bus = event_bus
        whitelist = _DEFAULT_FORCE_WHITELIST
        if app_config_port is not None:
            try:
                configured = app_config_port.get_control_message_force_caller_whitelist()
                whitelist = frozenset(configured) or whitelist
            except Exception:
                pass
        self._caller_whitelist = whitelist

    async def _emit(self, event_type: str, data: dict) -> None:
        if self._event_bus is not None:
            try:
                await self._event_bus.emit(event_type, data)
            except Exception:
                pass

    async def force_send(
        self,
        kind: ControlMessageKind,
        target_session_id: str = "",
        target_entity: str = "",
        reason: str = "",
        caller: str = "",
    ) -> ControlMessageDeliveryResult:
        """force 强制投递 — 绕过所有保护，必须成功投递。

        Args:
            kind: 控制消息类别（必须为系统级强制 1-3）
            target_session_id: 目标会话 ID
            target_entity: 目标实体标识
            reason: 强制投递原因（审计）
            caller: 调用方标识（白名单校验）

        Returns:
            投递结果（FORCE_DELIVERED / REJECTED）
        """
        # 1. 权限校验（系统核心层，spec §5.7.1 规则 2）
        if caller not in self._caller_whitelist:
            await self._emit(
                "control.force_denied",
                {"caller": caller, "kind": int(kind)},
            )
            return ControlMessageDeliveryResult(
                delivered=False,
                result=DeliveryResult.REJECTED,
                detail="CONTROL_FORCE_PERMISSION_DENIED",
            )

        # 2. 类别校验（系统级强制，编号 1-3，spec §5.7.1 规则 5）
        if not ((1 << (int(kind) - 1)) & UNMASKABLE_MASK):
            return ControlMessageDeliveryResult(
                delivered=False,
                result=DeliveryResult.REJECTED,
                detail="CONTROL_FORCE_KIND_INVALID",
            )

        # 3. 清除目标的屏蔽/忽略（该类别，spec §5.7.1 规则 1）
        self._mask_manager.clear_blocked_bit(kind, target_session_id)
        self._mask_manager.clear_ignored_bit(kind, target_session_id)

        # 4. 清除目标的 UNKILLABLE 标志（force 投递系统级强制时无论是否致命均清除，
        #    spec §5.6.1 规则 3）
        if target_entity and self._unkillable_guard.is_protected(target_entity):
            self._unkillable_guard.clear_unkillable(target_entity)
            await self._emit("control.unkillable_cleared", {"entity": target_entity})

        # 5. 直接入队 + 唤醒处理
        info = {
            "source": caller,
            "reason": reason,
            "force": True,
            "timestamp": time.monotonic(),
            "target_entity": target_entity,
        }
        await self._pending_manager.force_enqueue(kind, info, target_session_id)

        # 6. 审计记录 + 事件发布（spec §5.7.1 规则 4）
        await self._emit(
            "control.force_delivered",
            {
                "caller": caller,
                "target": target_entity or target_session_id,
                "kind": int(kind),
                "reason": reason,
            },
        )
        return ControlMessageDeliveryResult(
            delivered=True, result=DeliveryResult.FORCE_DELIVERED
        )
