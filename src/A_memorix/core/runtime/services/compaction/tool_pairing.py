"""ZG-N5 压缩升级——tool-pairing 边界平衡检查器。

对标 dsh compaction/src/tool-pairing.ts。
增量 balance state（inProgressToolCalls 计数），按 surface generation 缓存。
surface 重写后缓存失效重建。
"""

from typing import Any, Sequence

from .types import CorruptSurfaceError


class _BalanceCache:
    """增量 balance state for one session surface generation。"""

    def __init__(self, generation: int) -> None:
        self.generation = generation
        self.cut_balanced: list[bool] = [True]
        self.index_by_seq: dict[int, int] = {}
        self.in_progress_tool_calls: int = 0


def _event_delta(event: Any) -> int:
    """计算单个事件对 in-progress tool-call 计数的变化。

    对标 dsh tool-pairing.ts:29 eventDelta。
    assistant/message 的 tool-call block +1，tool/result -1，其他 0。
    """
    event_type = getattr(event, "type", None)
    if event_type == "assistant/message":
        data = getattr(event, "data", None)
        if data is None:
            return 0
        message = getattr(data, "message", None)
        if message is None:
            return 0
        content = getattr(message, "content", [])
        count = 0
        for block in content:
            block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if block_type == "tool-call":
                count += 1
        return count
    if event_type == "tool/result":
        return -1
    return 0


def _event_for_seq(events: Sequence[Any], seq: int) -> Any:
    """读取并校验 surface seq 对应的事件。"""
    if seq < 0 or seq >= len(events):
        raise CorruptSurfaceError(f"surface seq {seq} 超出事件范围（corrupt surface）")
    event = events[seq]
    event_seq = getattr(event, "seq", None)
    if event_seq is not None and event_seq != seq:
        raise CorruptSurfaceError(f"surface seq {seq} 无匹配事件（corrupt surface）")
    return event


class ToolPairingBalancer:
    """tool-pairing 边界平衡检查器——增量 balance state + 缓存。"""

    def __init__(self) -> None:
        self._cache_by_session: dict[str, _BalanceCache] = {}

    def _balance_cache(
        self,
        session_id: str,
        surface_nodes: Sequence[int],
        generation: int,
        events: Sequence[Any],
    ) -> _BalanceCache:
        """获取或重建 balance cache——对标 dsh tool-pairing.ts:83 balanceCache。"""
        cached = self._cache_by_session.get(session_id)

        if (
            cached is None
            or cached.generation != generation
            or len(cached.cut_balanced) - 1 > len(surface_nodes)
        ):
            rebuilt = _BalanceCache(generation)
            self._extend_cache(rebuilt, surface_nodes, events)
            self._cache_by_session[session_id] = rebuilt
            return rebuilt

        if len(cached.cut_balanced) - 1 < len(surface_nodes):
            self._extend_cache(cached, surface_nodes, events)
        return cached

    def _extend_cache(
        self,
        cache: _BalanceCache,
        surface_nodes: Sequence[int],
        events: Sequence[Any],
    ) -> None:
        """折叠未处理的 surface sequences 到 balance state。

        对标 dsh tool-pairing.ts:50 extendCache。
        校验未见 tail 后再突变缓存（防部分推进）。
        """
        processed = len(cache.cut_balanced) - 1
        tail = surface_nodes[processed:]
        pending_cuts: list[bool] = []
        in_progress = cache.in_progress_tool_calls
        for seq in tail:
            event = _event_for_seq(events, seq)
            in_progress += _event_delta(event)
            if in_progress < 0:
                raise CorruptSurfaceError(
                    f"surface seq {seq} 的 tool/result 无前置 tool-call（corrupt surface）"
                )
            pending_cuts.append(in_progress == 0)

        for offset, seq in enumerate(tail):
            cache.index_by_seq[seq] = processed + offset
        cache.cut_balanced.extend(pending_cuts)
        cache.in_progress_tool_calls = in_progress

    def _cut_balance(
        self,
        cache: _BalanceCache,
        seq: int,
        offset: int,
    ) -> bool:
        """获取切分点平衡状态——对标 dsh tool-pairing.ts:100 cutBalance。"""
        index = cache.index_by_seq.get(seq)
        if index is None:
            raise CorruptSurfaceError(f"surface seq {seq} 不在当前 surface 中")
        balanced_idx = index + offset
        if balanced_idx < 0 or balanced_idx >= len(cache.cut_balanced):
            raise CorruptSurfaceError(f"surface seq {seq} 切分点越界")
        return cache.cut_balanced[balanced_idx]

    def balanced_before(
        self,
        session_id: str,
        surface_nodes: Sequence[int],
        generation: int,
        events: Sequence[Any],
        seq: int,
    ) -> bool:
        """切分点 seq 前是否平衡（inProgressToolCalls === 0）。

        对标 dsh tool-pairing.ts:117 toolPairingBalancedBefore。
        """
        cache = self._balance_cache(session_id, surface_nodes, generation, events)
        return self._cut_balance(cache, seq, 0)

    def balanced_after(
        self,
        session_id: str,
        surface_nodes: Sequence[int],
        generation: int,
        events: Sequence[Any],
        seq: int,
    ) -> bool:
        """切分点 seq 后是否平衡。

        对标 dsh tool-pairing.ts:129 toolPairingBalancedAfter。
        """
        cache = self._balance_cache(session_id, surface_nodes, generation, events)
        return self._cut_balance(cache, seq, 1)

    def adjust_to_nearest_balanced(
        self,
        session_id: str,
        surface_nodes: Sequence[int],
        generation: int,
        events: Sequence[Any],
        ideal_idx: int,
    ) -> int | None:
        """向前调整到最近平衡点——对标 dsh selectCompactableRange 平衡调整。

        Args:
            ideal_idx: 理想切分点位置索引

        Returns:
            最近平衡点的 seq，无可行返回 None
        """
        for idx in range(ideal_idx, -1, -1):
            if idx >= len(surface_nodes):
                continue
            seq = surface_nodes[idx]
            if self.balanced_before(session_id, surface_nodes, generation, events, seq):
                return seq
        return None

    def invalidate_cache(self, session_id: str) -> None:
        """使 session 的 balance cache 失效——surface 重写后调用。"""
        self._cache_by_session.pop(session_id, None)