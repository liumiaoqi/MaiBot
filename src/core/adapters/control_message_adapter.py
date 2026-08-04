"""ControlMessageAdapter — 实现 ControlMessagePort，组装 8 引擎。

适配器层，唯一允许导入控制消息引擎类的地方（spec §7.1 规则 2）。
核心通过 ControlMessagePort Protocol 接口交互，不直接导入本模块。
"""

import time
import uuid

from collections import deque
from typing import Any, Optional

from src.core.control_message.fatal_diffuser import FatalDiffuser
from src.core.control_message.force_channel import ForceChannel
from src.core.control_message.kind_registry import ControlMessageKindRegistry
from src.core.control_message.mask_manager import ControlMessageMaskManager
from src.core.control_message.priority_dispatcher import PriorityDispatcher
from src.core.control_message.two_level_pending import TwoLevelPendingManager
from src.core.control_message.types import (
    ControlMessage,
    ControlMessageDeliveryResult,
    ControlMessageEffectiveMask,
    ControlMessageKind,
    ControlMessagePendingView,
    DeliveryDecisionRecord,
    DeliveryResult,
    FatalDiffuseRecord,
    MaskOperation,
    MaskScope,
    UnkillableDeclaration,
)
from src.core.control_message.unkillable_guard import UnkillableGuard
from src.core.protocols import ControlMessagePort


# 决策历史环形缓冲上限（spec §9.2 配置项）
from src.common.logger import get_logger

logger = get_logger("control_message_adapter")

_DEFAULT_DELIVERY_HISTORY_LIMIT = 100

# 故障上报 reason（spec §7.3 衔接约束）
_FAULT_REASON = "control_message_error"


