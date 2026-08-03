"""FusedWritePipeline — 统一写入管线（MF-P2-001/003/004/006）。

observe / ingest 均解析为概念图事件后调用 write()：

1. 幂等：同一 event_id 重复写入跳过（event_writes 表持久化去重）
2. 锁：涉及概念节点加 WriteLockManager 节点级锁（超时抛错）
3. 双投影串行写入（先事实投影后联想投影）在同一 SQLite BEGIN/COMMIT 事务
   （R05——SQLite 单写者模型不支持同事务并行写）
4. 向量写入在事务外：失败标记节点 embedding_pending=True（R06——向量是
   可重建索引，非权威数据源，失败不回滚概念图）
"""

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from src.common.logger import get_logger
from src.common.memory_types import MemoryWriteResult

from .concept_graph import ConceptGraph
from .concept_graph_store import ConceptGraphStore
from .models import ConceptNode, NodeCategory, RelationEdge, TraceEdge
from .unified_id_generator import UnifiedIdGenerator
from .write_lock_manager import WriteLockManager, WriteLockTimeoutError

logger = get_logger("A_Memorix.FusedWritePipeline")


class ConceptGraphWriteError(RuntimeError):
    """概念图写入失败（SQLite 异常映射，调用方负责回滚语义）。"""


@dataclass(slots=True)
class FusedWriteResult:
    """一次写入的结果。"""

    event_id: str
    written: bool = False
    nodes_written: int = 0
    relations_written: int = 0
    traces_written: int = 0
    embedding_pending: list[str] = field(default_factory=list)


