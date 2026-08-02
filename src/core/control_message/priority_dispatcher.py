"""ZG-8 控制消息优先级 — 优先级投递引擎。

对标 Linux `next_signal` 优先级算法 + `get_signal` 固定优先级链：
先私后共 → 同步优先 → 低编号优先 → 屏蔽过滤，单一决策点。

优先级链（spec §5.3.1 规则 1）：
系统级强制(1-3) → 引擎致命(4-6) → 会话控制(7-9) → 调试(10-11) → 普通(12-14) → 实时(15-16)
编号区间天然编码优先级（ADR-02），dequeue 的低编号优先自动按链出队。
"""

from typing import Optional

from src.core.control_message.kind_registry import ControlMessageKindRegistry
from src.core.control_message.mask_manager import ControlMessageMaskManager
from src.core.control_message.pending_queue import ControlMessagePending
from src.core.control_message.types import ControlMessagePendingNode


class PriorityDispatcher:
    """优先级投递引擎 — 两级 pending 出队决策点。"""

    def __init__(
        self,
        kind_registry: ControlMessageKindRegistry,
        mask_manager: ControlMessageMaskManager,
    ) -> None:
        self._kind_registry = kind_registry
        self._mask_manager = mask_manager

    def next_control_message(
        self,
        private_pending: ControlMessagePending,
        shared_pending: ControlMessagePending,
        session_id: str,
    ) -> Optional[ControlMessagePendingNode]:
        """优先级出队 — 先私后共（spec §5.8.1 规则 2/3）。

        Args:
            private_pending: 会话私有 pending 队列
            shared_pending: 系统共享 pending 队列
            session_id: 出队会话 ID

        Returns:
            最高优先级可投递控制消息节点；无可投递消息（空/全被屏蔽）时
            返回 None（放行用户消息，spec §5.3.1 规则 5）
        """
        effective_mask = self._mask_manager.get_effective_mask(session_id)
        blocked = effective_mask.blocked_bits
        ignored = effective_mask.ignored_bits

        # 先私后共：私有队列有可投递消息优先出队
        node = private_pending.dequeue(blocked, ignored)
        if node is not None:
            return node

        # 私有队列空或全被屏蔽，扫描系统共享队列
        return shared_pending.dequeue(blocked, ignored)