class ControlMessageAdapter(ControlMessagePort):
    """控制消息优先级适配器 — 组装 8 引擎，实现 ControlMessagePort。

    适配器层唯一入口，核心模块不导入控制消息具体类（spec §7.1 规则 1）。
    """

    def __init__(
        self,
        event_bus_port: Any = None,
        service_manager_port: Any = None,
        app_config_port: Any = None,
        watchdog_port: Any = None,
        session_lifecycle_port: Any = None,
    ):
        """初始化适配器并组装 8 引擎。

        Args:
            event_bus_port: AutonomyEventBusPort（发布 control.* 事件）
            service_manager_port: ServiceManagerPort（故障上报）
            app_config_port: AppConfigPort（屏蔽/白名单/队列上限配置）
            watchdog_port: WatchdogPort（超时订阅，T16 接线）
            session_lifecycle_port: SessionLifecyclePort（会话回调 + 关联任务查询）
        """
        self._event_bus = event_bus_port
        self._service_manager = service_manager_port
        self._app_config = app_config_port
        self._watchdog = watchdog_port
        self._session_lifecycle = session_lifecycle_port

        history_limit = _DEFAULT_DELIVERY_HISTORY_LIMIT
        if app_config_port is not None:
            try:
                history_limit = app_config_port.get_control_message_delivery_history_limit()
            except Exception:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("投递历史上限配置读取失败，使用默认 %s", _DEFAULT_DELIVERY_HISTORY_LIMIT, exc_info=True)

        # 1. 类别注册表
        self._kind_registry = ControlMessageKindRegistry(app_config_port)

        # 2. 屏蔽管理器
        self._mask_manager = ControlMessageMaskManager(
            kind_registry=self._kind_registry,
            app_config_port=app_config_port,
        )

        # 3. UNKILLABLE 保护
        self._unkillable_guard = UnkillableGuard(app_config_port)

        # 4. 优先级投递器
        self._priority_dispatcher = PriorityDispatcher(
            kind_registry=self._kind_registry,
            mask_manager=self._mask_manager,
        )

        # 5. 两级 pending 管理器
        self._pending_manager = TwoLevelPendingManager(
            kind_registry=self._kind_registry,
            priority_dispatcher=self._priority_dispatcher,
            mask_manager=self._mask_manager,
            app_config_port=app_config_port,
        )

        # 6. force 通道
        self._force_channel = ForceChannel(
            mask_manager=self._mask_manager,
            unkillable_guard=self._unkillable_guard,
            pending_manager=self._pending_manager,
            event_bus=event_bus_port,
            app_config_port=app_config_port,
        )

        # 7. 致命扩散
        self._fatal_diffuser = FatalDiffuser(
            session_lifecycle_port=session_lifecycle_port,
            event_bus=event_bus_port,
            app_config_port=app_config_port,
        )

        # 8. 投递决策历史
        self._delivery_history: deque[DeliveryDecisionRecord] = deque(
            maxlen=max(1, history_limit)
        )

    # ── 投递类（热路径）────────────────────────────────────────────

    async def send(
        self,
        kind: ControlMessageKind,
        payload: dict[str, Any],
        target_session_id: str = "",
        target_entity: str = "",
        source: str = "",
        trace_id: str = "",
    ) -> ControlMessageDeliveryResult:
        """投递控制消息（非 force，走完整优先级链）。

        流程：类别判定 → 忽略判定（丢弃）→ UNKILLABLE 保护 → 入队 →
        致命扩散 → 记录决策（屏蔽语义由出队时过滤，spec §5.3.1 规则 4）。
        """
        try:
            kind = ControlMessageKind(kind)
        except ValueError:
            raise ValueError(f"CONTROL_KIND_UNKNOWN: {kind}") from None

        now = time.monotonic()
        info = {
            "source": source,
            "payload": payload,
            "force": False,
            "timestamp": now,
            "trace_id": trace_id,
            "target_entity": target_entity,
        }

        # 1. 忽略判定：被忽略类别直接丢弃不入队（spec §5.4.1 规则 4）
        effective = self._mask_manager.get_effective_mask(target_session_id)
        if (1 << (kind - 1)) & effective.ignored_bits:
            await self._emit("control.ignored", {"kind": int(kind), "session": target_session_id})
            self._record_decision(kind, target_session_id, target_entity, now, "ignored", False, False,
                                  DeliveryResult.REJECTED_IGNORED)
            return ControlMessageDeliveryResult(
                delivered=False, result=DeliveryResult.REJECTED_IGNORED
            )

        # 2. UNKILLABLE 保护：致命 + 受保护实体 + 非 force → 拒绝淘汰（spec §5.6.1 规则 2）
        if target_entity:
            protection = self._unkillable_guard.check_protection(target_entity, kind, force=False)
            if protection.action.value == "rejected":
                await self._emit(
                    "control.unkillable_protected",
                    {"entity": target_entity, "kind": int(kind)},
                )
                self._record_decision(kind, target_session_id, target_entity, now, "not_blocked",
                                      False, False, DeliveryResult.REJECTED_UNKILLABLE)
                return ControlMessageDeliveryResult(
                    delivered=False,
                    result=DeliveryResult.REJECTED_UNKILLABLE,
                    detail=protection.reason,
                )

        # 3. 入队（定向入私有队列，全局入共享队列）
        if target_session_id:
            result = await self._pending_manager.send_to_session(target_session_id, kind, info)
        else:
            result = await self._pending_manager.send_to_system(kind, info)

        if not result.accepted:
            await self._emit("control.pending_overflow", {"kind": int(kind), "reason": result.reason})
            await self._report_fault(f"pending overflow: {result.reason}")
            self._record_decision(kind, target_session_id, target_entity, now, "not_blocked",
                                  False, False, DeliveryResult.REJECTED)
            return ControlMessageDeliveryResult(
                delivered=False, result=DeliveryResult.REJECTED, detail=result.reason
            )

        # 4. 致命扩散（SESSION_DESTROY，异步不阻塞）
        if self._kind_registry.is_fatal(kind):
            await self._fatal_diffuser.diffuse(target_session_id or "", kind)

        # 5. 记录决策（入队侧：QUEUED）
        self._record_decision(kind, target_session_id, target_entity, now, "not_blocked",
                              False, False, DeliveryResult.QUEUED)
        return ControlMessageDeliveryResult(delivered=False, result=DeliveryResult.QUEUED)

    async def force_send(
        self,
        kind: ControlMessageKind,
        target_session_id: str = "",
        target_entity: str = "",
        reason: str = "",
        caller: str = "",
    ) -> ControlMessageDeliveryResult:
        """force 强制投递 — 委托 ForceChannel（spec §5.7）。"""
        try:
            kind = ControlMessageKind(kind)
        except ValueError:
            raise ValueError(f"CONTROL_KIND_UNKNOWN: {kind}") from None
        result = await self._force_channel.force_send(
            kind, target_session_id, target_entity, reason, caller
        )
        # force 致命消息（4-6）也触发扩散（spec §5.9.1 规则 1 未豁免 force，CX 审核 P1-8）
        if result.delivered and self._kind_registry.is_fatal(kind):
            await self._fatal_diffuser.diffuse(target_session_id or "", kind)
        self._record_decision(
            kind, target_session_id, target_entity, time.monotonic(), "not_blocked",
            True, result.delivered and bool(target_entity),
            result.result,
        )
        return result

    def dequeue_next(self, session_id: str) -> Optional[ControlMessage]:
        """出队下一个控制消息（同步，热路径）。

        将内部 PendingNode 转换为 Protocol 接口定义的 ControlMessage
        （design §5.1）；无可投递消息返回 None（放行用户消息）。
        """
        node = self._pending_manager.dequeue_next_sync(session_id)
        if node is None:
            return None
        self._emit_sync(
            "control.delivered",
            {"kind": int(node.kind), "session": session_id},
        )
        return ControlMessage(
            kind=node.kind,
            source=node.info.get("source", ""),
            target_session_id=session_id,
            target_entity=node.info.get("target_entity", ""),
            payload=node.info.get("payload", {}),
            force=node.info.get("force", False),
            timestamp=node.info.get("timestamp", 0.0),
            trace_id=node.info.get("trace_id", ""),
        )

    # ── 屏蔽管理类 ─────────────────────────────────────────────────

    async def set_blocked(
        self,
        how: MaskOperation,
        kinds: set[ControlMessageKind],
        scope: MaskScope,
        session_id: str = "",
    ) -> set[ControlMessageKind]:
        bits = 0
        for k in kinds:
            bits |= 1 << (int(k) - 1)
        result_bits = self._mask_manager.set_blocked(how, bits, scope, session_id)
        return {ControlMessageKind(i + 1) for i in range(16) if result_bits & (1 << i)}

    async def set_ignored(
        self,
        kinds: set[ControlMessageKind],
        scope: MaskScope,
        session_id: str = "",
    ) -> set[ControlMessageKind]:
        bits = 0
        for k in kinds:
            bits |= 1 << (int(k) - 1)
        result_bits = self._mask_manager.set_ignored(bits, scope, session_id)
        return {ControlMessageKind(i + 1) for i in range(16) if result_bits & (1 << i)}

    def get_effective_mask(self, session_id: str) -> ControlMessageEffectiveMask:
        return self._mask_manager.get_effective_mask(session_id)

    # ── UNKILLABLE 管理类 ──────────────────────────────────────────

    async def declare_unkillable(
        self, entity_id: str, entity_type: str = "agent"
    ) -> None:
        self._unkillable_guard.declare_unkillable(entity_id, entity_type)

    async def clear_unkillable(self, entity_id: str) -> None:
        self._unkillable_guard.clear_unkillable(entity_id)

    def list_unkillable_entities(self) -> list[UnkillableDeclaration]:
        return self._unkillable_guard.list_unkillable_entities()

    # ── 会话生命周期类 ─────────────────────────────────────────────

    async def on_session_created(self, session_id: str) -> None:
        self._pending_manager.on_session_created(session_id)

    async def on_session_destroyed(self, session_id: str) -> None:
        self._pending_manager.on_session_destroyed(session_id)
        # 会话销毁触发致命扩散（T18：向关联异步任务扩散取消信号）
        await self._fatal_diffuser.diffuse(session_id, ControlMessageKind.SESSION_DESTROY)

    # ── 内省查询类（WebUI）─────────────────────────────────────────

    def get_pending_view(self, session_id: str = "") -> ControlMessagePendingView:
        view = self._pending_manager.get_pending_view(session_id)
        return ControlMessagePendingView(
            session_id=view[0],
            nodes=view[1],
            category_bitmap=view[2],
            total_count=view[3],
        )

    def get_delivery_history(self, limit: int = 100) -> list[DeliveryDecisionRecord]:
        return list(self._delivery_history)[-limit:]

    def get_diffuse_history(self, limit: int = 100) -> list[FatalDiffuseRecord]:
        return self._fatal_diffuser.get_diffuse_history(limit)

    # ── 内部工具 ───────────────────────────────────────────────────

    def _record_decision(
        self,
        kind: ControlMessageKind,
        target_session_id: str,
        target_entity: str,
        decision_time: float,
        blocked_status: str,
        force_used: bool,
        unkillable_cleared: bool,
        delivery_result: DeliveryResult,
    ) -> None:
        self._delivery_history.append(
            DeliveryDecisionRecord(
                decision_id=uuid.uuid7().hex,
                kind=kind,
                target_session_id=target_session_id,
                target_entity=target_entity,
                priority_level=self._kind_registry.get_category(kind).value,
                blocked_status=blocked_status,
                force_used=force_used,
                unkillable_cleared=unkillable_cleared,
                delivery_result=delivery_result,
                decision_time=decision_time,
            )
        )

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._event_bus is not None:
            try:
                await self._event_bus.emit(event_type, data)
            except Exception:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("control 事件发布失败: %s", event_type, exc_info=True)

    def _emit_sync(self, event_type: str, data: dict[str, Any]) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.emit_sync(event_type, data)
            except Exception:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("control 事件同步发布失败: %s", event_type, exc_info=True)

    async def _report_fault(self, detail: str) -> None:
        if self._service_manager is not None:
            try:
                await self._service_manager.report_external_fault(
                    "control_message", _FAULT_REASON, detail
                )
            except Exception:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("故障上报失败: %s", detail, exc_info=True)

    # ── 健康探针（T19 使用）────────────────────────────────────────

    async def health_probe(self) -> dict[str, Any]:
        """健康检查探针 — pending 队列不卡死、决策历史可用。"""
        return {
            "healthy": True,
            "shared_pending_count": self._pending_manager.get_pending_view("")[3],
        }

    # ── 系统状态联动（T17）────────────────────────────────────────

    async def apply_system_state(self, state_name: str) -> None:
        """ZG-6 状态迁移联动 — 通过系统级屏蔽集实现类别过滤（T17）。

        - DEGRADING：屏蔽调试追踪（10-11），降低非关键类别干扰
        - SHUTTING_DOWN：屏蔽调试/普通/实时（10-16），只留系统级强制 + 引擎致命
        - BOOTING/READY：不干预（保持配置默认）

        ZG-8 不维护系统状态，只订阅 ZG-6 状态变更（spec §7.6 规则 2）。
        """
        if "DEGRADING" in state_name:
            await self.set_blocked(MaskOperation.BLOCK, {10, 11}, MaskScope.SYSTEM)
        elif "SHUTTING_DOWN" in state_name:
            await self.set_blocked(
                MaskOperation.BLOCK, {10, 11, 12, 13, 14, 15, 16}, MaskScope.SYSTEM
            )
