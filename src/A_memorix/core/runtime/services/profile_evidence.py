from __future__ import annotations

from typing import Any, Callable, Coroutine, Dict, List, Optional, Sequence

from ...storage import MetadataStore
from ...utils.metadata import coerce_metadata_dict
from src.common.logger import get_logger

logger = get_logger("A_memorix.profile_evidence_service")


class ProfileEvidenceService:
    """Profile 证据域服务 — 从 SDKMemoryKernel 提取的画像证据构建/查询/纠错逻辑。"""

    def __init__(
        self,
        *,
        metadata_store: MetadataStore,
        person_profile_service: Any,
        tokens: Callable[..., List[str]],
        trim_text: Callable[[str, int], str],
        query_person_profile_with_feedback_refresh: Callable[..., Coroutine[Any, Any, Dict[str, Any]]],
        execute_delete_action: Callable[..., Coroutine[Any, Any, Dict[str, Any]]],
        invalidate_import_manifest_for_sources: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        self.metadata_store = metadata_store
        self._person_profile_service = person_profile_service
        self._tokens = tokens
        self._trim_text = trim_text
        self._query_person_profile_with_feedback_refresh = query_person_profile_with_feedback_refresh
        self._execute_delete_action = execute_delete_action
        self._invalidate_import_manifest_for_sources = invalidate_import_manifest_for_sources

    # ── 静态工具 ──────────────────────────────────────────────

    @staticmethod
    def _profile_evidence_type_from_source(source: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        meta = metadata if isinstance(metadata, dict) else {}
        source_type = str(meta.get("source_type", "") or "").strip()
        if source_type in {"person_fact", "chat_summary"}:
            return source_type
        token = str(source or meta.get("source", "") or "").strip()
        if token.startswith("person_fact:"):
            return "person_fact"
        if token.startswith("chat_summary:"):
            return "chat_summary"
        return "paragraph"

    @staticmethod
    def _profile_relation_content(relation: Dict[str, Any]) -> str:
        subject = str(relation.get("subject", "") or "").strip()
        predicate = str(relation.get("predicate", "") or "").strip()
        obj = str(relation.get("object", "") or "").strip()
        if subject and predicate and obj:
            return f"{subject} -[{predicate}]-> {obj}"
        return " ".join(item for item in (subject, predicate, obj) if item).strip()

    # ── 证据项构建 ────────────────────────────────────────────

    def _build_profile_relation_evidence_item(self, relation: Dict[str, Any], *, index: int) -> Dict[str, Any]:
        relation_hash = str(relation.get("hash", "") or "").strip()
        metadata = coerce_metadata_dict(relation.get("metadata"))
        return {
            "evidence_key": f"relation:{relation_hash or index}",
            "evidence_type": "relation",
            "hash": relation_hash,
            "content": self._profile_relation_content(relation),
            "source": str(relation.get("source_paragraph", "") or metadata.get("source", "") or "").strip(),
            "source_type": "relation",
            "metadata": metadata,
            "score": None,
            "confidence": relation.get("confidence"),
            "correction_mode": "delete_relation",
            "deletable": bool(relation_hash),
            "not_deletable_reason": "" if relation_hash else "缺少关系 hash",
            "raw": relation,
        }

    def _build_profile_paragraph_evidence_item(
        self,
        item: Dict[str, Any],
        *,
        index: int,
        fallback_hash: str = "",
    ) -> Dict[str, Any]:
        hash_value = str(item.get("hash", "") or fallback_hash or "").strip()
        metadata = coerce_metadata_dict(item.get("metadata"))
        source = str(item.get("source", "") or metadata.get("source", "") or "").strip()
        content = str(item.get("content", "") or "").strip()
        source_type = self._profile_evidence_type_from_source(source, metadata)
        is_deleted = False
        if hash_value:
            try:
                paragraph = self.metadata_store.get_paragraph(hash_value) if self.metadata_store else None
            except Exception:
                paragraph = None
            if isinstance(paragraph, dict):
                paragraph_metadata = coerce_metadata_dict(paragraph.get("metadata"))
                metadata = {**paragraph_metadata, **metadata}
                source = source or str(paragraph.get("source", "") or "").strip()
                content = content or str(paragraph.get("content", "") or "").strip()
                source_type = self._profile_evidence_type_from_source(source, metadata)
                is_deleted = bool(paragraph.get("is_deleted", 0))
        return {
            "evidence_key": f"{source_type}:{hash_value or index}",
            "evidence_type": source_type,
            "hash": hash_value,
            "content": self._trim_text(content, 260),
            "source": source,
            "source_type": source_type,
            "metadata": metadata,
            "score": item.get("score"),
            "confidence": None,
            "correction_mode": "delete_paragraph",
            "deletable": bool(hash_value) and not is_deleted,
            "not_deletable_reason": "" if hash_value and not is_deleted else ("证据已删除" if is_deleted else "缺少段落 hash"),
            "raw": item,
        }

    def _build_profile_evidence_items(self, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        assert self.metadata_store is not None
        evidence: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def append(item: Dict[str, Any]) -> None:
            evidence_type = str(item.get("evidence_type", "") or "").strip()
            hash_value = str(item.get("hash", "") or "").strip()
            key = (evidence_type, hash_value or str(item.get("evidence_key", "") or ""))
            if not key[0] or key in seen:
                return
            seen.add(key)
            evidence.append(item)

        for index, relation in enumerate(profile.get("relation_edges") or [], start=1):
            if isinstance(relation, dict):
                append(self._build_profile_relation_evidence_item(relation, index=index))

        for index, item in enumerate(profile.get("vector_evidence") or [], start=1):
            if isinstance(item, dict):
                append(self._build_profile_paragraph_evidence_item(item, index=index))

        for index, hash_value in enumerate(self._tokens(profile.get("evidence_ids")), start=1):
            if any(str(item.get("hash", "") or "").strip() == hash_value for item in evidence):
                continue
            paragraph = self.metadata_store.get_paragraph(hash_value)
            if isinstance(paragraph, dict):
                append(
                    self._build_profile_paragraph_evidence_item(
                        {
                            "hash": hash_value,
                            "content": str(paragraph.get("content", "") or ""),
                            "source": str(paragraph.get("source", "") or ""),
                            "metadata": coerce_metadata_dict(paragraph.get("metadata")),
                        },
                        index=index,
                    )
                )
                continue
            relation = self.metadata_store.get_relation(hash_value)
            if isinstance(relation, dict):
                append(self._build_profile_relation_evidence_item(relation, index=index))

        return evidence

    # ── 证据响应构建 ──────────────────────────────────────────

    def _profile_evidence_response(self, profile: Dict[str, Any], *, requested_person_id: str, limit: int) -> Dict[str, Any]:
        if not bool(profile.get("success")):
            return {
                "success": False,
                "error": str(profile.get("error", "") or "人物画像查询失败"),
                "person_id": str(profile.get("person_id", "") or requested_person_id),
                "evidence": [],
            }
        evidence = self._build_profile_evidence_items(profile)
        return {
            "success": True,
            "person_id": str(profile.get("person_id", "") or requested_person_id),
            "person_name": str(profile.get("person_name", "") or ""),
            "profile_text": str(profile.get("profile_text", "") or ""),
            "auto_profile_text": str(profile.get("auto_profile_text", "") or profile.get("profile_text", "") or ""),
            "profile_version": profile.get("profile_version"),
            "updated_at": profile.get("updated_at"),
            "expires_at": profile.get("expires_at"),
            "profile_source": str(profile.get("profile_source", "") or "auto_snapshot"),
            "has_manual_override": bool(profile.get("has_manual_override", False)),
            "manual_override_text": str(profile.get("manual_override_text", "") or ""),
            "evidence": evidence[: max(1, int(limit or 12))],
            "evidence_count": len(evidence),
            "raw_profile": profile,
        }

    # ── 管理接口 ──────────────────────────────────────────────

    async def profile_evidence_admin(
        self,
        *,
        person_id: str = "",
        person_keyword: str = "",
        limit: int = 12,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        profile = await self._query_person_profile_with_feedback_refresh(
            person_id=person_id,
            person_keyword=person_keyword,
            limit=max(1, int(limit or 12)),
            force_refresh=force_refresh,
            source_note="sdk_memory_kernel.memory_profile_admin.evidence",
        )
        requested_person_id = str(profile.get("person_id", "") or person_id or "").strip() if isinstance(profile, dict) else person_id
        return self._profile_evidence_response(profile if isinstance(profile, dict) else {}, requested_person_id=requested_person_id, limit=limit)

    async def profile_correct_evidence_admin(
        self,
        *,
        person_id: str = "",
        person_keyword: str = "",
        evidence_type: str,
        hash_value: str,
        requested_by: str = "webui",
        reason: str = "profile_evidence_correction",
        refresh: bool = True,
        limit: int = 12,
    ) -> Dict[str, Any]:
        normalized_type = str(evidence_type or "").strip().lower()
        normalized_hash = str(hash_value or "").strip()
        if normalized_type not in {"relation", "paragraph", "person_fact", "chat_summary"}:
            return {"success": False, "error": "不支持的画像证据类型"}
        if not normalized_hash:
            return {"success": False, "error": "画像证据 hash 不能为空"}

        evidence_payload = await self.profile_evidence_admin(
            person_id=person_id,
            person_keyword=person_keyword,
            limit=max(50, int(limit or 12)),
            force_refresh=False,
        )
        if not bool(evidence_payload.get("success")):
            return evidence_payload
        matched = None
        for item in evidence_payload.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("hash", "") or "").strip() != normalized_hash:
                continue
            item_type = str(item.get("evidence_type", "") or "").strip().lower()
            if normalized_type == item_type or (normalized_type == "paragraph" and item_type in {"person_fact", "chat_summary"}):
                matched = item
                break
        if matched is None:
            return {"success": False, "error": "当前画像证据中未找到目标 hash"}
        if not bool(matched.get("deletable", False)):
            return {
                "success": False,
                "error": str(matched.get("not_deletable_reason", "") or "该画像证据不可纠错"),
                "evidence": matched,
            }

        delete_mode = "relation" if normalized_type == "relation" else "paragraph"
        delete_result = await self._execute_delete_action(
            mode=delete_mode,
            selector={"hashes": [normalized_hash]},
            requested_by=requested_by or "webui",
            reason=reason or "profile_evidence_correction",
        )
        if bool(delete_result.get("success")):
            await self._invalidate_import_manifest_for_sources(delete_result)

        refreshed_profile: Dict[str, Any] = {}
        refreshed_evidence: Dict[str, Any] = {}
        if refresh and bool(delete_result.get("success")):
            refreshed_profile = await self._person_profile_service.query_person_profile(
                person_id=str(evidence_payload.get("person_id", "") or person_id),
                top_k=max(4, int(limit or 12)),
                force_refresh=True,
                source_note="sdk_memory_kernel.memory_profile_admin.correct_evidence",
            )
            refreshed_evidence = self._profile_evidence_response(
                refreshed_profile if isinstance(refreshed_profile, dict) else {},
                requested_person_id=str(evidence_payload.get("person_id", "") or person_id),
                limit=limit,
            )

        return {
            "success": bool(delete_result.get("success")),
            "person_id": str(evidence_payload.get("person_id", "") or person_id),
            "evidence": matched,
            "delete_result": delete_result,
            "operation_id": str(delete_result.get("operation_id", "") or ""),
            "refreshed_profile": refreshed_profile,
            "refreshed_evidence": refreshed_evidence,
            "error": str(delete_result.get("error", "") or ""),
        }