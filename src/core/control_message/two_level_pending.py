"""ZG-8 控制消息优先级 — 两级 pending 引擎。

对标 Linux 线程私有 pending + 进程共享 pending：
- 会话私有队列（_private_pending[session_id]，max_nodes=256）
- 系统共享队列（_shared_pending，max_nodes=1024）
- 出队先私后共（对标 dequeue_signal），共享队列 asyncio.Lock 串行化防竞争
- 会话销毁清理私有队列防内存泄漏
"""

import asyncio
from typing import Any, Optional

from src.common.logger import get_logger
from src.core.control_message.kind_registry import ControlMessageKindRegistry
from src.core.control_message.mask_manager import ControlMessageMaskManager
from src.core.control_message.pending_queue import ControlMessagePending
from src.core.control_message.priority_dispatcher import PriorityDispatcher
from src.core.control_message.types import (
    ControlMessageKind,
    ControlMessagePendingNode,
    EnqueueResult,
)

logger = get_logger("two_level_pending")

# 默认队列上限（spec §5.8.1 规则 5）
_DEFAULT_PRIVATE_LIMIT = 256
_DEFAULT_SHARED_LIMIT = 1024


class TwoLevelPendingManager:
    """两级 pending 引擎 — 私有 + 共享 + 先私后共。"""

    def __init__(
        self,
        kind_registry: ControlMessageKindRegistry,
        priority_dispatcher: PriorityDispatcher,
        mask_manager: ControlMessageMaskManager,
        app_config_port: object = None,
    ) -> None:
        """初始化两级 pending 管理器。

        Args:
            kind_registry: 分类引擎
            priority_dispatcher: 优先级投递器（先私后共决策）
            mask_manager: 屏蔽管理器（有效屏蔽集查询）
            app_config_port: AppConfigPort（队列上限配置，可选）
        """
        self._kind_registry = kind_registry
        self._priority_dispatcher = priority_dispatcher
        self._mask_manager = mask_manager
        private_limit = _DEFAULT_PRIVATE_LIMIT
        shared_limit = _DEFAULT_SHARED_LIMIT
        if app_config_port is not None:
            try:
                private_limit = app_config_port.get_control_message_private_queue_limit()
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, "私有队列上限配置读取失败，使用默认", exception=exc)
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("私有队列上限配置读取失败，使用默认 %s", _DEFAULT_PRIVATE_LIMIT, exc_info=True)
            try:
                shared_limit = app_config_port.get_control_message_shared_queue_limit()
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, "共享队列上限配置读取失败，使用默认", exception=exc)
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("共享队列上限配置读取失败，使用默认 %s", _DEFAULT_SHARED_LIMIT, exc_info=True)
        self._private_limit = max(1, private_limit)
        self._shared_limit = max(1, shared_limit)
        self._shared_pending = ControlMessagePending(
            kind_registry=kind_registry, max_nodes=self._shared_limit
        )
        self._private_pending: dict[str, ControlMessagePending] = {}
        self._shared_lock = asyncio.Lock()

    async def send_to_session(
        self, session_id: str, kind: ControlMessageKind, info: dict[str, Any]
    ) -> EnqueueResult:
        """定向控制消息入会话私有队列（spec §5.8.1 规则 1）。

        私有队列不存在时降级共享队列（spec §5.8.2 异常场景 1）。
        """
        private = self._private_pending.get(session_id)
        if private is None:
            return await self.send_to_system(kind, info)
        return private.enqueue(kind, info)

    async def send_to_system(
        self, kind: ControlMessageKind, info: dict[str, Any]
    ) -> EnqueueResult:
        """全局控制消息入系统共享队列（spec §5.8.1 规则 2）。"""
        return self._shared_pending.enqueue(kind, info)

    async def dequeue_next(self, session_id: str) -> Optional[ControlMessagePendingNode]:
        """先私后共出队（spec §5.8.1 规则 2）。

        共享锁全程持有（串行化所有会话出队，防共享队列重复出队，ADR-10）；
        dispatcher 为纯同步逻辑，锁内无 await 间隙。

        Returns:
            最高优先级控制消息节点，无可投递消息时返回 None
        """
        async with self._shared_lock:
            return self.dequeue_next_sync(session_id)

    def dequeue_next_sync(self, session_id: str) -> Optional[ControlMessagePendingNode]:
        """同步出队（热路径，事件循环内调用）。

        与 dequeue_next 等价（dispatcher 纯同步无 await 间隙，事件循环内天然原子）；
        用于 ControlMessagePort.dequeue_next（同步接口）的委托。
        """
        private = self._private_pending.get(session_id)
        return self._priority_dispatcher.next_control_message(
            private, self._shared_pending, session_id
        )

    async def force_enqueue(
        self,
        kind: ControlMessageKind,
        info: dict,
        session_id: str = "",
    ) -> None:
        """force 直接入队（对标 force_sig_info_to_task 直投）。

        绕过去重判定与队列上限（force 为 last resort，频率极低，spec §4.2 可靠性 2
        "必须成功入队"）；目标 = 会话私有队列（存在时）否则系统共享队列。
        """
        target = self._shared_pending
        if session_id:
            private = self._private_pending.get(session_id)
            if private is not None:
                target = private
        bit = 1 << (kind - 1)
        node = ControlMessagePendingNode(
            kind=kind,
            info=info,
            is_standard=self._kind_registry.is_standard(kind),
            is_realtime=self._kind_registry.is_realtime(kind),
            insert_order=0,
        )
        target.node_list.append(node)
        target.node_count += 1
        target.kind_bitmap |= bit

    def on_session_created(self, session_id: str) -> None:
        """会话创建：创建私有 pending 队列。"""
        if session_id and session_id not in self._private_pending:
            self._private_pending[session_id] = ControlMessagePending(
                kind_registry=self._kind_registry, max_nodes=self._private_limit
            )

    def on_session_destroyed(self, session_id: str) -> None:
        """会话销毁：清理私有 pending 队列（spec §5.8.1 规则 3，防内存泄漏）。"""
        self._private_pending.pop(session_id, None)
        self._mask_manager.drop_session_mask(session_id)

    def get_pending_view(self, session_id: str = "") -> tuple:
        """内省快照（适配器包装为 ControlMessagePendingView）。"""
        if session_id:
            pending = self._private_pending.get(session_id)
        else:
            pending = self._shared_pending
        if pending is None:
            return (session_id, (), 0, 0)
        return (
            session_id,
            tuple(pending.node_list),
            pending.kind_bitmap,
            pending.node_count,
        )
