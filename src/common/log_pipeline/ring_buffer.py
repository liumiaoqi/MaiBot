"""环形缓冲 — 最近 N 条结构化日志的内存存储（ZG-2 BUF 域）。

对标 Linux printk 环形缓冲：固定容量 + 字节上限 + ERROR 保留优先级。
"""

from dataclasses import dataclass, field
import threading


@dataclass(frozen=True)
class BufferEntry:
    """环形缓冲条目（字段名与 JSONL 既有命名一致，spec 6.1）。"""

    sequence: int            # 单调递增，进程内不重复
    timestamp: str           # ISO 8601（与 JSONL 时间格式一致）
    level: str               # DEBUG/INFO/WARNING/ERROR/CRITICAL
    logger_name: str
    module: str              # structlog 处理链产出，可空
    event: str               # 日志消息文本，可空
    rate_limit: bool = False  # 仅摘要日志为 True
    extra: dict = field(default_factory=dict)  # 其他结构化字段，超长截断
    truncated: bool = False  # 单条超长截断标记


_LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


class RingBuffer:
    """定长环形缓冲。

    实现：定长 list + head 指针（覆盖写），支持 ERROR/CRITICAL 保留优先级——
    超限时优先淘汰最旧的非 ERROR 条目，全 ERROR 则覆盖最旧（兜底）。
    双上限：条数 capacity + 字节 max_bytes，任一超限即触发淘汰。
    """

    def __init__(self, capacity: int, max_bytes: int, entry_max_bytes: int) -> None:
        self._capacity = capacity
        self._max_bytes = max_bytes
        self._entry_max_bytes = entry_max_bytes
        self._slots: list[BufferEntry | None] = [None] * capacity
        self._head = 0          # 下一个写入位置
        self._size = 0          # 当前条数
        self._total_bytes = 0   # 当前字节占用（估算：event + logger_name 等）
        self._seq = 0           # 单调序号
        self._lock = threading.RLock()

    @property
    def size(self) -> int:
        with self._lock:
            return self._size

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._total_bytes

    def append(self, entry: BufferEntry) -> None:
        """写入条目；超限时优先淘汰最旧低级别。"""
        with self._lock:
            entry_bytes = self._entry_bytes(entry)

            # 单条超长截断（不影响条目计数）
            if entry_bytes > self._entry_max_bytes:
                entry = self._truncate_entry(entry)
                entry_bytes = self._entry_bytes(entry)

            # 条数满 → 淘汰
            while self._size >= self._capacity:
                if not self._evict_oldest_non_error():
                    break  # 全 ERROR，兜底覆盖最旧

            # 字节超限 → 继续淘汰（保留 ERROR）
            while self._total_bytes + entry_bytes > self._max_bytes and self._size > 0:
                if not self._evict_oldest_non_error():
                    break

            # 写入
            seq = self._seq
            self._seq += 1
            final_entry = BufferEntry(
                sequence=seq,
                timestamp=entry.timestamp,
                level=entry.level,
                logger_name=entry.logger_name,
                module=entry.module,
                event=entry.event,
                rate_limit=entry.rate_limit,
                extra=entry.extra,
                truncated=entry.truncated,
            )
            self._slots[self._head] = final_entry
            self._head = (self._head + 1) % self._capacity
            if self._size < self._capacity:
                self._size += 1
            self._total_bytes += entry_bytes

    def snapshot(self, limit: int | None = None) -> list[BufferEntry]:
        """返回最近条目的快照（按写入顺序，最新在后）。线程安全。"""
        with self._lock:
            if self._size == 0:
                return []
            # 按写入顺序遍历（从最旧到最新）
            start = (self._head - self._size) % self._capacity
            ordered: list[BufferEntry] = []
            for i in range(self._size):
                idx = (start + i) % self._capacity
                entry = self._slots[idx]
                if entry is not None:
                    ordered.append(entry)
            if limit is not None and limit > 0:
                ordered = ordered[-limit:]
            return list(ordered)

    def drain(self) -> list[BufferEntry]:
        """取出全部条目（导出用），导出后清空。"""
        with self._lock:
            entries = self.snapshot()
            self._slots = [None] * self._capacity
            self._head = 0
            self._size = 0
            self._total_bytes = 0
            return entries

    # ── 内部 ──────────────────────────────────────────────

    @staticmethod
    def _entry_bytes(entry: BufferEntry) -> int:
        """估算单条字节（event + logger_name + module + extra 序列化近似）。"""
        size = len(entry.event or "") + len(entry.logger_name or "") + len(entry.module or "")
        for k, v in entry.extra.items():
            size += len(str(k)) + len(str(v))
        return size + 64  # 固定开销（时间戳/级别/序号等）

    def _truncate_entry(self, entry: BufferEntry) -> BufferEntry:
        """单条超长截断（保留头部，标记 truncated）。"""
        max_chars = self._entry_max_bytes // 4  # UTF-8 中文 3-4 字节，保守取 1/4
        return BufferEntry(
            sequence=entry.sequence,
            timestamp=entry.timestamp,
            level=entry.level,
            logger_name=entry.logger_name,
            module=entry.module,
            event=(entry.event or "")[:max_chars],
            rate_limit=entry.rate_limit,
            extra=entry.extra,
            truncated=True,
        )

    def _evict_oldest_non_error(self) -> bool:
        """淘汰最旧的非 ERROR/CRITICAL 条目。返回是否成功淘汰。"""
        start = (self._head - self._size) % self._capacity
        for i in range(self._size):
            idx = (start + i) % self._capacity
            entry = self._slots[idx]
            if entry is not None and _LEVEL_ORDER.get(entry.level, 30) < 40:
                # 淘汰该条目
                self._slots[idx] = None
                self._total_bytes -= self._entry_bytes(entry)
                self._size -= 1
                return True
        return False  # 全 ERROR，调用方兜底覆盖最旧
