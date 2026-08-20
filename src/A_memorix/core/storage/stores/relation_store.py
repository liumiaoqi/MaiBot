"""
关系存储 — 从 MetadataStore 提取的关系 CRUD、V5 状态管理、保护/修剪、FTS。
"""

import pickle
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.common.logger import get_logger
from ...utils.hash import compute_hash
from ._utils import (
    as_optional_float,
    canonicalize_name,
    decode_metadata,
    deep_merge_dict,
    iter_sql_batches,
    normalize_hash_sequence,
    row_to_dict,
)

logger = get_logger("A_Memorix.RelationStore")


class RelationStore:
    """关系 CRUD + V5 状态 + 保护/修剪 + 回收站 + FTS。"""

    def __init__(self, conn: sqlite3.Connection, write_lock: Optional[threading.Lock] = None) -> None:
        self._conn = conn
        self._write_lock = write_lock or threading.RLock()

    # ==================================================================
    # 基础 CRUD
    # ==================================================================

    def compute_relation_hash(self, subject: str, predicate: str, obj: str) -> str:
        s_canon = canonicalize_name(subject)
        p_canon = canonicalize_name(predicate)
        o_canon = canonicalize_name(obj)
        if not all([s_canon, p_canon, o_canon]):
            raise ValueError("Relation components cannot be empty")
        relation_key = f"{s_canon}|{p_canon}|{o_canon}"
        return compute_hash(relation_key)

    def add_relation(
        self,
        subject: str,
        predicate: str,
        obj: str,
        vector_index: Optional[int] = None,
        confidence: float = 1.0,
        source_paragraph: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        hash_value = self.compute_relation_hash(subject, predicate, obj)
        now = datetime.now().timestamp()
        with self._write_lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO relations
                    (hash, subject, predicate, object, vector_index, confidence,
                     created_at, source_paragraph, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        hash_value,
                        subject,
                        predicate,
                        obj,
                        vector_index,
                        confidence,
                        now,
                        source_paragraph,
                        pickle.dumps(metadata or {}),
                    ),
                )
                self._conn.commit()
                if cursor.rowcount > 0:
                    logger.debug(f"添加关系: {subject} -{predicate}-> {obj}")
                else:
                    logger.debug(f"关系已存在: {subject} -{predicate}-> {obj}")

                if source_paragraph:
                    self.link_paragraph_relation(source_paragraph, hash_value)
                return hash_value
            except sqlite3.IntegrityError as e:
                logger.warning(f"添加关系异常: {e}")
                return hash_value

    def get_relation(
        self,
        hash_value: str,
        include_inactive: bool = True,
    ) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        if include_inactive:
            cursor.execute("SELECT * FROM relations WHERE hash = ?", (hash_value,))
        else:
            cursor.execute(
                """
                SELECT * FROM relations
                WHERE hash = ? AND (is_inactive IS NULL OR is_inactive = 0)
                """,
                (hash_value,),
            )
        row = cursor.fetchone()
        return row_to_dict(row) if row else None

    def get_relations_by_hashes(
        self,
        hash_values: Sequence[str],
        include_inactive: bool = True,
    ) -> Dict[str, Dict[str, Any]]:
        normalized = normalize_hash_sequence(hash_values)
        if not normalized:
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        cursor = self._conn.cursor()
        inactive_sql = "" if include_inactive else "AND (is_inactive IS NULL OR is_inactive = 0)"
        for batch in iter_sql_batches(normalized):
            placeholders = ",".join(["?"] * len(batch))
            cursor.execute(
                f"""
                SELECT * FROM relations
                WHERE hash IN ({placeholders}) {inactive_sql}
                """,
                tuple(batch),
            )
            for row in cursor.fetchall():
                payload = row_to_dict(row)
                out[str(payload.get("hash", ""))] = payload
        return out

    def delete_relation(self, hash_value: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM relations WHERE hash = ?", (hash_value,))
        self._conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"删除关系: {hash_value[:16]}...")
        return deleted

    def get_relations(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
        include_inactive: bool = True,
    ) -> List[Dict[str, Any]]:
        conditions = []
        params = []
        if subject:
            conditions.append("LOWER(subject) = ?")
            params.append(canonicalize_name(subject))
        if predicate:
            conditions.append("LOWER(predicate) = ?")
            params.append(canonicalize_name(predicate))
        if object:
            conditions.append("LOWER(object) = ?")
            params.append(canonicalize_name(object))
        if not include_inactive:
            conditions.append("(is_inactive IS NULL OR is_inactive = 0)")

        sql = "SELECT * FROM relations"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        cursor = self._conn.cursor()
        cursor.execute(sql, tuple(params))
        return [row_to_dict(row) for row in cursor.fetchall()]

    def get_relations_by_entity_names(
        self,
        entity_names: Sequence[str],
        include_inactive: bool = False,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """ZG-28 批量查询多个实体名作为 subject 或 object 的关系。

        Returns:
            Dict[entity_name, List[relation_dict]]，key=实体名，value=该实体作为
            subject 或 object 的关系列表（一个 relation 可能同时匹配 subject 和
            object，归入匹配的各 entity_name——与原逐条合并行为一致）。
        """
        canonicalized = [canonicalize_name(name) for name in entity_names if name and str(name).strip()]
        if not canonicalized:
            return {}
        # 去重保留顺序
        seen = set()
        unique_names = []
        for name in canonicalized:
            if name not in seen:
                seen.add(name)
                unique_names.append(name)

        out: Dict[str, List[Dict[str, Any]]] = {name: [] for name in unique_names}
        inactive_sql = "" if include_inactive else "AND (is_inactive IS NULL OR is_inactive = 0)"
        cursor = self._conn.cursor()
        for batch in iter_sql_batches(unique_names):
            placeholders = ",".join(["?"] * len(batch))
            cursor.execute(
                f"""
                SELECT * FROM relations
                WHERE (LOWER(subject) IN ({placeholders}) OR LOWER(object) IN ({placeholders}))
                {inactive_sql}
                """,
                tuple(batch) + tuple(batch),
            )
            for row in cursor.fetchall():
                payload = row_to_dict(row)
                row_subject = str(payload.get("subject", "")).lower()
                row_object = str(payload.get("object", "")).lower()
                for name in batch:
                    if row_subject == name or row_object == name:
                        out[name].append(payload)
        return out

    def get_all_triples(self) -> List[Tuple[str, str, str, str]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT subject, predicate, object, hash FROM relations")
        return list(cursor.fetchall())

    def count_relations(
        self,
        include_deleted: bool = False,
        only_deleted: bool = False,
    ) -> int:
        cursor = self._conn.cursor()
        if only_deleted:
            cursor.execute("SELECT COUNT(*) FROM deleted_relations")
            return cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM relations")
        active_count = cursor.fetchone()[0]
        if not include_deleted:
            return active_count
        cursor.execute("SELECT COUNT(*) FROM deleted_relations")
        deleted_count = cursor.fetchone()[0]
        return int(active_count) + int(deleted_count)

    def get_relation_db_snapshot(self) -> Tuple[int, float, str]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT
                COUNT(*) AS relation_count,
                COALESCE(MAX(created_at), 0) AS max_created_at,
                COALESCE(MAX(hash), '') AS max_hash
            FROM relations
            """
        )
        row = cursor.fetchone()
        if not row:
            return (0, 0.0, "")
        return (int(row[0] or 0), float(row[1] or 0.0), str(row[2] or ""))

    # ==================================================================
    # 段落-关系关联
    # ==================================================================

    def link_paragraph_relation(self, paragraph_hash: str, relation_hash: str) -> bool:
        with self._write_lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO paragraph_relations
                    (paragraph_hash, relation_hash)
                    VALUES (?, ?)
                    """,
                    (paragraph_hash, relation_hash),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    # ==================================================================
    # Metadata 更新
    # ==================================================================

    def update_relation_metadata(
        self,
        relation_hash: str,
        patch: Dict[str, Any],
        *,
        merge: bool = True,
    ) -> Optional[Dict[str, Any]]:
        hash_token = str(relation_hash or "").strip()
        if not hash_token:
            raise ValueError("relation_hash 不能为空")
        if not isinstance(patch, dict):
            raise TypeError("patch 必须是 dict")

        # P0-2: relation metadata RMW 原子化（ZG-30）
        # 对标 dsh defensive-patterns "Async state is not synchronous state"
        # RMW 竞态本质是异步状态（并发 SELECT metadata）当同步状态用，显式事务边界是修复
        # 不用 json_patch：metadata 是 pickle 序列化非 JSON，改 JSON 需迁移——显式事务零迁移风险
        for attempt in range(3):
            try:
                with self._write_lock:
                    cursor = self._conn.cursor()
                    cursor.execute("BEGIN IMMEDIATE")
                    cursor.execute(
                        "SELECT metadata FROM relations WHERE hash = ? LIMIT 1", (hash_token,)
                    )
                    row = cursor.fetchone()
                    if row is None:
                        cursor.execute("ROLLBACK")
                        return None

                    metadata = decode_metadata(row["metadata"])
                    updated = deep_merge_dict(metadata, patch) if merge else dict(patch)
                    cursor.execute(
                        "UPDATE relations SET metadata = ? WHERE hash = ?",
                        (pickle.dumps(updated), hash_token),
                    )
                    cursor.execute("COMMIT")
                return updated
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    try:
                        cursor.execute("ROLLBACK")
                    except Exception:
                        logger.exception("relation_store ROLLBACK 失败")
                    if attempt == 2:
                        logger.error(f"relation metadata update db locked after 3 retries, hash={hash_token}")
                        raise
                    continue
                raise

    # ==================================================================
    # P0-3: graph_synced 标记 + 补偿查询（ZG-30）
    # ==================================================================

    def set_graph_synced(self, relation_hash: str, synced: bool) -> None:
        """标记 relation 的 graph_synced 状态（P0-3 跨存储补偿）。"""
        hash_token = str(relation_hash or "").strip()
        if not hash_token:
            return
        self.update_relation_metadata(hash_token, {"graph_synced": bool(synced)}, merge=True)

    def get_relations_pending_graph_sync(self, limit: int = 50) -> list:
        """查询 graph_synced=false 的 relation（P0-3 补偿队列消费）。

        全表扫描 + pickle decode（低频：维护循环 1h 间隔）。
        先按 metadata IS NOT NULL 缩小范围。
        """
        with self._write_lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT hash, subject, object, confidence, metadata FROM relations "
                "WHERE metadata IS NOT NULL LIMIT ?",
                (limit * 10,),
            )
            rows = cursor.fetchall()

        pending = []
        for row in rows:
            try:
                meta = decode_metadata(row["metadata"])
                if meta.get("graph_synced") is False:
                    pending.append({
                        "hash": row["hash"],
                        "subject": row["subject"],
                        "object": row["object"],
                        "confidence": row["confidence"],
                    })
                    if len(pending) >= limit:
                        break
            except Exception:
                continue
        return pending

    def update_relation_timestamp(
        self,
        hash_value: str,
        access_count_delta: int = 1,
    ) -> None:
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE relations
            SET last_accessed = ?, access_count = access_count + ?
            WHERE hash = ?
            """,
            (now, access_count_delta, hash_value),
        )
        self._conn.commit()

    # ==================================================================
    # 向量状态
    # ==================================================================

    def set_relation_vector_state(
        self,
        hash_value: str,
        state: str,
        error: Optional[str] = None,
        bump_retry: bool = False,
    ) -> bool:
        state_norm = str(state or "").strip().lower()
        if state_norm not in {"none", "pending", "ready", "failed"}:
            raise ValueError(f"无效 vector_state: {state}")

        now = datetime.now().timestamp()
        err_text = (str(error).strip() if error is not None else None)
        if err_text:
            err_text = err_text[:500]
        clear_error = state_norm in {"none", "pending", "ready"}

        cursor = self._conn.cursor()
        if bump_retry:
            cursor.execute(
                """
                UPDATE relations
                SET vector_state = ?,
                    vector_updated_at = ?,
                    vector_error = ?,
                    vector_retry_count = COALESCE(vector_retry_count, 0) + 1
                WHERE hash = ?
                """,
                (state_norm, now, None if clear_error else err_text, hash_value),
            )
        else:
            cursor.execute(
                """
                UPDATE relations
                SET vector_state = ?,
                    vector_updated_at = ?,
                    vector_error = ?
                WHERE hash = ?
                """,
                (state_norm, now, None if clear_error else err_text, hash_value),
            )
        self._conn.commit()
        return cursor.rowcount > 0

    def list_relations_by_vector_state(
        self,
        states: List[str],
        limit: int = 200,
        max_retry: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        normalized_states = [
            str(s or "").strip().lower()
            for s in (states or [])
            if str(s or "").strip()
        ]
        normalized_states = [
            s for s in normalized_states if s in {"none", "pending", "ready", "failed"}
        ]
        if not normalized_states:
            return []

        placeholders = ",".join(["?"] * len(normalized_states))
        params: List[Any] = list(normalized_states)
        sql = f"""
            SELECT hash, subject, predicate, object, confidence, source_paragraph,
                   vector_state, vector_updated_at, vector_error, vector_retry_count, created_at
            FROM relations
            WHERE vector_state IN ({placeholders})
        """
        if max_retry is not None:
            sql += " AND COALESCE(vector_retry_count, 0) < ?"
            params.append(int(max_retry))
        sql += " ORDER BY COALESCE(vector_updated_at, created_at, 0) ASC LIMIT ?"
        params.append(max(1, int(limit)))

        cursor = self._conn.cursor()
        cursor.execute(sql, tuple(params))
        return [row_to_dict(row) for row in cursor.fetchall()]

    def count_relations_by_vector_state(self) -> Dict[str, int]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT COALESCE(vector_state, 'none') AS state, COUNT(*) AS cnt
            FROM relations
            GROUP BY COALESCE(vector_state, 'none')
            """
        )
        result: Dict[str, int] = {"none": 0, "pending": 0, "ready": 0, "failed": 0}
        total = 0
        for row in cursor.fetchall():
            state = str(row["state"] or "none").lower()
            count = int(row["cnt"] or 0)
            if state not in result:
                result[state] = 0
            result[state] += count
            total += count
        result["total"] = total
        return result

    # ==================================================================
    # 模糊查询
    # ==================================================================

    def search_relations_by_subject_or_object(
        self,
        query: str,
        *,
        limit: int = 5,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        q = str(query or "").strip()
        if not q:
            return []
        max_limit = int(max(1, limit))
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM relations
            WHERE subject LIKE ? OR object LIKE ?
            LIMIT ?
            """,
            (f"%{q}%", f"%{q}%", max_limit),
        )
        rows = [row_to_dict(row) for row in cursor.fetchall()]
        if rows or not include_deleted:
            return rows

        cursor.execute(
            """
            SELECT * FROM deleted_relations
            WHERE subject LIKE ? OR object LIKE ?
            LIMIT ?
            """,
            (f"%{q}%", f"%{q}%", max_limit),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]

    def get_relations_subject_object_map(
        self,
        hashes: List[str],
    ) -> Dict[str, Tuple[str, str]]:
        if not hashes:
            return {}
        cursor = self._conn.cursor()
        placeholders = ",".join(["?"] * len(hashes))
        cursor.execute(
            f"SELECT hash, subject, object FROM relations WHERE hash IN ({placeholders})",
            hashes,
        )
        return {str(row[0]): (str(row[1]), str(row[2])) for row in cursor.fetchall()}

    # ==================================================================
    # V5 状态管理
    # ==================================================================

    def get_relation_status_batch(self, hashes: List[str]) -> Dict[str, Dict[str, Any]]:
        if not hashes:
            return {}
        placeholders = ",".join(["?"] * len(hashes))
        cursor = self._conn.cursor()
        cursor.execute(
            f"""
            SELECT hash, is_inactive, confidence, is_pinned, protected_until,
                   last_reinforced, inactive_since
            FROM relations
            WHERE hash IN ({placeholders})
            """,
            hashes,
        )
        result = {}
        for row in cursor.fetchall():
            result[row["hash"]] = {
                "is_inactive": bool(row["is_inactive"]),
                "weight": row["confidence"],
                "is_pinned": bool(row["is_pinned"]),
                "protected_until": row["protected_until"],
                "last_reinforced": row["last_reinforced"],
                "inactive_since": row["inactive_since"],
            }
        return result

    def mark_relations_active(
        self,
        hashes: List[str],
        boost_weight: Optional[float] = None,
    ) -> None:
        if not hashes:
            return
        placeholders = ",".join(["?"] * len(hashes))
        cursor = self._conn.cursor()
        if boost_weight is not None:
            cursor.execute(
                f"""
                UPDATE relations
                SET is_inactive = 0, inactive_since = NULL,
                    confidence = MAX(confidence, ?)
                WHERE hash IN ({placeholders})
                """,
                (boost_weight, *hashes),
            )
        else:
            cursor.execute(
                f"""
                UPDATE relations
                SET is_inactive = 0, inactive_since = NULL
                WHERE hash IN ({placeholders})
                """,
                hashes,
            )
        self._conn.commit()

    def mark_relations_inactive(
        self,
        hashes: List[str],
        inactive_since: Optional[float] = None,
    ) -> None:
        if not hashes:
            return
        mark_time = inactive_since if inactive_since is not None else datetime.now().timestamp()
        cursor = self._conn.cursor()
        chunk_size = 500
        for i in range(0, len(hashes), chunk_size):
            chunk = hashes[i : i + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            sql = f"""
                UPDATE relations
                SET is_inactive = 1, inactive_since = ?
                WHERE hash IN ({placeholders})
            """
            cursor.execute(sql, [mark_time] + chunk)
        self._conn.commit()

    def update_relations_protection(
        self,
        hashes: List[str],
        protected_until: Optional[float] = None,
        is_pinned: Optional[bool] = None,
        last_reinforced: Optional[float] = None,
    ) -> None:
        if not hashes:
            return
        updates = []
        params = []
        if protected_until is not None:
            updates.append("protected_until = ?")
            params.append(protected_until)
        if is_pinned is not None:
            updates.append("is_pinned = ?")
            params.append(1 if is_pinned else 0)
        if last_reinforced is not None:
            updates.append("last_reinforced = ?")
            params.append(last_reinforced)
        if not updates:
            return

        sql_set = ", ".join(updates)
        placeholders = ",".join(["?"] * len(hashes))
        params.extend(hashes)
        cursor = self._conn.cursor()
        cursor.execute(
            f"UPDATE relations SET {sql_set} WHERE hash IN ({placeholders})", params
        )
        self._conn.commit()

    def reinforce_relations(self, hashes: List[str]) -> None:
        if not hashes:
            return
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        chunk_size = 500
        for i in range(0, len(hashes), chunk_size):
            chunk = hashes[i : i + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            sql = f"""
                UPDATE relations
                SET last_reinforced = ?, is_inactive = 0, inactive_since = NULL
                WHERE hash IN ({placeholders})
            """
            cursor.execute(sql, [now] + chunk)
        self._conn.commit()

    def protect_relations(
        self,
        hashes: List[str],
        is_pinned: bool = False,
        ttl_seconds: float = 0,
    ) -> None:
        if not hashes:
            return
        now = datetime.now().timestamp()
        protected_until = (now + ttl_seconds) if ttl_seconds > 0 else 0
        cursor = self._conn.cursor()
        chunk_size = 500
        for i in range(0, len(hashes), chunk_size):
            chunk = hashes[i : i + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            sql = f"""
                UPDATE relations
                SET is_pinned = ?, protected_until = ?
                WHERE hash IN ({placeholders})
            """
            cursor.execute(sql, [is_pinned, protected_until] + chunk)
        self._conn.commit()

    def get_protected_relations_hashes(self) -> List[str]:
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT hash FROM relations
            WHERE is_pinned = 1 OR protected_until > ?
            """,
            (now,),
        )
        return [row[0] for row in cursor.fetchall()]

    def get_memory_status_summary(self, now_ts: Optional[float] = None) -> Dict[str, int]:
        now_ts = float(now_ts) if now_ts is not None else datetime.now().timestamp()
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM relations WHERE is_inactive = 0")
        active_count = int(cursor.fetchone()[0] or 0)
        cursor.execute("SELECT COUNT(*) FROM relations WHERE is_inactive = 1")
        inactive_count = int(cursor.fetchone()[0] or 0)
        cursor.execute("SELECT COUNT(*) FROM deleted_relations")
        deleted_count = int(cursor.fetchone()[0] or 0)
        cursor.execute("SELECT COUNT(*) FROM relations WHERE is_pinned = 1")
        pinned_count = int(cursor.fetchone()[0] or 0)
        cursor.execute("SELECT COUNT(*) FROM relations WHERE protected_until > ?", (now_ts,))
        ttl_count = int(cursor.fetchone()[0] or 0)
        return {
            "active_count": active_count,
            "inactive_count": inactive_count,
            "deleted_count": deleted_count,
            "pinned_count": pinned_count,
            "temp_protected_count": ttl_count,
        }

    # ==================================================================
    # 修剪 / 备份 / 恢复
    # ==================================================================

    def get_prune_candidates(self, cutoff_time: float, limit: int = 1000) -> List[str]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT hash FROM relations
            WHERE is_inactive = 1 AND inactive_since < ?
            LIMIT ?
            """,
            (cutoff_time, limit),
        )
        return [row[0] for row in cursor.fetchall()]

    def backup_and_delete_relations(self, hashes: List[str]) -> int:
        if not hashes:
            return 0
        placeholders = ",".join(["?"] * len(hashes))
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                f"""
                INSERT OR REPLACE INTO deleted_relations
                (hash, subject, predicate, object, vector_index, confidence, created_at,
                 vector_state, vector_updated_at, vector_error, vector_retry_count,
                 source_paragraph, metadata, is_permanent, last_accessed, access_count,
                 is_inactive, inactive_since, is_pinned, protected_until, last_reinforced, deleted_at)
                SELECT
                 hash, subject, predicate, object, vector_index, confidence, created_at,
                 vector_state, vector_updated_at, vector_error, vector_retry_count,
                 source_paragraph, metadata, is_permanent, last_accessed, access_count,
                 is_inactive, inactive_since, is_pinned, protected_until, last_reinforced, ?
                FROM relations
                WHERE hash IN ({placeholders})
                """,
                (now, *hashes),
            )
            cursor.execute(f"DELETE FROM relations WHERE hash IN ({placeholders})", hashes)
            deleted_count = cursor.rowcount
            self._conn.commit()
            return deleted_count
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, '备份删除失败', exception=e)
            logger.error(f"备份删除失败: {e}")
            self._conn.rollback()
            return 0

    def restore_relation_metadata(self, hash_value: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        try:
            cursor.execute("SELECT * FROM deleted_relations WHERE hash = ?", (hash_value,))
            row = cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            if "deleted_at" in data:
                del data["deleted_at"]

            columns = list(data.keys())
            placeholders = ",".join(["?"] * len(columns))
            cols_str = ",".join(columns)
            values = list(data.values())

            cursor.execute(
                f"INSERT OR REPLACE INTO relations ({cols_str}) VALUES ({placeholders})",
                values,
            )
            cursor.execute("DELETE FROM deleted_relations WHERE hash = ?", (hash_value,))
            self._conn.commit()
            return row_to_dict(row)
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, '恢复关系失败:  -', exception=e)
            logger.error(f"恢复关系失败: {hash_value} - {e}")
            self._conn.rollback()
            return None

    def restore_relation(self, hash_value: str) -> Optional[Dict[str, Any]]:
        return self.restore_relation_metadata(hash_value)

    def restore_relation_status_from_snapshot(
        self,
        hash_value: str,
        snapshot: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        token = str(hash_value or "").strip()
        if not token or not isinstance(snapshot, dict):
            return None

        current = self.get_relation_status_batch([token]).get(token)
        if current is None:
            restored = self.restore_relation(token)
            if restored is None:
                return None

        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE relations
            SET is_inactive = ?, confidence = ?, is_pinned = ?,
                protected_until = ?, last_reinforced = ?, inactive_since = ?
            WHERE hash = ?
            """,
            (
                1 if bool(snapshot.get("is_inactive")) else 0,
                float(snapshot.get("weight", 0.0) or 0.0),
                1 if bool(snapshot.get("is_pinned")) else 0,
                as_optional_float(snapshot.get("protected_until")),
                as_optional_float(snapshot.get("last_reinforced")),
                as_optional_float(snapshot.get("inactive_since")),
                token,
            ),
        )
        self._conn.commit()
        return self.get_relation_status_batch([token]).get(token)

    # ==================================================================
    # 回收站
    # ==================================================================

    def get_deleted_relations(self, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM deleted_relations ORDER BY deleted_at DESC LIMIT ?", (limit,)
        )
        data = []
        for row in cursor.fetchall():
            d = dict(row)
            if "metadata" in d and d["metadata"]:
                try:
                    d["metadata"] = pickle.loads(d["metadata"])
                except Exception as exc:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.WARNING, '反序列化关系元数据失败', exception=exc)
                    logger.warning(f"反序列化关系元数据失败: {exc}")
                    pass
            data.append(d)
        return data

    def get_deleted_relation(self, hash_value: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM deleted_relations WHERE hash = ?", (hash_value,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        if "metadata" in d and d["metadata"]:
            try:
                d["metadata"] = pickle.loads(d["metadata"])
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, '反序列化关系元数据失败', exception=exc)
                logger.warning(f"反序列化关系元数据失败: {exc}")
                pass
        return d

    def purge_deleted_relations(
        self,
        *,
        cutoff_time: float,
        limit: int = 1000,
    ) -> List[str]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT hash FROM deleted_relations
            WHERE deleted_at IS NOT NULL AND deleted_at < ?
            ORDER BY deleted_at ASC LIMIT ?
            """,
            (float(cutoff_time), max(1, int(limit or 1000))),
        )
        hashes = [
            str(row[0] or "").strip()
            for row in cursor.fetchall()
            if str(row[0] or "").strip()
        ]
        if not hashes:
            return []
        placeholders = ",".join(["?"] * len(hashes))
        cursor.execute(f"DELETE FROM deleted_relations WHERE hash IN ({placeholders})", tuple(hashes))
        self._conn.commit()
        return hashes

    def get_orphan_deleted_relation_hashes(self, limit: int = 200) -> List[str]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT d.hash FROM deleted_relations d
            LEFT JOIN relations r ON r.hash = d.hash
            WHERE r.hash IS NULL
            LIMIT ?
            """,
            (int(max(1, limit)),),
        )
        return [str(row[0]) for row in cursor.fetchall()]

    # ==================================================================
    # Hash 别名
    # ==================================================================

    def resolve_relation_hash_alias(
        self,
        value: str,
        *,
        include_deleted: bool = False,
    ) -> List[str]:
        token = str(value or "").strip().lower()
        if not token:
            return []
        if len(token) == 64 and all(ch in "0123456789abcdef" for ch in token):
            cursor = self._conn.cursor()
            cursor.execute("SELECT 1 FROM relations WHERE hash = ? LIMIT 1", (token,))
            if cursor.fetchone():
                return [token]
            if include_deleted:
                cursor.execute(
                    "SELECT 1 FROM deleted_relations WHERE hash = ? LIMIT 1", (token,)
                )
                if cursor.fetchone():
                    return [token]
            return []
        if len(token) != 32 or not all(ch in "0123456789abcdef" for ch in token):
            return []
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT hash FROM relation_hash_aliases WHERE alias32 = ?", (token,)
        )
        row = cursor.fetchone()
        if not row:
            return []
        return [str(row[0])]

    def rebuild_relation_hash_aliases(self) -> Dict[str, Any]:
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relation_hash_aliases (
                alias32 TEXT PRIMARY KEY,
                hash TEXT NOT NULL
            )
        """)
        cursor.execute("DELETE FROM relation_hash_aliases")

        cursor.execute("SELECT hash FROM relations")
        hashes = [str(r[0]) for r in cursor.fetchall()]
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='deleted_relations'"
        )
        has_deleted_relations = cursor.fetchone() is not None
        if has_deleted_relations:
            cursor.execute("SELECT hash FROM deleted_relations")
            hashes.extend(str(r[0]) for r in cursor.fetchall())

        alias_map: Dict[str, str] = {}
        conflicts: Dict[str, set] = {}
        for h in hashes:
            if len(h) != 64:
                continue
            alias = h[:32]
            old = alias_map.get(alias)
            if old is None:
                alias_map[alias] = h
            elif old != h:
                conflicts.setdefault(alias, set()).update({old, h})

        for alias, full_hash in alias_map.items():
            if alias in conflicts:
                continue
            cursor.execute(
                "INSERT INTO relation_hash_aliases(alias32, hash) VALUES (?, ?)",
                (alias, full_hash),
            )
        self._conn.commit()
        return {
            "inserted": len(alias_map) - len(conflicts),
            "conflict_count": len(conflicts),
            "conflicts": sorted(conflicts.keys()),
        }

    def search_relation_hashes_by_text(self, query: str, limit: int = 5) -> List[str]:
        q = str(query or "").strip()
        if not q:
            return []
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT hash FROM relations WHERE subject LIKE ? OR object LIKE ? LIMIT ?",
            (f"%{q}%", f"%{q}%", int(max(1, limit))),
        )
        return [str(row[0]) for row in cursor.fetchall()]

    def search_deleted_relation_hashes_by_text(
        self, query: str, limit: int = 5
    ) -> List[str]:
        q = str(query or "").strip()
        if not q:
            return []
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT hash FROM deleted_relations WHERE subject LIKE ? OR object LIKE ? LIMIT ?",
            (f"%{q}%", f"%{q}%", int(max(1, limit))),
        )
        return [str(row[0]) for row in cursor.fetchall()]

    # ==================================================================
    # FTS5 — 关系全文检索
    # ==================================================================

    def ensure_relations_fts_schema(self) -> bool:
        cur = self._conn.cursor()
        try:
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS relations_fts
                USING fts5(
                    relation_hash UNINDEXED,
                    content,
                    tokenize='unicode61'
                )
            """)
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS relations_ai
                AFTER INSERT ON relations
                BEGIN
                    INSERT INTO relations_fts(relation_hash, content)
                    VALUES (
                        new.hash,
                        COALESCE(new.subject, '') || ' ' ||
                        COALESCE(new.predicate, '') || ' ' ||
                        COALESCE(new.object, '')
                    );
                END
            """)
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS relations_ad
                AFTER DELETE ON relations
                BEGIN
                    DELETE FROM relations_fts WHERE relation_hash = old.hash;
                END
            """)
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS relations_au
                AFTER UPDATE OF subject, predicate, object ON relations
                BEGIN
                    DELETE FROM relations_fts WHERE relation_hash = new.hash;
                    INSERT INTO relations_fts(relation_hash, content)
                    VALUES (
                        new.hash,
                        COALESCE(new.subject, '') || ' ' ||
                        COALESCE(new.predicate, '') || ' ' ||
                        COALESCE(new.object, '')
                    );
                END
            """)
            self._conn.commit()
            return True
        except sqlite3.OperationalError as e:
            logger.warning(f"relations FTS5 schema 创建失败（可能不支持 FTS5）: {e}")
            self._conn.rollback()
            return False

    def ensure_relations_fts_backfilled(self) -> bool:
        cur = self._conn.cursor()
        try:
            cur.execute("SELECT COUNT(1) AS n FROM relations")
            rel_count = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(1) AS n FROM relations_fts")
            fts_count = int(cur.fetchone()[0])
            if rel_count != fts_count:
                cur.execute("DELETE FROM relations_fts")
                cur.execute("""
                    INSERT INTO relations_fts(relation_hash, content)
                    SELECT
                        r.hash,
                        COALESCE(r.subject, '') || ' ' ||
                        COALESCE(r.predicate, '') || ' ' ||
                        COALESCE(r.object, '')
                    FROM relations r
                """)
                self._conn.commit()
                logger.info(f"relations FTS 回填完成: relations={rel_count}, fts={rel_count}")
            return True
        except sqlite3.OperationalError as e:
            logger.warning(f"relations FTS 回填失败: {e}")
            self._conn.rollback()
            return False

    def fts_search_relations_bm25(
        self,
        match_query: str,
        limit: int = 20,
        max_doc_len: int = 512,
        include_inactive: bool = True,
    ) -> List[Dict[str, Any]]:
        if not match_query.strip():
            return []
        cur = self._conn.cursor()
        active_clause = (
            "" if include_inactive else " AND (r.is_inactive IS NULL OR r.is_inactive = 0)"
        )
        try:
            cur.execute(
                f"""
                SELECT
                    r.hash, r.subject, r.predicate, r.object,
                    bm25(relations_fts) AS bm25_score
                FROM relations_fts
                JOIN relations r ON r.hash = relations_fts.relation_hash
                WHERE relations_fts MATCH ?
                {active_clause}
                ORDER BY bm25_score ASC
                LIMIT ?
                """,
                (match_query, max(1, int(limit))),
            )
            rows = cur.fetchall()
            out: List[Dict[str, Any]] = []
            for row in rows:
                content = f"{row['subject']} {row['predicate']} {row['object']}"
                if max_doc_len > 0:
                    content = content[:max_doc_len]
                out.append(
                    {
                        "hash": row["hash"],
                        "subject": row["subject"],
                        "predicate": row["predicate"],
                        "object": row["object"],
                        "content": content,
                        "bm25_score": float(row["bm25_score"]),
                    }
                )
            return out
        except sqlite3.OperationalError as e:
            logger.warning(f"relations FTS 查询失败: {e}")
            return []
