"""
实体存储 — 从 MetadataStore 提取的实体 CRUD 与关联操作。
"""

import pickle
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from src.common.logger import get_logger
from ...utils.hash import compute_hash
from ._utils import (
    canonicalize_name,
    normalize_hash_sequence,
    iter_sql_batches,
    row_to_dict,
)

logger = get_logger("A_Memorix.EntityStore")


class EntityStore:
    """实体 CRUD + 段落-实体关联管理。"""

    def __init__(self, conn: sqlite3.Connection, write_lock: Optional[threading.Lock] = None) -> None:
        self._conn = conn
        self._write_lock = write_lock or threading.RLock()

    # ------------------------------------------------------------------
    # 实体 CRUD
    # ------------------------------------------------------------------

    def add_entity(
        self,
        name: str,
        vector_index: Optional[int] = None,
        source_paragraph: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """添加实体。返回实体哈希值。"""
        name_normalized = canonicalize_name(name)
        if not name_normalized:
            raise ValueError("Entity name cannot be empty")

        hash_value = compute_hash(name_normalized)
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO entities
                (hash, name, vector_index, appearance_count, created_at, metadata)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (
                    hash_value,
                    name,
                    vector_index,
                    now,
                    pickle.dumps(metadata or {}),
                ),
            )
            logger.debug(f"添加实体: {name} ({hash_value[:8]})")
            self._conn.commit()

            if source_paragraph:
                self.link_paragraph_entity(source_paragraph, hash_value)
            return hash_value

        except sqlite3.IntegrityError:
            self.revive_if_deleted(entity_hashes=[hash_value])
            cursor.execute(
                "UPDATE entities SET appearance_count = appearance_count + 1 WHERE hash = ?",
                (hash_value,),
            )
            self._conn.commit()
            logger.debug(f"实体已存在(复活/计数+1): {name}")
            if source_paragraph:
                self.link_paragraph_entity(source_paragraph, hash_value)
            return hash_value

    def get_entity(self, hash_value: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM entities WHERE hash = ?", (hash_value,))
        row = cursor.fetchone()
        return row_to_dict(row) if row else None

    def get_entities_by_hashes(
        self,
        hash_values: Sequence[str],
    ) -> Dict[str, Dict[str, Any]]:
        normalized = normalize_hash_sequence(hash_values)
        if not normalized:
            return {}

        out: Dict[str, Dict[str, Any]] = {}
        cursor = self._conn.cursor()
        for batch in iter_sql_batches(normalized):
            placeholders = ",".join(["?"] * len(batch))
            cursor.execute(
                f"SELECT * FROM entities WHERE hash IN ({placeholders})",
                tuple(batch),
            )
            for row in cursor.fetchall():
                payload = row_to_dict(row)
                out[str(payload.get("hash", ""))] = payload
        return out

    def delete_entity(self, hash_or_name: str) -> bool:
        """删除实体（级联删除相关关联）。"""
        cursor = self._conn.cursor()
        entity_name = None
        entity_hash = None

        cursor.execute("SELECT name, hash FROM entities WHERE hash = ?", (hash_or_name,))
        row = cursor.fetchone()
        if row:
            entity_name = row[0]
            entity_hash = row[1]
        else:
            cursor.execute("SELECT name, hash FROM entities WHERE name = ?", (hash_or_name,))
            row = cursor.fetchone()
            if row:
                entity_name = row[0]
                entity_hash = row[1]
            else:
                name_canon = canonicalize_name(hash_or_name)
                canon_hash = compute_hash(name_canon)
                cursor.execute("SELECT name, hash FROM entities WHERE hash = ?", (canon_hash,))
                row = cursor.fetchone()
                if row:
                    entity_name = row[0]
                    entity_hash = row[1]

        if not entity_name or not entity_hash:
            logger.debug(f"删除实体请求跳过：未在元数据记录中找到 {hash_or_name}")
            return False

        logger.info(f"开始删除实体: {entity_name} (Hash: {entity_hash[:8]}...)")
        try:
            cursor.execute(
                "SELECT hash FROM relations WHERE subject = ? OR object = ?",
                (entity_name, entity_name),
            )
            relation_hashes = [r[0] for r in cursor.fetchall()]
            if relation_hashes:
                logger.info(f"发现 {len(relation_hashes)} 个相关关系，准备级联删除")
                placeholders = ",".join(["?"] * len(relation_hashes))
                cursor.execute(
                    f"DELETE FROM paragraph_relations WHERE relation_hash IN ({placeholders})",
                    relation_hashes,
                )
                cursor.execute(
                    f"DELETE FROM relations WHERE hash IN ({placeholders})",
                    relation_hashes,
                )
                logger.info("相关关系已级联删除")

            cursor.execute("DELETE FROM paragraph_entities WHERE entity_hash = ?", (entity_hash,))
            cursor.execute("DELETE FROM entities WHERE hash = ?", (entity_hash,))
            self._conn.commit()
            logger.info("实体删除完成")
            return True
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "删除实体失败", exception=e)
            logger.error(f"删除实体时发生错误: {e}")
            self._conn.rollback()
            return False

    def count_entities(self) -> int:
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM entities")
        return cursor.fetchone()[0]

    def is_entity_still_referenced(self, entity_hash: str, entity_name: str = "") -> bool:
        token_hash = str(entity_hash or "").strip()
        if token_hash:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT 1 FROM paragraph_entities WHERE entity_hash = ? LIMIT 1",
                (token_hash,),
            )
            if cursor.fetchone() is not None:
                return True

        canon_name = canonicalize_name(entity_name)
        if canon_name:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT 1 FROM relations
                WHERE LOWER(TRIM(subject)) = ? OR LOWER(TRIM(object)) = ?
                LIMIT 1
                """,
                (canon_name, canon_name),
            )
            if cursor.fetchone() is not None:
                return True
        return False

    # ------------------------------------------------------------------
    # 段落-实体关联
    # ------------------------------------------------------------------

    def link_paragraph_entity(
        self,
        paragraph_hash: str,
        entity_hash: str,
        mention_count: int = 1,
    ) -> bool:
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                """
                INSERT OR IGNORE INTO paragraph_entities
                (paragraph_hash, entity_hash, mention_count)
                VALUES (?, ?, ?)
                """,
                (paragraph_hash, entity_hash, mention_count),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    """
                    UPDATE paragraph_entities
                    SET mention_count = mention_count + ?
                    WHERE paragraph_hash = ? AND entity_hash = ?
                    """,
                    (mention_count, paragraph_hash, entity_hash),
                )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    # ------------------------------------------------------------------
    # 软删除 / GC
    # ------------------------------------------------------------------

    def mark_as_deleted(self, hashes: List[str]) -> int:
        if not hashes:
            return 0
        now = datetime.now().timestamp()
        count = 0
        batch_size = 900
        for i in range(0, len(hashes), batch_size):
            batch = hashes[i : i + batch_size]
            placeholders = ",".join(["?"] * len(batch))
            cursor = self._conn.cursor()
            cursor.execute(
                f"""
                UPDATE entities
                SET is_deleted = 1, deleted_at = ?
                WHERE is_deleted = 0 AND hash IN ({placeholders})
                """,
                [now] + batch,
            )
            count += cursor.rowcount
        self._conn.commit()
        if count > 0:
            logger.info(f"软删除标记 (entities): {count} 项")
        return count

    def sweep_deleted_items(self, grace_period_seconds: float) -> List[tuple]:
        now = datetime.now().timestamp()
        cutoff = now - grace_period_seconds
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT hash, name FROM entities
            WHERE is_deleted = 1 AND deleted_at < ?
            """,
            (cutoff,),
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def physically_delete_entities(self, hashes: List[str]) -> int:
        if not hashes:
            return 0
        count = 0
        batch_size = 900
        for i in range(0, len(hashes), batch_size):
            batch = hashes[i : i + batch_size]
            placeholders = ",".join(["?"] * len(batch))
            cursor = self._conn.cursor()
            cursor.execute(f"DELETE FROM entities WHERE hash IN ({placeholders})", batch)
            count += cursor.rowcount
        self._conn.commit()
        return count

    def revive_if_deleted(self, entity_hashes: List[str]) -> int:
        count = 0
        if entity_hashes:
            batch_size = 900
            for i in range(0, len(entity_hashes), batch_size):
                batch = entity_hashes[i : i + batch_size]
                placeholders = ",".join(["?"] * len(batch))
                cursor = self._conn.cursor()
                cursor.execute(
                    f"""
                    UPDATE entities
                    SET is_deleted = 0, deleted_at = NULL
                    WHERE is_deleted = 1 AND hash IN ({placeholders})
                    """,
                    batch,
                )
                count += cursor.rowcount
        if count > 0:
            self._conn.commit()
            logger.info(f"自动复活: {count} 项实体")
        return count

    def revive_entities_by_names(self, names: List[str]) -> int:
        if not names:
            return 0
        hashes = [compute_hash(canonicalize_name(n)) for n in names]
        return self.revive_if_deleted(entity_hashes=hashes)

    def restore_entity_by_hash(self, entity_hash: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute(
            "UPDATE entities SET is_deleted=0, deleted_at=NULL WHERE hash=?",
            (str(entity_hash),),
        )
        changed = cursor.rowcount > 0
        if changed:
            self._conn.commit()
        return changed

    def get_entity_status_batch(self, hashes: List[str]) -> Dict[str, Dict[str, Any]]:
        if not hashes:
            return {}
        result = {}
        batch_size = 900
        for i in range(0, len(hashes), batch_size):
            batch = hashes[i : i + batch_size]
            placeholders = ",".join(["?"] * len(batch))
            cursor = self._conn.cursor()
            cursor.execute(
                f"""
                SELECT hash, is_deleted, deleted_at
                FROM entities
                WHERE hash IN ({placeholders})
                """,
                batch,
            )
            for row in cursor.fetchall():
                result[row[0]] = {"is_deleted": bool(row[1]), "deleted_at": row[2]}
        return result

    def get_deleted_entities(self, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT hash, name, deleted_at
            FROM entities
            WHERE is_deleted = 1
            ORDER BY deleted_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        items = []
        for row in cursor.fetchall():
            items.append(
                {
                    "hash": row[0],
                    "name": row[1],
                    "type": "entity",
                    "deleted_at": row[2],
                }
            )
        return items

    def get_entity_gc_candidates(
        self,
        isolated_hashes: List[str],
        retention_seconds: float,
    ) -> List[str]:
        if not isolated_hashes:
            return []

        normalized_hashes: List[str] = []
        for item in isolated_hashes:
            if not item:
                continue
            v = str(item).strip()
            if len(v) == 64 and all(c in "0123456789abcdefABCDEF" for c in v):
                normalized_hashes.append(v.lower())
            else:
                canon = canonicalize_name(v)
                if canon:
                    normalized_hashes.append(compute_hash(canon))

        normalized_hashes = list(dict.fromkeys(normalized_hashes))
        if not normalized_hashes:
            return []

        now = datetime.now().timestamp()
        cutoff = now - retention_seconds
        candidates = []
        batch_size = 900

        for i in range(0, len(normalized_hashes), batch_size):
            batch = normalized_hashes[i : i + batch_size]
            placeholders = ",".join(["?"] * len(batch))
            query = f"""
                SELECT e.hash FROM entities e
                WHERE e.hash IN ({placeholders})
                AND e.is_deleted = 0
                AND (e.created_at IS NULL OR e.created_at < ?)
                AND NOT EXISTS (
                    SELECT 1 FROM paragraph_entities pe
                    JOIN paragraphs p ON pe.paragraph_hash = p.hash
                    WHERE pe.entity_hash = e.hash
                    AND p.is_deleted = 0
                )
            """
            cursor = self._conn.cursor()
            cursor.execute(query, [*batch, cutoff])
            candidates.extend([row[0] for row in cursor.fetchall()])

        return candidates
