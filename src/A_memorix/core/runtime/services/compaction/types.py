"""ZG-N5 压缩升级——事件类型与值对象定义。

对标 dsh compaction-basic/src/types.ts + region.ts 事件类型。
事务身份 UUID4 附着于 start/summary/end 三事件，重放时定位压缩边界。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional


class AbortSignal:
    """取消信号——对标 dsh AbortSignal，支持压缩让出。"""

    def __init__(self) -> None:
        self._aborted = False
        self._callbacks: list[Callable[[], None]] = []

    @property
    def aborted(self) -> bool:
        return self._aborted

    def abort(self) -> None:
        if self._aborted:
            return
        self._aborted = True
        for cb in self._callbacks:
            try:
                cb()
            except Exception:
                pass

    def on_abort(self, callback: Callable[[], None]) -> None:
        if self._aborted:
            callback()
        else:
            self._callbacks.append(callback)

    def throw_if_aborted(self) -> None:
        if self._aborted:
            raise CompactionAbortedError("压缩已取消")


class CompactionAbortedError(Exception):
    """压缩被取消异常。"""


@dataclass(frozen=True)
class CompactionId:
    """压缩事务身份（UUID4）——同一压缩操作的 start/summary/end 一致。"""

    value: str

    @classmethod
    def generate(cls) -> "CompactionId":
        import uuid

        return cls(value=str(uuid.uuid4()))


@dataclass(frozen=True)
class CompactionRange:
    """被压缩范围（值对象，不可变）。

    start/end 为 surface seq，start_idx/end_idx 为位置索引，shadowed_seqs 为被替换的 seq 列表。
    """

    start: int
    end: int
    start_idx: int
    end_idx: int
    shadowed_seqs: tuple[int, ...] = field(default_factory=tuple)


class CompactionReason(Enum):
    """压缩触发原因枚举。"""

    PRESSURE = "pressure"
    PERIODIC = "periodic"
    MANUAL = "manual"
    OVERFLOW_RECOVERY = "overflow_recovery"


@dataclass(frozen=True)
class ModelRoute:
    """模型路由信息——摘要生成使用的 provider/model/max_tokens。"""

    provider: str
    model: str
    max_tokens: int


@dataclass(frozen=True)
class CompactionStartEvent:
    """压缩开始事件（durable lock 标记）。

    对标 dsh region.ts:189 session.append('compaction/start', lifecycle)。
    """

    tx_id: CompactionId
    session_id: str
    range: CompactionRange
    triggered_at: datetime
    reason: CompactionReason
    turn: Optional[int] = None
    seq: int = 0


@dataclass(frozen=True)
class CompactionSummaryEvent:
    """压缩摘要事件——含摘要文本 + 原始范围引用 + 模型路由 + 闭合状态。"""

    tx_id: CompactionId
    summary: str
    range_ref: CompactionRange
    model_route: ModelRoute
    generated_at: datetime
    closed: bool = False
    error: Optional[str] = None
    seq: int = 0


@dataclass(frozen=True)
class CompactionEndEvent:
    """压缩结束事件——成功 error=None，失败 error 非 None。"""

    tx_id: CompactionId
    error: Optional[str] = None
    seq: int = 0


@dataclass(frozen=True)
class SurfaceReplacementRecord:
    """surface 替换记录——replace_generation 单调递增，用于 tool-pairing 缓存失效。"""

    replace_generation: int
    replaced_range: CompactionRange
    summary_node_id: str
    tx_id: CompactionId


@dataclass(frozen=True)
class SummaryNode:
    """摘要节点——surface 替换中替换原始范围的节点。"""

    node_id: str
    summary: str
    tx_id: CompactionId
    model_route: ModelRoute
    generated_at: datetime


@dataclass(frozen=True)
class CompactionResult:
    """压缩结果——返回给调用方。"""

    compaction_id: CompactionId
    shadowed_range: CompactionRange
    shadowed_seqs: tuple[int, ...]
    shadowed_token_count: int
    summary: str
    model_route: ModelRoute


@dataclass(frozen=True)
class EventSeq:
    """事件持久化后的序列标识。"""

    seq: int
    event_type: str


@dataclass(frozen=True)
class LockResult:
    """锁获取结果。"""

    acquired: bool
    tx_id: CompactionId
    stale_marker: bool = False


@dataclass(frozen=True)
class ReplaceResult:
    """surface 替换结果。"""

    new_generation: int
    replaced_range: CompactionRange
    summary_node_id: str


class ManualCompactionError(Exception):
    """手动压缩异常——busy/summary/commit/changed。"""

    def __init__(self, reason: str, message: str = "") -> None:
        self.reason = reason
        super().__init__(message or f"手动压缩失败: {reason}")


class SummaryNotSmallerError(Exception):
    """摘要不收敛异常——framed_tokens >= shadowed_tokens。"""


class CorruptSurfaceError(Exception):
    """surface 损坏异常——seq 无匹配事件或 tool/result 无前置 call。"""


class LockStateUnqueryableError(Exception):
    """锁状态不可查询异常——不假设无锁。"""


class IdleStateUnqueryableError(Exception):
    """空闲状态不可查询异常。"""