from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import asyncio
import time

from src.common.logger import get_logger

logger = get_logger("a_memorix.services.person_profile_facade")


class PersonProfileFacade:
    """人物画像查询、刷新、队列管理。"""

    def __init__(
        self,
        *,
        cfg: Callable[[str, Any], Any],
        metadata_store_getter: Callable[[], Any],
        person_profile_service_getter: Callable[[], Any],
        feedback_correction_service_getter: Callable[[], Any],
        hit_filter_service_getter: Callable[[], Any],
        active_person_timestamps: Dict[str, float],
        background_scheduler: Any,
        initialize: Callable[[], Any],
    ) -> None:
        self._cfg = cfg
        self._get_metadata_store = metadata_store_getter
        self._get_person_profile_service = person_profile_service_getter
        self._get_feedback_correction_service = feedback_correction_service_getter
        self._get_hit_filter_service = hit_filter_service_getter
        self._active_person_timestamps = active_person_timestamps
        self._scheduler = background_scheduler
        self._initialize = initialize

    @staticmethod
    def empty_person_profile_response(*, person_id: str = "", person_name: str = "") -> Dict[str, Any]:
        return {
            "summary": "",
            "traits": [],
            "evidence": [],
            "person_id": str(person_id or "").strip(),
            "person_name": str(person_name or "").strip(),
            "profile_source": "",
            "has_manual_override": False,
        }

    def build_person_profile_response(
        self,
        profile: Dict[str, Any],
        *,
        requested_person_id: str,
        limit: int,
    ) -> Dict[str, Any]:
        metadata_store = self._get_metadata_store()
        assert metadata_store is not None
        if not bool(profile.get("success")):
            return self.empty_person_profile_response(
                person_id=str(profile.get("person_id", "") or requested_person_id),
                person_name=str(profile.get("person_name", "") or ""),
            )

        evidence: List[Dict[str, Any]] = []
        evidence_limit = max(1, int(limit or 10))
        for hash_value in profile.get("evidence_ids", [])[:evidence_limit]:
            paragraph = metadata_store.get_paragraph(hash_value)
            if paragraph is not None:
                evidence.append(
                    {
                        "hash": hash_value,
                        "content": str(paragraph.get("content", "") or "")[:220],
                        "metadata": paragraph.get("metadata", {}) or {},
                        "type": "paragraph",
                    }
                )
                continue

            relation = metadata_store.get_relation(hash_value)
            if relation is not None:
                evidence.append(
                    {
                        "hash": hash_value,
                        "content": " ".join(
                            [
                                str(relation.get("subject", "") or "").strip(),
                                str(relation.get("predicate", "") or "").strip(),
                                str(relation.get("object", "") or "").strip(),
                            ]
                        ).strip(),
                        "metadata": {
                            "confidence": relation.get("confidence"),
                            "source_paragraph": relation.get("source_paragraph"),
                        },
                        "type": "relation",
                    }
                )

        hit_filter = self._get_hit_filter_service()
        evidence = hit_filter.filter_user_visible_hits(evidence)
        text = str(profile.get("profile_text", "") or "").strip()
        traits = [line.strip("- ").strip() for line in text.splitlines() if line.strip()][:8]
        return {
            "summary": text,
            "traits": traits,
            "evidence": evidence,
            "person_id": str(profile.get("person_id", "") or requested_person_id),
            "person_name": str(profile.get("person_name", "") or ""),
            "profile_source": str(profile.get("profile_source", "") or "auto_snapshot"),
            "has_manual_override": bool(profile.get("has_manual_override", False)),
        }

    async def get_person_profile(self, *, person_id: str, chat_id: str = "", limit: int = 10) -> Dict[str, Any]:
        del chat_id
        await self._initialize()
        assert self._get_metadata_store() is not None
        assert self._get_person_profile_service() is not None
        self.mark_person_active(person_id)
        fcs = self._get_feedback_correction_service()
        profile = await fcs._query_person_profile_with_feedback_refresh(
            person_id=person_id,
            limit=max(4, int(limit or 10)),
            source_note="person_profile_facade.get_person_profile",
        )
        return self.build_person_profile_response(profile, requested_person_id=person_id, limit=limit)

    async def refresh_person_profile(self, person_id: str, limit: int = 10, *, mark_active: bool = True) -> Dict[str, Any]:
        await self._initialize()
        pps = self._get_person_profile_service()
        assert pps
        if mark_active:
            self.mark_person_active(person_id)
        profile = await pps.query_person_profile(
            person_id=person_id,
            top_k=max(4, int(limit or 10)),
            force_refresh=True,
            source_note="person_profile_facade.refresh_person_profile",
        )
        return profile if isinstance(profile, dict) else {}

    def mark_person_active(self, person_id: str) -> None:
        token = str(person_id or "").strip()
        if not token:
            return
        self._active_person_timestamps[token] = time.time()

    def _queue_interval_seconds(self) -> float:
        return max(1.0, float(self._cfg("person_profile.refresh_queue_interval_seconds", 60) or 60))

    def _queue_batch_size(self) -> int:
        return max(1, int(self._cfg("person_profile.refresh_queue_batch_size", 10) or 10))

    def _debounce_seconds(self) -> float:
        return max(0.0, float(self._cfg("person_profile.refresh_debounce_seconds", 120) or 0))

    def _retry_backoff_seconds(self) -> float:
        return max(0.0, float(self._cfg("person_profile.refresh_retry_backoff_seconds", 300) or 0))

    def _max_retry(self) -> int:
        return max(0, int(self._cfg("person_profile.max_retry", 3) or 0))

    def enqueue_person_profile_refresh(self, person_id: str, *, reason: str = "") -> bool:
        metadata_store = self._get_metadata_store()
        if metadata_store is None or not bool(self._cfg("person_profile.enabled", True)):
            return False
        payload = metadata_store.enqueue_person_profile_refresh(
            person_id=person_id,
            reason=str(reason or "").strip() or "memory_ingest",
        )
        return isinstance(payload, dict)

    def has_pending_person_profile_refresh(self, person_id: str) -> bool:
        metadata_store = self._get_metadata_store()
        if metadata_store is None:
            return False
        request = metadata_store.get_person_profile_refresh_request(person_id)
        if not isinstance(request, dict):
            return False
        status = str(request.get("status", "") or "").strip().lower()
        if status in {"pending", "running"}:
            return True
        if status != "failed":
            return False
        return int(request.get("retry_count", 0) or 0) < self._max_retry()

    async def process_person_profile_refresh_queue_batch(self, *, limit: int) -> Dict[str, Any]:
        fcs = self._get_feedback_correction_service()
        return await fcs._process_feedback_profile_refresh_batch(
            limit=limit,
            debounce_seconds=self._debounce_seconds(),
            retry_backoff_seconds=self._retry_backoff_seconds(),
            max_retry=self._max_retry(),
        )

    async def person_profile_refresh_loop(self) -> None:
        try:
            while not self._scheduler.stopping:
                interval_minutes = max(1.0, float(self._cfg("person_profile.refresh_interval_minutes", 30) or 30))
                await asyncio.sleep(max(60.0, interval_minutes * 60.0))
                if self._scheduler.stopping:
                    break
                if not bool(self._cfg("person_profile.enabled", True)):
                    continue
                active_window_hours = max(1.0, float(self._cfg("person_profile.active_window_hours", 72.0) or 72.0))
                max_refresh = max(1, int(self._cfg("person_profile.max_refresh_per_cycle", 50) or 50))
                cutoff = time.time() - active_window_hours * 3600.0
                candidates = [
                    person_id
                    for person_id, seen_at in sorted(
                        self._active_person_timestamps.items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )
                    if seen_at >= cutoff
                ][:max_refresh]
                for person_id in candidates:
                    try:
                        if self.has_pending_person_profile_refresh(person_id):
                            continue
                        await self.refresh_person_profile(person_id, limit=max(4, int(self._cfg("person_profile.top_k_evidence", 12) or 12)), mark_active=False)
                    except Exception as exc:
                        logger.warning(f"刷新人物画像失败: {exc}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"person_profile_refresh loop 异常: {exc}")

    async def person_profile_refresh_queue_loop(self) -> None:
        try:
            while not self._scheduler.stopping:
                await asyncio.sleep(self._queue_interval_seconds())
                if self._scheduler.stopping:
                    break
                if not bool(self._cfg("person_profile.enabled", True)):
                    continue
                await self.process_person_profile_refresh_queue_batch(
                    limit=self._queue_batch_size()
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"person_profile_refresh_queue loop 异常: {exc}")