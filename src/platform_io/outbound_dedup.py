"""出站消息幂等去重窗口（ZG-23a）。

基于 ``dict + heapq`` 模式（参考入站 ``dedupe.py``），在出站消息发送前
拦截同一 ``message_id`` 的短窗口内重复投递。

- ``dict`` 保存 message_id 到 DedupRecord 的映射
- ``heapq`` 维护按过期时间排序的小顶堆，懒清理过期条目

与入站 ``MessageDeduplicator`` 的区别：
1. 返回 ``DedupDecision``（携带命中记录），而非单纯 bool
2. 支持 ``force_send=True`` 豁免合法重发
3. fail-open 降级：异常时放行所有消息，不阻断发送
4. 提供 ``is_recently_sent`` 只读查询，供 reply 重试幂等检查使用
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import heapq
import time

from src.common.logger import get_logger
from src.core.tainted_mask.mark import mark_exception_swallowed

logger = get_logger("platform_io.outbound_dedup")


@dataclass
class DedupRecord:
    """出站去重窗口中的单条记录。"""

    message_id: str
    route_key: Any = None
    source_path: str = ""
    first_seen_at: float = 0.0
    expires_at: float = 0.0


@dataclass
class DedupDecision:
    """去重决策结果。

    Attributes:
        allow: True 表示放行发送，False 表示抑制（重复）。
        hit_record: 抑制时携带命中的缓存记录，放行时为 None。
    """

    allow: bool = True
    hit_record: Optional[DedupRecord] = None


class OutboundDedupWindow:
    """出站消息幂等去重窗口。

    在 ``PlatformIOManager.send_message`` 入口拦截同一 ``message_id`` 的
    短窗口内重复投递，防止超时重试、并发竞态等场景下的重复发送。

    Notes:
        - 非线程安全，依赖单事件循环串行调用
        - 常见路径 ``O(log n)``，集中清理最坏 ``O(k log n)``
        - fail-open：内部异常时放行所有消息，不阻断发送
    """

    def __init__(self, ttl_seconds: float = 3.0, max_entries: int = 5000) -> None:
        """初始化出站去重窗口。

        Args:
            ttl_seconds: 窗口时长（秒），取值范围 2-5，越界回退 3.0。
            max_entries: 缓存条目上限，取值范围 100-50000，越界回退 5000。
        """
        # 越界回退
        if ttl_seconds < 2.0 or ttl_seconds > 5.0:
            logger.warning(f"出站去重窗口时长越界: {ttl_seconds}，回退默认值 3.0")
            ttl_seconds = 3.0
        if max_entries < 100 or max_entries > 50000:
            logger.warning(f"出站去重窗口最大条目数越界: {max_entries}，回退默认值 5000")
            max_entries = 5000

        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._seen: Dict[str, float] = {}
        self._records: Dict[str, DedupRecord] = {}
        self._expire_heap: List[Tuple[float, str]] = []

    def check_and_record(
        self,
        message_id: str,
        route_key: Any = None,
        source_path: str = "",
        force_send: bool = False,
    ) -> DedupDecision:
        """检查 message_id 是否在窗口内已发送，并记录本次发送。

        Args:
            message_id: 出站消息唯一标识。
            route_key: 路由键，用于日志排障。
            source_path: 来源路径，用于日志排障。
            force_send: True 时豁免去重（合法重发），不写入缓存。

        Returns:
            DedupDecision: allow=True 放行，allow=False 抑制（携带 hit_record）。
        """
        try:
            # 合法重发豁免
            if force_send:
                return DedupDecision(allow=True)

            # message_id 为空跳过去重
            if not message_id:
                logger.warning("出站去重检查: message_id 为空，跳过去重放行")
                return DedupDecision(allow=True)

            now = time.monotonic()
            self._purge_expired(now)

            # 查询窗口命中
            expires_at = self._seen.get(message_id)
            if expires_at is not None and expires_at > now:
                # 命中：抑制
                hit = self._records.get(message_id)
                logger.warning(
                    f"出站消息去重抑制: message_id={message_id} "
                    f"source={source_path} 剩余窗口={expires_at - now:.3f}s"
                )
                return DedupDecision(allow=False, hit_record=hit)

            # 未命中：写入缓存
            if len(self._seen) >= self._max_entries:
                self._evict_earliest_live()

            new_expires = now + self._ttl_seconds
            self._seen[message_id] = new_expires
            record = DedupRecord(
                message_id=message_id,
                route_key=route_key,
                source_path=source_path,
                first_seen_at=now,
                expires_at=new_expires,
            )
            self._records[message_id] = record
            heapq.heappush(self._expire_heap, (new_expires, message_id))
            return DedupDecision(allow=True)

        except Exception as e:
            # fail-open 降级：异常时放行
            logger.error(f"出站去重窗口异常，降级放行: {e}")
            mark_exception_swallowed("outbound_dedup.check_and_record")
            return DedupDecision(allow=True)

    def is_recently_sent(self, message_id: str) -> bool:
        """只读查询 message_id 是否在窗口内已发送。

        供 reply 重试幂等检查使用，不修改缓存。

        Args:
            message_id: 出站消息唯一标识。

        Returns:
            bool: True 表示窗口内已发送，False 表示未发送或已过期。
        """
        try:
            if not message_id:
                return False

            now = time.monotonic()
            expires_at = self._seen.get(message_id)
            if expires_at is not None and expires_at > now:
                return True
            return False

        except Exception as e:
            # fail-open 降级：异常时返回 False（未发送），允许重试
            logger.error(f"出站去重窗口查询异常，降级返回 False: {e}")
            mark_exception_swallowed("outbound_dedup.is_recently_sent")
            return False

    def clear(self) -> None:
        """清空全部去重缓存。"""
        self._seen.clear()
        self._records.clear()
        self._expire_heap.clear()

    def _purge_expired(self, now: float) -> None:
        """从缓存中清理已过期的去重条目。"""
        while self._expire_heap and self._expire_heap[0][0] <= now:
            expires_at, message_id = heapq.heappop(self._expire_heap)
            current_expires_at = self._seen.get(message_id)
            if current_expires_at is None:
                continue
            if current_expires_at != expires_at:
                continue
            self._seen.pop(message_id, None)
            self._records.pop(message_id, None)

    def _evict_earliest_live(self) -> None:
        """达容量上限时淘汰最早过期的有效键。"""
        while self._expire_heap:
            expires_at, message_id = heapq.heappop(self._expire_heap)
            current_expires_at = self._seen.get(message_id)
            if current_expires_at is None:
                continue
            if current_expires_at != expires_at:
                continue
            self._seen.pop(message_id, None)
            self._records.pop(message_id, None)
            return