class FusedWritePipeline:
    """统一写入管线。"""

    def __init__(
        self,
        concept_graph: ConceptGraph,
        store: ConceptGraphStore,
        write_lock_manager: Optional[WriteLockManager] = None,
        embedding_writer: Optional[Callable[[list[ConceptNode]], list[str]]] = None,
        concept_extractor: Optional[Callable[[str], Awaitable[list[str]]]] = None,
        write_lock_timeout: float = 5.0,
    ) -> None:
        """初始化。

        Args:
            concept_graph: 概念图核心
            store: 概念图存储（事务/幂等表）
            write_lock_manager: 节点级锁（默认新建）
            embedding_writer: 向量写入回调，输入待嵌入节点列表，返回嵌入成功的
                节点 id 列表；None 时跳过向量写入（全部标记 pending）
            concept_extractor: 概念提取回调（文本 → 概念名列表），
                observe_experience/ingest_summary 使用；None 时入口降级
            write_lock_timeout: 写入锁超时秒数（CX-P1：接线
                memory_fusion.write_lock_timeout）
        """
        self._graph = concept_graph
        self._store = store
        self._lock_manager = write_lock_manager or WriteLockManager()
        self._embedding_writer = embedding_writer
        self._concept_extractor = concept_extractor
        self._write_lock_timeout = max(0.1, float(write_lock_timeout))
        self._id_generator = UnifiedIdGenerator()

    async def write(
        self,
        *,
        event_id: str,
        concepts: list[ConceptNode],
        relations: list[RelationEdge] | None = None,
        traces: list[TraceEdge] | None = None,
    ) -> FusedWriteResult:
        """统一写入：一次写入产生事实投影 + 联想投影。

        幂等 → 锁 → 同一 SQLite 事务双投影串行写入 → 事务外向量写入。
        """
        relations = relations or []
        traces = traces or []
        if not event_id:
            raise ConceptGraphWriteError("event_id 为空——写入必须携带事件标识")

        if self._store.has_event_written(event_id):
            return FusedWriteResult(event_id=event_id, written=False)

        concept_ids = [c.id for c in concepts]
        token = await self._lock_manager.acquire(
            concept_ids, timeout=self._write_lock_timeout,
        )
        try:
            if self._store.has_event_written(event_id):
                return FusedWriteResult(event_id=event_id, written=False)
            return self._write_locked(
                event_id=event_id,
                concepts=concepts,
                relations=relations,
                traces=traces,
            )
        except WriteLockTimeoutError as exc:
            logger.warning("写入锁超时: event_id=%s concepts=%s", event_id, concept_ids)
            raise ConceptGraphWriteError(str(exc)) from exc
        finally:
            self._lock_manager.release(token)

    def _write_locked(
        self,
        *,
        event_id: str,
        concepts: list[ConceptNode],
        relations: list[RelationEdge],
        traces: list[TraceEdge],
    ) -> FusedWriteResult:
        """持锁状态下执行：双投影串行写入同一 SQLite 事务 + 向量写入。"""
        try:
            with self._store.transaction():
                for node in concepts:
                    self._store.upsert_node(node)
                for edge in relations:  # 先事实投影
                    self._store.upsert_relation_edge(edge)
                for edge in traces:  # 后联想投影
                    self._store.upsert_trace_edge(edge)
                self._store.mark_event_written(event_id)
        except Exception as exc:
            logger.error("概念图写入失败: event_id=%s error=%s", event_id, exc, exc_info=True)
            raise ConceptGraphWriteError(f"概念图写入失败: {exc}") from exc

        # 向量写入在事务外（R06）：失败标记 embedding_pending，不回滚概念图
        pending: list[str] = []
        if self._embedding_writer is not None:
            try:
                succeeded = self._embedding_writer(concepts) or []
                succeeded_set = set(succeeded)
                for node in concepts:
                    if node.id not in succeeded_set:
                        pending.append(node.id)
                        self._mark_embedding_pending(node.id)
            except Exception as exc:
                logger.warning(
                    "向量写入失败，标记 embedding_pending 后台补写: event_id=%s error=%s",
                    event_id,
                    exc,
                )
                for node in concepts:
                    pending.append(node.id)
                    self._mark_embedding_pending(node.id)
        else:
            for node in concepts:
                pending.append(node.id)
                self._mark_embedding_pending(node.id)

        return FusedWriteResult(
            event_id=event_id,
            written=True,
            nodes_written=len(concepts),
            relations_written=len(relations),
            traces_written=len(traces),
            embedding_pending=pending,
        )

    def _mark_embedding_pending(self, node_id: str) -> None:
        node = self._store.get_node_by_id(node_id)
        if node is None:
            return
        node.embedding_pending = True
        self._store.upsert_node(node)

    async def observe_experience(self, request: Any) -> MemoryWriteResult:
        """实时体验写入入口：概念提取 → 概念图双投影 write()。

        概念间两两建 Trace 边（共同出现 = 联想激活），perspective 标记 agent。
        未注入 concept_extractor 时返回失败结果（不抛异常）。
        """
        text = str(getattr(request, "text", "") or "").strip()
        agent_id = str(getattr(request, "agent_id", "") or "")
        source_id = str(getattr(request, "source_id", "") or "")
        valence = float(getattr(request, "valence", 0.0) or 0.0)

        if not text:
            return MemoryWriteResult(success=False, detail="observe 文本为空")
        if self._concept_extractor is None:
            return MemoryWriteResult(
                success=False, detail="concept_extractor 未注入，概念图写入跳过",
            )

        concept_names = await self._concept_extractor(text)
        if not concept_names:
            return MemoryWriteResult(success=False, detail="未提取到概念")

        now = time.time()
        concepts = [
            ConceptNode(
                id=self._id_generator.generate(name),
                name=name,
                type=NodeCategory.CONCEPT,
                created_at=now,
                updated_at=now,
            )
            for name in concept_names
        ]
        # 概念两两成对 → 联想投影（共同出现即联想激活）
        traces: list[TraceEdge] = []
        for i, src in enumerate(concepts):
            for dst in concepts[i + 1:]:
                traces.append(TraceEdge(
                    id=f"trace:{source_id}:{src.id}:{dst.id}",
                    source_concept_id=src.id,
                    target_concept_id=dst.id,
                    weight=0.5,
                    valence=valence,
                    perspective=f"agent:{agent_id}" if agent_id else "observe",
                    last_activated_at=now,
                    created_at=now,
                ))

        result = await self.write(
            event_id=source_id or f"observe:{now:.6f}",
            concepts=concepts,
            traces=traces,
        )
        return MemoryWriteResult(
            success=result.written,
            stored_ids=[c.id for c in concepts] if result.written else [],
            detail=f"concepts={result.nodes_written} traces={result.traces_written}",
        )

    async def ingest_summary(self, **kwargs: Any) -> dict:
        """离线摘要写入入口：概念提取 → write()（与 observe 同一管线）。

        kwargs: text / external_id / chat_id / agent_id
        """
        text = str(kwargs.get("text") or "").strip()
        external_id = str(kwargs.get("external_id") or "").strip()

        if not text:
            return {"success": False, "detail": "ingest 文本为空"}
        if self._concept_extractor is None:
            return {"success": False, "detail": "concept_extractor 未注入"}

        concept_names = await self._concept_extractor(text)
        if not concept_names:
            return {"success": False, "detail": "未提取到概念"}

        now = time.time()
        concepts = [
            ConceptNode(
                id=self._id_generator.generate(name),
                name=name,
                type=NodeCategory.CONCEPT,
                created_at=now,
                updated_at=now,
            )
            for name in concept_names
        ]
        result = await self.write(
            event_id=external_id or f"ingest:{now:.6f}",
            concepts=concepts,
        )
        return {
            "success": result.written,
            "concepts": [c.name for c in concepts],
            "detail": f"concepts={result.nodes_written}",
        }
