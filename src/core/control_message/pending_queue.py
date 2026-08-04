"""ZG-8 控制消息优先级 — 双结构待处理队列引擎。

对标 Linux `sigpending`（`sigset_t signal` + `list_head list`）：
- 类别位图（int）：O(1) 存在性查询 / 去重判定
- 有序链表（deque）：保序 + payload 承载
- 标准消息同类去重（对标 legacy_queue），实时消息同类排队保留全部实例

位图约定：类别编号 kind 对应位 (1 << (kind - 1))。
"""

from collections import deque
from typing import Any, Optional

from src.common.logger import get_logger
from src.core.control_message.kind_registry import ControlMessageKindRegistry
from src.core.control_message.types import (
    SYNCHRONOUS_MASK,
    UNMASKABLE_MASK,
    ControlMessageKind,
    ControlMessagePendingNode,
    EnqueueResult,
)

logger = get_logger(__name__)


class ControlMessagePending:
    """双结构 pending 队列 — 类别位图 + 有序链表。

    Thread-safety：调用方（TwoLevelPendingManager）保证单队列访问串行化。
    """

    def __init__(
        self,
        kind_registry: ControlMessageKindRegistry,
        max_nodes: int = 256,
    ) -> None:
        """初始化 pending 队列。

        Args:
            kind_registry: 分类引擎（标准/实时/同步判定）
            max_nodes: 节点数上限（默认 256，防控制消息风暴）
        """
        self._registry = kind_registry
        self.max_nodes = max_nodes
        self.kind_bitmap: int = 0
        self.node_list: deque[ControlMessagePendingNode] = deque()
        self.node_count: int = 0
        self._insert_counter: int = 0

    def _next_insert_order(self) -> int:
        self._insert_counter += 1
        return self._insert_counter

    def enqueue(
        self, kind: ControlMessageKind, info: dict[str, Any]
    ) -> EnqueueResult:
        """控制消息入队 — 标准去重 / 实时排队（对标 __send_signal_locked + legacy_queue）。

        标准消息已 pending 时更新 payload 并移至链表尾（保留最新，spec §5.2.1 规则 4）；
        实时消息始终新增节点保留全部实例。

        Args:
            kind: 控制消息类别
            info: 控制消息详情（source/payload/timestamp/trace_id 等）

        Returns:
            EnqueueResult，达上限时 accepted=False（CONTROL_PENDING_OVERFLOW）
        """
        bit = 1 << (kind - 1)

        if self._registry.is_standard(kind) and self.kind_bitmap & bit:
            # 已 pending 的标准消息：去重更新不占新节点（CX P2-3——必须在溢出判断之前，
            # 否则队列满时先驱逐低优先级节点、去重分支又不占位 → 误删）
            for i, node in enumerate(self.node_list):
                if node.kind == kind:
                    node.info = info
                    node.insert_order = self._next_insert_order()
                    moved = self.node_list[i]
                    del self.node_list[i]
                    self.node_list.append(moved)
                    break
            return EnqueueResult(accepted=True, deduplicated=True)

        if self.node_count >= self.max_nodes:
            evict_target = self._find_eviction_target(kind)
            if evict_target is not None:
                self.node_list.remove(evict_target)
                self.node_count -= 1
                evict_bit = 1 << (evict_target.kind - 1)
                if not any(n.kind == evict_target.kind for n in self.node_list):
                    self.kind_bitmap &= ~evict_bit
                logger.info(
                    "priority_eviction: kind=%d 驱逐 kind=%d",
                    int(kind), int(evict_target.kind),
                )
            else:
                return EnqueueResult(accepted=False, reason="CONTROL_PENDING_OVERFLOW")

        if self._registry.is_standard(kind):
            self.kind_bitmap |= bit
            node = ControlMessagePendingNode(
                kind=kind,
                info=info,
                is_standard=True,
                is_realtime=False,
                insert_order=self._next_insert_order(),
            )
            self.node_list.append(node)
            self.node_count += 1
            return EnqueueResult(accepted=True)

        # 实时消息：始终新增节点（保留全部实例，spec §5.2.1 规则 3）
        self.kind_bitmap |= bit
        node = ControlMessagePendingNode(
            kind=kind,
            info=info,
            is_standard=False,
            is_realtime=True,
            insert_order=self._next_insert_order(),
        )
        self.node_list.append(node)
        self.node_count += 1
        return EnqueueResult(accepted=True)

    def _find_eviction_target(
        self, new_kind: ControlMessageKind
    ) -> Optional[ControlMessagePendingNode]:
        """优先级感知溢出驱逐：找到可驱逐的最低优先级节点（spec §5.2.1 规则 7）。

        驱逐条件：被驱逐节点编号 > 新消息编号；编号 1-3 不可驱逐。
        同编号时驱逐最早入队的（insert_order 最小），首次找到即为目标。
        """
        evictable_node = None
        evictable_kind_max = int(new_kind)

        for node in self.node_list:
            node_kind = int(node.kind)
            if node_kind <= 3:
                continue
            if node_kind > evictable_kind_max:
                evictable_kind_max = node_kind
                evictable_node = node

        return evictable_node

    def dequeue(
        self, blocked_mask: int, ignored_mask: int
    ) -> Optional[ControlMessagePendingNode]:
        """按优先级出队 — 同步优先 + 低编号优先 + 屏蔽/忽略过滤（对标 next_signal + dequeue_signal）。

        可投递位图 = pending & ~(blocked | ignored)；被屏蔽/忽略的消息留队列不出队。

        Args:
            blocked_mask: 屏蔽位图（被屏蔽类别不出队）
            ignored_mask: 忽略位图（被忽略类别不出队）

        Returns:
            最高优先级节点，无可投递消息时返回 None
        """
        if self.node_count == 0:
            return None

        deliverable = self.kind_bitmap & ~(blocked_mask | ignored_mask)
        if deliverable == 0:
            return None  # 全被屏蔽/忽略

        # 系统级强制（1-3）绝对优先，其次同步优先（4-6，spec §5.3.1 规则 2：
        # "同步优先仅在系统级强制已出队后生效"）
        force_deliverable = deliverable & UNMASKABLE_MASK
        if force_deliverable:
            deliverable = force_deliverable
        else:
            sync_deliverable = deliverable & SYNCHRONOUS_MASK
            if sync_deliverable:
                deliverable = sync_deliverable

        # 低编号优先：取最低设置位（对标 ffz(~x)，spec §5.3.1 规则 3）
        lowest_bit = deliverable & (-deliverable)
        target_kind = ControlMessageKind(lowest_bit.bit_length())

        # 从链表取该类别最早入队的节点
        for i, node in enumerate(self.node_list):
            if node.kind == target_kind:
                del self.node_list[i]
                self.node_count -= 1
                # 位图与链表一致性：该类别无剩余节点时清位
                if not any(n.kind == target_kind for n in self.node_list):
                    self.kind_bitmap &= ~(1 << (target_kind - 1))
                return node

        return None  # 位图有但链表无（一致性异常，降级处理）

    def has_pending(self, kind: ControlMessageKind) -> bool:
        """O(1) 位图查询某类别是否 pending（spec §5.2.1 规则 1）。"""
        return (self.kind_bitmap & (1 << (kind - 1))) != 0

    def is_full(self) -> bool:
        """队列是否达节点上限。"""
        return self.node_count >= self.max_nodes
