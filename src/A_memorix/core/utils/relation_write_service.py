"""
统一关系写入与关系向量化服务。

规则：
1. 元数据是主数据源，向量是从索引。
2. 关系先写 metadata，再写向量。
3. 向量失败不回滚 metadata，依赖状态机与回填任务修复。
"""


from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.common.logger import get_logger


logger = get_logger("A_Memorix.RelationWriteService")


@dataclass
class RelationWriteResult:
    hash_value: str
    vector_written: bool
    vector_already_exists: bool
    vector_state: str


class RelationWriteService:
    """关系写入收口服务。"""

    ERROR_MAX_LEN = 500

    def __init__(
        self,
        metadata_store: Any,
        graph_store: Any,
        vector_store: Any,
        embedding_manager: Any,
        graph_vector_store: Any = None,
        use_typed_relation_ids: bool = False,
    ):
        self.metadata_store = metadata_store
        self.graph_store = graph_store
        self.vector_store = vector_store
        self.graph_vector_store = graph_vector_store or vector_store
        self.embedding_manager = embedding_manager
        self.use_typed_relation_ids = bool(use_typed_relation_ids)

    @staticmethod
    def build_relation_vector_text(subject: str, predicate: str, obj: str) -> str:
        s = str(subject or "").strip()
        p = str(predicate or "").strip()
        o = str(obj or "").strip()
        # 双表达：兼容关键词检索与自然语言问句
        return f"{s} {p} {o}\n{s}和{o}的关系是{p}"

    @staticmethod
    def relation_vector_id(hash_value: str) -> str:
        return f"relation:{str(hash_value or '').strip()}"

    async def ensure_relation_vector(
        self,
        hash_value: str,
        subject: str,
        predicate: str,
        obj: str,
        *,
        max_error_len: int = ERROR_MAX_LEN,
        typed_id: bool = False,
    ) -> RelationWriteResult:
        """
        为已有关系确保向量存在并更新状态。
        """
        vector_id = self.relation_vector_id(hash_value) if typed_id else str(hash_value or "").strip()
        target_store = self.graph_vector_store if typed_id else self.vector_store
        if vector_id in target_store:
            self.metadata_store.set_relation_vector_state(hash_value, "ready")
            return RelationWriteResult(
                hash_value=hash_value,
                vector_written=False,
                vector_already_exists=True,
                vector_state="ready",
            )

        self.metadata_store.set_relation_vector_state(hash_value, "pending")
        try:
            vector_text = self.build_relation_vector_text(subject, predicate, obj)
            embedding = await self.embedding_manager.encode(vector_text)
            target_store.add(
                vectors=embedding.reshape(1, -1),
                ids=[vector_id],
            )
            self.metadata_store.set_relation_vector_state(hash_value, "ready")
            logger.info(
                "metric.relation_vector_write_success=1 "
                "metric.relation_vector_write_success_count=1 "
                f"hash={hash_value[:16]}"
            )
            return RelationWriteResult(
                hash_value=hash_value,
                vector_written=True,
                vector_already_exists=False,
                vector_state="ready",
            )
        except ValueError:
            # 向量已存在冲突，按成功处理
            self.metadata_store.set_relation_vector_state(hash_value, "ready")
            return RelationWriteResult(
                hash_value=hash_value,
                vector_written=False,
                vector_already_exists=True,
                vector_state="ready",
            )
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "关系向量写入失败", exception=e)
            logger.warning("操作失败", exc_info=True)
            err = str(e)[:max_error_len]
            self.metadata_store.set_relation_vector_state(
                hash_value,
                "failed",
                error=err,
                bump_retry=True,
            )
            logger.warning(
                "metric.relation_vector_write_fail=1 "
                "metric.relation_vector_write_fail_count=1 "
                f"hash={hash_value[:16]} "
                f"err={err}"
            )
            return RelationWriteResult(
                hash_value=hash_value,
                vector_written=False,
                vector_already_exists=False,
                vector_state="failed",
            )

    async def upsert_relation_with_vector(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0,
        source_paragraph: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        write_vector: bool = True,
    ) -> RelationWriteResult:
        """
        统一关系写入：
        1) 写 metadata relation
        2) 写 graph edge relation_hash
        3) 按需写 relation vector
        """
        rel_hash = self.metadata_store.add_relation(
            subject=subject,
            predicate=predicate,
            obj=obj,
            confidence=confidence,
            source_paragraph=source_paragraph,
            metadata={**(metadata or {}), "graph_synced": False},
        )

        # P0-3: 跨存储事务补偿（ZG-30）
        # 对标 dsh defensive-patterns "Dispose must reach quiescence" + 补偿事务/Saga
        # 跨存储操作需 await 子操作完成 + 失败补偿，不得 fire-and-forget
        # P2: graph 写入传 confidence 作为权重
        try:
            self.graph_store.add_edges(
                [(subject, obj)], weights=[confidence], relation_hashes=[rel_hash]
            )
            self.metadata_store.relations.set_graph_synced(rel_hash, True)
        except Exception as e:
            logger.warning(
                f"graph write failed, relation hash={rel_hash} pending sync, err={e}"
            )

        if not write_vector:
            self.metadata_store.set_relation_vector_state(rel_hash, "none")
            return RelationWriteResult(
                hash_value=rel_hash,
                vector_written=False,
                vector_already_exists=False,
                vector_state="none",
            )

        return await self.ensure_relation_vector(
            hash_value=rel_hash,
            subject=subject,
            predicate=predicate,
            obj=obj,
            typed_id=self.use_typed_relation_ids,
        )

    async def compensate_graph_sync(self) -> None:
        """补偿 graph_synced=false 的 relation（P0-3 维护循环补偿）。

        对标 dsh "Dispose must reach quiescence"——失败不孤儿，需补偿。
        """
        pending = self.metadata_store.relations.get_relations_pending_graph_sync(limit=50)
        for rel in pending:
            for attempt in range(5):
                try:
                    self.graph_store.add_edges(
                        [(rel["subject"], rel["object"])],
                        weights=[rel["confidence"]],
                        relation_hashes=[rel["hash"]],
                    )
                    self.metadata_store.relations.set_graph_synced(rel["hash"], True)
                    break
                except Exception as e:
                    if attempt == 4:
                        logger.error(
                            f"graph sync failed after 5 retries, hash={rel['hash']}, err={e}"
                        )
                    continue
