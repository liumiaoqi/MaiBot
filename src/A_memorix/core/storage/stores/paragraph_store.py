"""
段落存储 — 从 MetadataStore 提取的段落 CRUD、FTS、N-gram 等全部段落相关操作。
"""

import pickle
import re
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.common.logger import get_logger
from ...utils.hash import compute_hash, normalize_text
from ...utils.time_parser import normalize_time_meta
from ._utils import (
    char_ngrams,
    decode_metadata,
    dedupe_episode_sources,
    iter_sql_batches,
    merge_paragraph_metadata,
    normalize_episode_source,
    normalize_hash_sequence,
    row_to_dict,
)

try:
    import jieba  # type: ignore
    HAS_JIEBA = True
except Exception:
    HAS_JIEBA = False

logger = get_logger("A_Memorix.ParagraphStore")


class ParagraphStore:
    """段落 CRUD + FTS5 + N-gram 倒排索引 + 软删除 / GC。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ==================================================================
    # 段落 CRUD
    # ==================================================================

    def add_paragraph(
        self,
        content: str,
        vector_index: Optional[int] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        knowledge_type: str = "mixed",
        time_meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        content_normalized = normalize_text(content)
        hash_value = compute_hash(content_normalized)
        now = datetime.now().timestamp()
        word_count = len(content_normalized.split())
        normalized_time = normalize_time_meta(time_meta)

        cursor = self._conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO paragraphs
                (
                    hash, content, vector_index, created_at, updated_at, metadata, source, word_count,
                    event_time, event_time_start, event_time_end, time_granularity, time_confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hash_value,
                    content,
                    vector_index,
                    now,
                    now,
                    pickle.dumps(metadata or {}),
                    source,
                    word_count,
                    normalized_time.get("event_time"),
                    normalized_time.get("event_time_start"),
                    normalized_time.get("event_time_end"),
                    normalized_time.get("time_granularity"),
                    normalized_time.get("time_confidence", 1.0),
                ),
            )
            self._upsert_paragraph_ngram_if_ready(hash_value, content, count_delta=1)
            self.fts_upsert_tokenized_paragraph(hash_value)
            self._conn.commit()
            logger.info(f"添加段落: hash={hash_value[:16]}..., words={word_count}")
            return hash_value
        except sqlite3.IntegrityError:
            logger.debug(f"段落已存在: {hash_value[:16]}...")
            if metadata:
                self._merge_existing_paragraph_metadata(hash_value, metadata)
            self.revive_if_deleted(paragraph_hashes=[hash_value])
            return hash_value

    def add_paragraph_batch(self, paragraphs: list[dict]) -> list[str]:
        """批量添加段落，使用 executemany。返回 hash 列表。"""
        hashes = []
        rows = []
        now = datetime.now().timestamp()
        for p in paragraphs:
            content_normalized = normalize_text(p["content"])
            h = compute_hash(content_normalized)
            hashes.append(h)
            word_count = len(content_normalized.split())
            rows.append((h, p["content"], word_count, now, now))
        with self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO paragraphs (hash, content, word_count, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
        return hashes

    def get_paragraph(self, hash_value: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM paragraphs WHERE hash = ?", (hash_value,))
        row = cursor.fetchone()
        return row_to_dict(row) if row else None

    def get_paragraphs_by_hashes(
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
                f"SELECT * FROM paragraphs WHERE hash IN ({placeholders})",
                tuple(batch),
            )
            for row in cursor.fetchall():
                payload = row_to_dict(row)
                out[str(payload.get("hash", ""))] = payload
        return out

    def update_paragraph_time_meta(
        self,
        paragraph_hash: str,
        time_meta: Dict[str, Any],
    ) -> bool:
        normalized = normalize_time_meta(time_meta)
        if not normalized:
            return False

        updates: List[str] = []
        params: List[Any] = []
        for key in [
            "event_time", "event_time_start", "event_time_end",
            "time_granularity", "time_confidence",
        ]:
            if key in normalized:
                updates.append(f"{key} = ?")
                params.append(normalized[key])

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now().timestamp())
        params.append(paragraph_hash)

        cursor = self._conn.cursor()
        cursor.execute(
            f"UPDATE paragraphs SET {', '.join(updates)} WHERE hash = ?",
            tuple(params),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def update_paragraph_metadata(
        self,
        paragraph_hash: str,
        patch: Dict[str, Any],
        *,
        merge: bool = True,
    ) -> Optional[Dict[str, Any]]:
        hash_token = str(paragraph_hash or "").strip()
        if not hash_token:
            raise ValueError("paragraph_hash 不能为空")
        if not isinstance(patch, dict):
            raise TypeError("patch 必须是 dict")

        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT metadata, is_deleted FROM paragraphs WHERE hash = ? LIMIT 1",
            (hash_token,),
        )
        row = cursor.fetchone()
        if row is None or bool(row["is_deleted"]):
            return None

        metadata = decode_metadata(row["metadata"])
        updated = merge_paragraph_metadata(metadata, patch) if merge else dict(patch)
        cursor.execute(
            "UPDATE paragraphs SET metadata = ?, updated_at = ? WHERE hash = ?",
            (pickle.dumps(updated), datetime.now().timestamp(), hash_token),
        )
        self._conn.commit()
        return updated

    def delete_paragraph(self, hash_value: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute("SELECT is_deleted FROM paragraphs WHERE hash = ?", (hash_value,))
        row = cursor.fetchone()
        was_active = bool(row and (row["is_deleted"] is None or int(row["is_deleted"]) == 0))
        self._delete_paragraph_ngrams_if_ready(
            [hash_value],
            count_delta=-1 if was_active else 0,
        )
        self.fts_delete_tokenized_paragraph(hash_value)
        cursor.execute("DELETE FROM paragraphs WHERE hash = ?", (hash_value,))
        self._conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"删除段落: {hash_value[:16]}...")
        return deleted

    def delete_paragraph_atomic(self, paragraph_hash: str) -> Dict[str, Any]:
        cleanup_plan: Dict[str, Any] = {
            "paragraph_hash": paragraph_hash,
            "vector_id_to_remove": None,
            "edges_to_remove": [],
            "relation_prune_ops": [],
            "episode_sources_to_rebuild": [],
        }
        cursor = self._conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                "SELECT relation_hash FROM paragraph_relations WHERE paragraph_hash = ?",
                (paragraph_hash,),
            )
            candidate_relations = [row[0] for row in cursor.fetchall()]
            cursor.execute(
                "SELECT hash, source, is_deleted FROM paragraphs WHERE hash = ?",
                (paragraph_hash,),
            )
            paragraph_row = cursor.fetchone()
            paragraph_was_active = bool(
                paragraph_row
                and (paragraph_row["is_deleted"] is None or int(paragraph_row["is_deleted"]) == 0)
            )
            if paragraph_row:
                cleanup_plan["vector_id_to_remove"] = paragraph_hash
                cleanup_plan["episode_sources_to_rebuild"] = dedupe_episode_sources(
                    [paragraph_row["source"]]
                )

            self._delete_paragraph_ngrams_if_ready(
                [paragraph_hash],
                count_delta=-1 if paragraph_was_active else 0,
            )
            self.fts_delete_tokenized_paragraph(paragraph_hash)
            cursor.execute("DELETE FROM paragraphs WHERE hash = ?", (paragraph_hash,))

            orphaned_hashes = []
            for rel_hash in candidate_relations:
                count = cursor.execute(
                    "SELECT count(*) FROM paragraph_relations WHERE relation_hash = ?",
                    (rel_hash,),
                ).fetchone()[0]
                if count == 0:
                    cursor.execute(
                        "SELECT subject, object FROM relations WHERE hash = ?", (rel_hash,)
                    )
                    rel_info = cursor.fetchone()
                    if rel_info:
                        s_val, o_val = rel_info[0], rel_info[1]
                        cleanup_plan["relation_prune_ops"].append((s_val, o_val, rel_hash))
                        sibling_count = cursor.execute(
                            """
                            SELECT count(*) FROM relations
                            WHERE LOWER(TRIM(subject)) = LOWER(TRIM(?))
                              AND LOWER(TRIM(object)) = LOWER(TRIM(?))
                              AND hash != ?
                            """,
                            (s_val, o_val, rel_hash),
                        ).fetchone()[0]
                        if sibling_count == 0:
                            cleanup_plan["edges_to_remove"].append((s_val, o_val))
                    orphaned_hashes.append(rel_hash)

            if orphaned_hashes:
                placeholders = ",".join(["?"] * len(orphaned_hashes))
                cursor.execute(
                    f"DELETE FROM relations WHERE hash IN ({placeholders})", orphaned_hashes
                )

            self._conn.commit()
            if cleanup_plan["vector_id_to_remove"]:
                logger.debug(
                    f"原子删除段落成功: {paragraph_hash}, "
                    f"计划清理 {len(orphaned_hashes)} 个孤儿关系"
                )
            return cleanup_plan
        except Exception as e:
            self._conn.rollback()
            logger.error(f"DB Transaction failed: {e}")
            raise

    def query_paragraphs_temporal(
        self,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None,
        person: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
        allow_created_fallback: bool = True,
    ) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []

        effective_start = "COALESCE(p.event_time_start, p.event_time, p.event_time_end"
        effective_end = "COALESCE(p.event_time_end, p.event_time, p.event_time_start"
        if allow_created_fallback:
            effective_start += ", p.created_at)"
            effective_end += ", p.created_at)"
        else:
            effective_start += ")"
            effective_end += ")"

        conditions = ["(p.is_deleted IS NULL OR p.is_deleted = 0)"]
        params: List[Any] = []

        if source:
            conditions.append("p.source = ?")
            params.append(source)
        if person:
            conditions.append(
                """
                EXISTS (
                    SELECT 1 FROM paragraph_entities pe
                    JOIN entities e ON e.hash = pe.entity_hash
                    WHERE pe.paragraph_hash = p.hash
                      AND LOWER(e.name) LIKE ?
                )
                """
            )
            params.append(f"%{str(person).strip().lower()}%")

        if start_ts is not None and end_ts is not None:
            conditions.append(f"({effective_end} >= ? AND {effective_start} <= ?)")
            params.extend([start_ts, end_ts])
        elif start_ts is not None:
            conditions.append(f"({effective_end} >= ?)")
            params.append(start_ts)
        elif end_ts is not None:
            conditions.append(f"({effective_start} <= ?)")
            params.append(end_ts)

        where_sql = " AND ".join(conditions)
        sql = f"""
            SELECT p.* FROM paragraphs p
            WHERE {where_sql}
            ORDER BY {effective_end} DESC, p.updated_at DESC
            LIMIT ?
        """
        params.append(limit)
        cursor = self._conn.cursor()
        cursor.execute(sql, tuple(params))
        return [row_to_dict(row) for row in cursor.fetchall()]

    def get_paragraphs_by_source(self, source: str) -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM paragraphs WHERE source = ?", (source,))
        return [row_to_dict(row) for row in cursor.fetchall()]

    def get_all_sources(self) -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT source, COUNT(*) as count, MAX(created_at) as last_updated
            FROM paragraphs
            WHERE source IS NOT NULL AND source != ''
              AND (is_deleted IS NULL OR is_deleted = 0)
            GROUP BY source
            ORDER BY last_updated DESC
            """
        )
        results = []
        for row in cursor.fetchall():
            results.append({"source": row[0], "count": row[1], "last_updated": row[2]})
        return results

    def get_live_paragraphs_by_source(self, source: str) -> List[Dict[str, Any]]:
        token = normalize_episode_source(source)
        if not token:
            return []
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM paragraphs
            WHERE TRIM(COALESCE(source, '')) = ?
              AND (is_deleted IS NULL OR is_deleted = 0)
            ORDER BY created_at ASC, hash ASC
            """,
            (token,),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]

    def search_paragraphs_by_content(self, content_query: str) -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM paragraphs WHERE content LIKE ?",
            (f"%{content_query}%",),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]

    def count_paragraphs(
        self,
        include_deleted: bool = False,
        only_deleted: bool = False,
    ) -> int:
        cursor = self._conn.cursor()
        if only_deleted:
            cursor.execute("SELECT COUNT(*) FROM paragraphs WHERE is_deleted = 1")
        elif include_deleted:
            cursor.execute("SELECT COUNT(*) FROM paragraphs")
        else:
            cursor.execute("SELECT COUNT(*) FROM paragraphs WHERE is_deleted = 0")
        return cursor.fetchone()[0]

    def _get_sources_for_paragraph_hashes(
        self,
        hashes: List[str],
        *,
        include_deleted: bool = True,
    ) -> List[str]:
        normalized_hashes = [
            str(item or "").strip()
            for item in (hashes or [])
            if str(item or "").strip()
        ]
        if not normalized_hashes:
            return []
        placeholders = ",".join(["?"] * len(normalized_hashes))
        conditions = ["hash IN ({})".format(placeholders), "TRIM(COALESCE(source, '')) != ''"]
        if not include_deleted:
            conditions.append("(is_deleted IS NULL OR is_deleted = 0)")
        cursor = self._conn.cursor()
        cursor.execute(
            f"""
            SELECT DISTINCT TRIM(source) AS source
            FROM paragraphs
            WHERE {' AND '.join(conditions)}
            """,
            tuple(normalized_hashes),
        )
        return dedupe_episode_sources([row["source"] for row in cursor.fetchall()])

    # ==================================================================
    # Metadata 合并
    # ==================================================================

    def _merge_existing_paragraph_metadata(
        self,
        paragraph_hash: str,
        metadata_patch: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(metadata_patch, dict):
            raise TypeError("metadata_patch 必须是 dict")
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT metadata FROM paragraphs WHERE hash = ? LIMIT 1",
            (paragraph_hash,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        metadata = decode_metadata(row["metadata"])
        updated = merge_paragraph_metadata(metadata, metadata_patch)
        if updated == metadata:
            return metadata
        cursor.execute(
            "UPDATE paragraphs SET metadata = ?, updated_at = ? WHERE hash = ?",
            (pickle.dumps(updated), datetime.now().timestamp(), paragraph_hash),
        )
        self._conn.commit()
        return updated

    # ==================================================================
    # FTS5 — 段落全文检索（基于原始 content external-content 表）
    # ==================================================================

    def ensure_fts_schema(self) -> bool:
        cur = self._conn.cursor()
        try:
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS paragraphs_fts
                USING fts5(
                    content,
                    content='paragraphs',
                    content_rowid='rowid',
                    tokenize='unicode61'
                )
            """)
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS paragraphs_ai
                AFTER INSERT ON paragraphs
                BEGIN
                    INSERT INTO paragraphs_fts(rowid, content)
                    VALUES (new.rowid, new.content);
                END
            """)
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS paragraphs_ad
                AFTER DELETE ON paragraphs
                BEGIN
                    INSERT INTO paragraphs_fts(paragraphs_fts, rowid, content)
                    VALUES ('delete', old.rowid, old.content);
                END
            """)
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS paragraphs_au
                AFTER UPDATE OF content ON paragraphs
                BEGIN
                    INSERT INTO paragraphs_fts(paragraphs_fts, rowid, content)
                    VALUES ('delete', old.rowid, old.content);
                    INSERT INTO paragraphs_fts(rowid, content)
                    VALUES (new.rowid, new.content);
                END
            """)
            self._conn.commit()
            return True
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS5 schema 创建失败（可能不支持 FTS5）: {e}")
            self._conn.rollback()
            return False

    def ensure_fts_backfilled(self) -> bool:
        cur = self._conn.cursor()
        try:
            cur.execute("SELECT COUNT(1) AS n FROM paragraphs")
            para_count = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(1) AS n FROM paragraphs_fts")
            fts_count = int(cur.fetchone()[0])
            if para_count > 0 and fts_count != para_count:
                cur.execute("INSERT INTO paragraphs_fts(paragraphs_fts) VALUES ('rebuild')")
                self._conn.commit()
                logger.info(f"FTS 回填完成: paragraphs={para_count}, fts={para_count}")
            return True
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS 回填失败: {e}")
            self._conn.rollback()
            return False

    def fts_upsert_paragraph(self, paragraph_hash: str) -> bool:
        cur = self._conn.cursor()
        try:
            cur.execute(
                "SELECT rowid, content FROM paragraphs WHERE hash = ?",
                (paragraph_hash,),
            )
            row = cur.fetchone()
            if not row:
                return False
            rowid = int(row[0])
            content = str(row[1] or "")
            cur.execute(
                "INSERT OR REPLACE INTO paragraphs_fts(rowid, content) VALUES (?, ?)",
                (rowid, content),
            )
            self._conn.commit()
            return True
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS upsert 失败: {e}")
            self._conn.rollback()
            return False

    def fts_delete_paragraph(self, paragraph_hash: str) -> bool:
        cur = self._conn.cursor()
        try:
            cur.execute(
                "SELECT rowid, content FROM paragraphs WHERE hash = ?",
                (paragraph_hash,),
            )
            row = cur.fetchone()
            if not row:
                return False
            rowid = int(row[0])
            content = str(row[1] or "")
            cur.execute(
                "INSERT INTO paragraphs_fts(paragraphs_fts, rowid, content) VALUES ('delete', ?, ?)",
                (rowid, content),
            )
            self._conn.commit()
            return True
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS delete 失败: {e}")
            self._conn.rollback()
            return False

    def fts_search_bm25(
        self,
        match_query: str,
        limit: int = 20,
        max_doc_len: int = 2000,
    ) -> List[Dict[str, Any]]:
        if not match_query.strip():
            return []
        cur = self._conn.cursor()
        try:
            cur.execute(
                """
                SELECT p.hash, p.content, bm25(paragraphs_fts) AS bm25_score
                FROM paragraphs_fts
                JOIN paragraphs p ON p.rowid = paragraphs_fts.rowid
                WHERE paragraphs_fts MATCH ?
                  AND (p.is_deleted IS NULL OR p.is_deleted = 0)
                ORDER BY bm25_score ASC
                LIMIT ?
                """,
                (match_query, max(1, int(limit))),
            )
            rows = cur.fetchall()
            results: List[Dict[str, Any]] = []
            for row in rows:
                content = str(row["content"] or "")
                if max_doc_len > 0:
                    content = content[:max_doc_len]
                results.append(
                    {
                        "hash": row["hash"],
                        "content": content,
                        "bm25_score": float(row["bm25_score"]),
                    }
                )
            return results
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS 查询失败: {e}")
            return []

    def fts_doc_count(self) -> int:
        cur = self._conn.cursor()
        try:
            cur.execute("SELECT COUNT(1) FROM paragraphs_fts")
            return int(cur.fetchone()[0])
        except sqlite3.OperationalError:
            return 0

    # ==================================================================
    # 预分词段落 FTS5 Shadow Index
    # ==================================================================

    @staticmethod
    def _paragraph_phrase_tokens(text: str) -> List[str]:
        return [
            token.lower()
            for token in re.findall(r"[A-Za-z0-9_]+|[一-鿿]{2,}", str(text or ""))
        ]

    def _tokenize_paragraph_for_fts(self, text: str) -> str:
        source = str(text or "")
        if HAS_JIEBA and jieba is not None:
            try:
                tokens = [
                    token.strip().lower()
                    for token in jieba.cut_for_search(source)
                    if token.strip()
                ]
            except Exception:
                tokens = list(source.lower())
        else:
            tokens = list(source.lower())
        tokens.extend(self._paragraph_phrase_tokens(source))
        return " ".join(dict.fromkeys(token for token in tokens if token))

    def _refresh_paragraph_tokenized_fts_meta(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='paragraph_tokenized_fts_meta'"
        )
        if cur.fetchone() is None:
            return
        cur.execute(
            "SELECT COUNT(1) FROM paragraphs WHERE is_deleted IS NULL OR is_deleted = 0"
        )
        para_count = int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO paragraph_tokenized_fts_meta(key, value) VALUES('paragraph_count', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (str(para_count),),
        )
        cur.execute(
            """
            INSERT INTO paragraph_tokenized_fts_meta(key, value) VALUES('updated_at', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (str(datetime.now().timestamp()),),
        )

    def ensure_paragraph_tokenized_fts_schema(self) -> bool:
        cur = self._conn.cursor()
        try:
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS paragraphs_tokenized_fts
                USING fts5(
                    paragraph_hash UNINDEXED,
                    tokenized,
                    tokenize='unicode61'
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS paragraph_tokenized_fts_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            self._conn.commit()
            return True
        except sqlite3.OperationalError as e:
            logger.warning(f"paragraph tokenized FTS5 schema 创建失败: {e}")
            self._conn.rollback()
            return False

    def ensure_paragraph_tokenized_fts_backfilled(self) -> bool:
        cur = self._conn.cursor()
        started = time.perf_counter()
        try:
            if not self.ensure_paragraph_tokenized_fts_schema():
                return False
            cur.execute(
                "SELECT COUNT(1) FROM paragraphs WHERE is_deleted IS NULL OR is_deleted = 0"
            )
            para_count = int(cur.fetchone()[0])
            cur.execute(
                "SELECT value FROM paragraph_tokenized_fts_meta WHERE key='paragraph_count'"
            )
            meta_row = cur.fetchone()
            indexed_docs = int(meta_row[0]) if meta_row and meta_row[0] is not None else -1
            if indexed_docs == para_count:
                return True

            cur.execute("DELETE FROM paragraphs_tokenized_fts")
            cur.execute(
                """
                SELECT hash, content FROM paragraphs
                WHERE is_deleted IS NULL OR is_deleted = 0
                """
            )
            batch: List[Tuple[str, str]] = []
            batch_size = 1000
            while True:
                rows = cur.fetchmany(batch_size)
                if not rows:
                    break
                for row in rows:
                    batch.append(
                        (
                            str(row["hash"]),
                            self._tokenize_paragraph_for_fts(str(row["content"] or "")),
                        )
                    )
                cur.executemany(
                    "INSERT INTO paragraphs_tokenized_fts(paragraph_hash, tokenized) VALUES (?, ?)",
                    batch,
                )
                batch.clear()
            if batch:
                cur.executemany(
                    "INSERT INTO paragraphs_tokenized_fts(paragraph_hash, tokenized) VALUES (?, ?)",
                    batch,
                )
            self._refresh_paragraph_tokenized_fts_meta()
            self._conn.commit()
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                f"paragraph tokenized FTS 回填完成: paragraphs={para_count}, duration_ms={elapsed_ms:.2f}"
            )
            return True
        except Exception as e:
            logger.warning(f"paragraph tokenized FTS 回填失败: {e}")
            self._conn.rollback()
            return False

    def fts_upsert_tokenized_paragraph(self, paragraph_hash: str) -> bool:
        cur = self._conn.cursor()
        try:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='paragraphs_tokenized_fts'"
            )
            if cur.fetchone() is None:
                return False
            cur.execute(
                """
                SELECT hash, content FROM paragraphs
                WHERE hash = ? AND (is_deleted IS NULL OR is_deleted = 0)
                """,
                (paragraph_hash,),
            )
            row = cur.fetchone()
            cur.execute(
                "DELETE FROM paragraphs_tokenized_fts WHERE paragraph_hash = ?",
                (paragraph_hash,),
            )
            if row:
                cur.execute(
                    "INSERT INTO paragraphs_tokenized_fts(paragraph_hash, tokenized) VALUES (?, ?)",
                    (
                        paragraph_hash,
                        self._tokenize_paragraph_for_fts(str(row["content"] or "")),
                    ),
                )
            self._refresh_paragraph_tokenized_fts_meta()
            self._conn.commit()
            return True
        except sqlite3.OperationalError as e:
            self._conn.rollback()
            logger.warning(f"paragraph tokenized FTS upsert 失败: {e}")
            return False

    def fts_delete_tokenized_paragraph(self, paragraph_hash: str) -> bool:
        cur = self._conn.cursor()
        try:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='paragraphs_tokenized_fts'"
            )
            if cur.fetchone() is None:
                return False
            cur.execute(
                "DELETE FROM paragraphs_tokenized_fts WHERE paragraph_hash = ?",
                (paragraph_hash,),
            )
            self._refresh_paragraph_tokenized_fts_meta()
            self._conn.commit()
            return True
        except sqlite3.OperationalError as e:
            self._conn.rollback()
            logger.warning(f"paragraph tokenized FTS delete 失败: {e}")
            return False

    def fts_search_tokenized_paragraphs_bm25(
        self,
        match_query: str,
        limit: int = 20,
        max_doc_len: int = 2000,
    ) -> List[Dict[str, Any]]:
        if not match_query.strip():
            return []
        cur = self._conn.cursor()
        try:
            cur.execute(
                """
                SELECT p.hash, p.content, bm25(paragraphs_tokenized_fts) AS bm25_score
                FROM paragraphs_tokenized_fts
                JOIN paragraphs p ON p.hash = paragraphs_tokenized_fts.paragraph_hash
                WHERE paragraphs_tokenized_fts MATCH ?
                  AND (p.is_deleted IS NULL OR p.is_deleted = 0)
                ORDER BY bm25_score ASC
                LIMIT ?
                """,
                (match_query, max(1, int(limit))),
            )
            rows = cur.fetchall()
            results: List[Dict[str, Any]] = []
            for row in rows:
                content = str(row["content"] or "")
                if max_doc_len > 0:
                    content = content[:max_doc_len]
                results.append(
                    {
                        "hash": row["hash"],
                        "content": content,
                        "bm25_score": float(row["bm25_score"]),
                    }
                )
            return results
        except sqlite3.OperationalError as e:
            logger.warning(f"paragraph tokenized FTS 查询失败: {e}")
            return []

    # ==================================================================
    # N-gram 倒排索引
    # ==================================================================

    def ensure_paragraph_ngram_schema(self) -> bool:
        cur = self._conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS paragraph_ngrams (
                    term TEXT NOT NULL,
                    paragraph_hash TEXT NOT NULL,
                    PRIMARY KEY (term, paragraph_hash),
                    FOREIGN KEY (paragraph_hash) REFERENCES paragraphs(hash) ON DELETE CASCADE
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_paragraph_ngrams_hash
                ON paragraph_ngrams(paragraph_hash)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS paragraph_ngram_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            self._conn.commit()
            return True
        except sqlite3.OperationalError as e:
            logger.warning(f"paragraph ngram schema 创建失败: {e}")
            self._conn.rollback()
            return False

    def _get_paragraph_ngram_n_if_ready(self) -> Optional[int]:
        cur = self._conn.cursor()
        try:
            cur.execute("SELECT value FROM paragraph_ngram_meta WHERE key='ngram_n'")
            row = cur.fetchone()
            if not row or row[0] is None:
                return None
            return max(1, int(row[0]))
        except (sqlite3.OperationalError, TypeError, ValueError):
            return None

    def is_paragraph_ngram_ready(self, n: int = 2) -> bool:
        cur = self._conn.cursor()
        try:
            current_n = self._get_paragraph_ngram_n_if_ready()
            if current_n != max(1, int(n)):
                return False
            cur.execute(
                "SELECT COUNT(1) FROM paragraphs WHERE is_deleted IS NULL OR is_deleted = 0"
            )
            para_count = int(cur.fetchone()[0])
            cur.execute("SELECT value FROM paragraph_ngram_meta WHERE key='paragraph_count'")
            row = cur.fetchone()
            if not row or row[0] is None:
                return False
            indexed_docs = int(row[0])
            return para_count == indexed_docs
        except (sqlite3.OperationalError, TypeError, ValueError):
            return False

    def _set_paragraph_ngram_meta_value(self, key: str, value: str) -> None:
        self._conn.execute(
            """
            INSERT INTO paragraph_ngram_meta(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (str(key), str(value)),
        )

    def _adjust_paragraph_ngram_count(self, delta: int) -> None:
        if delta == 0:
            return
        cur = self._conn.cursor()
        try:
            cur.execute("SELECT value FROM paragraph_ngram_meta WHERE key='paragraph_count'")
            row = cur.fetchone()
            if not row or row[0] is None:
                return
            current = max(0, int(row[0]))
        except (sqlite3.OperationalError, TypeError, ValueError):
            return
        self._set_paragraph_ngram_meta_value(
            "paragraph_count", str(max(0, current + int(delta)))
        )

    def _upsert_paragraph_ngram_if_ready(
        self,
        paragraph_hash: str,
        content: str,
        *,
        count_delta: int = 0,
    ) -> bool:
        n = self._get_paragraph_ngram_n_if_ready()
        if n is None:
            return False
        cur = self._conn.cursor()
        cur.execute("DELETE FROM paragraph_ngrams WHERE paragraph_hash = ?", (paragraph_hash,))
        terms = list(dict.fromkeys(char_ngrams(content, n)))
        if terms:
            cur.executemany(
                "INSERT OR IGNORE INTO paragraph_ngrams(term, paragraph_hash) VALUES (?, ?)",
                [(term, paragraph_hash) for term in terms],
            )
        self._adjust_paragraph_ngram_count(count_delta)
        return True

    def _delete_paragraph_ngrams_if_ready(
        self,
        paragraph_hashes: Sequence[str],
        *,
        count_delta: int = 0,
    ) -> bool:
        hashes = [str(h) for h in paragraph_hashes if str(h or "").strip()]
        if not hashes:
            return False
        if self._get_paragraph_ngram_n_if_ready() is None:
            return False
        cur = self._conn.cursor()
        batch_size = 900
        for i in range(0, len(hashes), batch_size):
            batch = hashes[i : i + batch_size]
            placeholders = ",".join(["?"] * len(batch))
            cur.execute(
                f"DELETE FROM paragraph_ngrams WHERE paragraph_hash IN ({placeholders})",
                batch,
            )
        self._adjust_paragraph_ngram_count(count_delta)
        return True

    def ensure_paragraph_ngram_backfilled(self, n: int = 2) -> bool:
        cur = self._conn.cursor()
        n = max(1, int(n))
        started = time.perf_counter()
        try:
            cur.execute("SELECT value FROM paragraph_ngram_meta WHERE key='ngram_n'")
            row = cur.fetchone()
            current_n = int(row[0]) if row and row[0] is not None else None

            cur.execute(
                "SELECT COUNT(1) FROM paragraphs WHERE is_deleted IS NULL OR is_deleted = 0"
            )
            para_count = int(cur.fetchone()[0])
            cur.execute("SELECT value FROM paragraph_ngram_meta WHERE key='paragraph_count'")
            meta_row = cur.fetchone()
            if meta_row and meta_row[0] is not None:
                indexed_docs = int(meta_row[0])
            else:
                cur.execute("SELECT COUNT(DISTINCT paragraph_hash) FROM paragraph_ngrams")
                indexed_docs = int(cur.fetchone()[0])

            need_rebuild = (current_n != n) or (para_count != indexed_docs)
            if not need_rebuild:
                return True

            cur.execute("DELETE FROM paragraph_ngrams")
            cur.execute(
                """
                SELECT hash, content FROM paragraphs
                WHERE is_deleted IS NULL OR is_deleted = 0
                """
            )
            rows = cur.fetchall()

            batch: List[Tuple[str, str]] = []
            batch_size = 2000
            term_count = 0
            for row in rows:
                p_hash = str(row["hash"])
                terms = list(dict.fromkeys(char_ngrams(str(row["content"] or ""), n)))
                term_count += len(terms)
                for term in terms:
                    batch.append((term, p_hash))
                if len(batch) >= batch_size:
                    cur.executemany(
                        "INSERT OR IGNORE INTO paragraph_ngrams(term, paragraph_hash) VALUES (?, ?)",
                        batch,
                    )
                    batch.clear()
            if batch:
                cur.executemany(
                    "INSERT OR IGNORE INTO paragraph_ngrams(term, paragraph_hash) VALUES (?, ?)",
                    batch,
                )

            cur.execute(
                """
                INSERT INTO paragraph_ngram_meta(key, value) VALUES('ngram_n', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(n),),
            )
            cur.execute(
                """
                INSERT INTO paragraph_ngram_meta(key, value) VALUES('paragraph_count', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(para_count),),
            )
            cur.execute(
                """
                INSERT INTO paragraph_ngram_meta(key, value) VALUES('updated_at', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(datetime.now().timestamp()),),
            )
            self._conn.commit()
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                f"paragraph ngram 回填完成: n={n}, paragraphs={para_count}, "
                f"terms={term_count}, duration_ms={elapsed_ms:.2f}"
            )
            return True
        except Exception as e:
            logger.warning(f"paragraph ngram 回填失败: {e}")
            self._conn.rollback()
            return False

    def ngram_search_paragraphs(
        self,
        tokens: List[str],
        limit: int = 20,
        max_doc_len: int = 2000,
    ) -> List[Dict[str, Any]]:
        uniq = [t for t in dict.fromkeys([str(x).strip().lower() for x in tokens]) if t]
        if not uniq:
            return []
        cur = self._conn.cursor()
        placeholders = ",".join(["?"] * len(uniq))
        try:
            cur.execute(
                f"""
                SELECT p.hash, p.content, COUNT(*) AS hit_terms
                FROM paragraph_ngrams ng
                JOIN paragraphs p ON p.hash = ng.paragraph_hash
                WHERE ng.term IN ({placeholders})
                  AND (p.is_deleted IS NULL OR p.is_deleted = 0)
                GROUP BY p.hash, p.content
                ORDER BY hit_terms DESC
                LIMIT ?
                """,
                tuple(uniq + [max(1, int(limit))]),
            )
            rows = cur.fetchall()
            out: List[Dict[str, Any]] = []
            token_count = max(1, len(uniq))
            for row in rows:
                hit_terms = int(row["hit_terms"])
                score = float(hit_terms / token_count)
                content = str(row["content"] or "")
                if max_doc_len > 0:
                    content = content[:max_doc_len]
                out.append(
                    {
                        "hash": row["hash"],
                        "content": content,
                        "bm25_score": -score,
                        "fallback_score": score,
                    }
                )
            return out
        except sqlite3.OperationalError as e:
            logger.warning(f"ngram 倒排查询失败: {e}")
            return []

    # ==================================================================
    # 软删除 / GC
    # ==================================================================

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
                UPDATE paragraphs
                SET is_deleted = 1, deleted_at = ?
                WHERE is_deleted = 0 AND hash IN ({placeholders})
                """,
                [now] + batch,
            )
            changed = cursor.rowcount
            count += changed
            if changed > 0:
                self._delete_paragraph_ngrams_if_ready(batch, count_delta=-changed)
                for paragraph_hash in batch:
                    self.fts_delete_tokenized_paragraph(str(paragraph_hash))
        self._conn.commit()
        if count > 0:
            logger.info(f"软删除标记 (paragraphs): {count} 项")
        return count

    def sweep_deleted_items(self, grace_period_seconds: float) -> List[Tuple[str, str]]:
        now = datetime.now().timestamp()
        cutoff = now - grace_period_seconds
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT hash, '' as name FROM paragraphs
            WHERE is_deleted = 1 AND deleted_at < ?
            """,
            (cutoff,),
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def physically_delete_paragraphs(self, hashes: List[str]) -> int:
        if not hashes:
            return 0
        active_delete_count = 0
        batch_size = 900
        for i in range(0, len(hashes), batch_size):
            batch = hashes[i : i + batch_size]
            placeholders = ",".join(["?"] * len(batch))
            cursor = self._conn.cursor()
            cursor.execute(
                f"""
                SELECT hash FROM paragraphs
                WHERE (is_deleted IS NULL OR is_deleted = 0)
                  AND hash IN ({placeholders})
                """,
                batch,
            )
            active_batch = [str(row["hash"]) for row in cursor.fetchall()]
            active_delete_count += len(active_batch)
        self._delete_paragraph_ngrams_if_ready(hashes, count_delta=-active_delete_count)
        for paragraph_hash in hashes:
            self.fts_delete_tokenized_paragraph(str(paragraph_hash))

        count = 0
        for i in range(0, len(hashes), batch_size):
            batch = hashes[i : i + batch_size]
            placeholders = ",".join(["?"] * len(batch))
            cursor = self._conn.cursor()
            cursor.execute(f"DELETE FROM paragraphs WHERE hash IN ({placeholders})", batch)
            count += cursor.rowcount
        if count > 0:
            self._refresh_paragraph_tokenized_fts_meta()
        self._conn.commit()
        return count

    def get_paragraph_gc_candidates(self, retention_seconds: float) -> List[str]:
        now = datetime.now().timestamp()
        cutoff = now - retention_seconds
        query = """
            SELECT p.hash FROM paragraphs p
            LEFT JOIN paragraph_relations pr ON p.hash = pr.paragraph_hash
            LEFT JOIN paragraph_entities pe ON p.hash = pe.paragraph_hash
            WHERE p.is_deleted = 0
            AND (p.created_at IS NULL OR p.created_at < ?)
            AND pr.relation_hash IS NULL
            AND pe.entity_hash IS NULL
        """
        cursor = self._conn.cursor()
        cursor.execute(query, (cutoff,))
        return [row[0] for row in cursor.fetchall()]

    def revive_if_deleted(self, paragraph_hashes: List[str]) -> int:
        count = 0
        if paragraph_hashes:
            batch_size = 900
            for i in range(0, len(paragraph_hashes), batch_size):
                batch = paragraph_hashes[i : i + batch_size]
                placeholders = ",".join(["?"] * len(batch))
                cursor = self._conn.cursor()
                cursor.execute(
                    f"""
                    SELECT hash, content FROM paragraphs
                    WHERE is_deleted = 1 AND hash IN ({placeholders})
                    """,
                    batch,
                )
                revive_rows = cursor.fetchall()
                cursor.execute(
                    f"""
                    UPDATE paragraphs
                    SET is_deleted = 0, deleted_at = NULL
                    WHERE is_deleted = 1 AND hash IN ({placeholders})
                    """,
                    batch,
                )
                changed = cursor.rowcount
                count += changed
                if changed > 0:
                    for row in revive_rows:
                        self._upsert_paragraph_ngram_if_ready(
                            str(row["hash"]),
                            str(row["content"] or ""),
                            count_delta=1,
                        )
                        self.fts_upsert_tokenized_paragraph(str(row["hash"]))
        if count > 0:
            self._conn.commit()
            logger.info(f"自动复活: {count} 项段落")
        return count

    def restore_paragraph_by_hash(self, paragraph_hash: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT content FROM paragraphs WHERE hash=? AND is_deleted=1",
            (str(paragraph_hash),),
        )
        row = cursor.fetchone()
        cursor.execute(
            "UPDATE paragraphs SET is_deleted=0, deleted_at=NULL WHERE hash=? AND is_deleted=1",
            (str(paragraph_hash),),
        )
        changed = cursor.rowcount > 0 and row is not None
        if changed:
            self._upsert_paragraph_ngram_if_ready(
                str(paragraph_hash), str(row["content"] or ""), count_delta=1
            )
            self.fts_upsert_tokenized_paragraph(str(paragraph_hash))
            self._conn.commit()
        return changed
