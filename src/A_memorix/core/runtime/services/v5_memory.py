from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from ...storage import MetadataStore


class V5MemoryService:

    def __init__(
        self,
        *,
        metadata_store: MetadataStore,
        cfg: Callable[[str, Any], Any],
        resolve_relation_hashes: Callable[[str], List[str]],
        resolve_deleted_relation_hashes: Callable[[str], List[str]],
        rebuild_graph_from_metadata: Callable[[], Dict[str, int]],
        persist_callback: Callable[[], None],
        last_maintenance_at_getter: Callable[[], Optional[float]],
        last_maintenance_at_setter: Callable[[float], None],
    ) -> None:
        self._metadata_store = metadata_store
        self._cfg = cfg
        self._resolve_relation_hashes = resolve_relation_hashes
        self._resolve_deleted_relation_hashes = resolve_deleted_relation_hashes
        self._rebuild_graph_from_metadata = rebuild_graph_from_metadata
        self._persist = persist_callback
        self._get_last_maintenance_at = last_maintenance_at_getter
        self._set_last_maintenance_at = last_maintenance_at_setter

    def memory_v5_status(self, *, target: str = "", limit: int = 50) -> Dict[str, Any]:
        now = time.time()
        summary = self._metadata_store.get_memory_status_summary(now)
        payload: Dict[str, Any] = {
            "success": True,
            **summary,
            "config": {
                "half_life_hours": float(self._cfg("memory.half_life_hours", 24.0) or 24.0),
                "base_decay_interval_hours": float(self._cfg("memory.base_decay_interval_hours", 1.0) or 1.0),
                "prune_threshold": float(self._cfg("memory.prune_threshold", 0.1) or 0.1),
                "freeze_duration_hours": float(self._cfg("memory.freeze_duration_hours", 24.0) or 24.0),
            },
            "last_maintenance_at": self._get_last_maintenance_at(),
        }
        token = str(target or "").strip()
        if not token:
            return payload

        active_hashes = self._resolve_relation_hashes(token)[:limit]
        deleted_hashes = self._resolve_deleted_relation_hashes(token)[:limit]
        active_statuses = self._metadata_store.get_relation_status_batch(active_hashes)
        items: List[Dict[str, Any]] = []
        for hash_value in active_hashes:
            relation = self._metadata_store.get_relation(hash_value) or {}
            status = active_statuses.get(hash_value, {})
            items.append(
                {
                    "hash": hash_value,
                    "subject": str(relation.get("subject", "") or ""),
                    "predicate": str(relation.get("predicate", "") or ""),
                    "object": str(relation.get("object", "") or ""),
                    "state": "inactive" if bool(status.get("is_inactive")) else "active",
                    "is_pinned": bool(status.get("is_pinned", False)),
                    "temp_protected": bool(float(status.get("protected_until") or 0.0) > now),
                    "protected_until": status.get("protected_until"),
                    "last_reinforced": status.get("last_reinforced"),
                    "weight": float(status.get("weight", relation.get("confidence", 0.0)) or 0.0),
                }
            )
        for hash_value in deleted_hashes:
            relation = self._metadata_store.get_deleted_relation(hash_value) or {}
            items.append(
                {
                    "hash": hash_value,
                    "subject": str(relation.get("subject", "") or ""),
                    "predicate": str(relation.get("predicate", "") or ""),
                    "object": str(relation.get("object", "") or ""),
                    "state": "deleted",
                    "is_pinned": bool(relation.get("is_pinned", False)),
                    "temp_protected": False,
                    "protected_until": relation.get("protected_until"),
                    "last_reinforced": relation.get("last_reinforced"),
                    "weight": float(relation.get("confidence", 0.0) or 0.0),
                    "deleted_at": relation.get("deleted_at"),
                }
            )
        payload["items"] = items[:limit]
        payload["count"] = len(payload["items"])
        payload["target"] = token
        return payload

    def adjust_relation_confidence(self, hashes: List[str], *, delta: float) -> Dict[str, float]:
        normalized = [str(item or "").strip() for item in hashes if str(item or "").strip()]
        if not normalized:
            return {}
        conn = self._metadata_store.get_connection()
        cursor = conn.cursor()
        chunk_size = 200
        for index in range(0, len(normalized), chunk_size):
            chunk = normalized[index : index + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            cursor.execute(
                f"""
                UPDATE relations
                SET confidence = MAX(0.0, COALESCE(confidence, 0.0) + ?)
                WHERE hash IN ({placeholders})
                """,
                tuple([float(delta)] + chunk),
            )
        conn.commit()
        statuses = self._metadata_store.get_relation_status_batch(normalized)
        return {hash_value: float((statuses.get(hash_value) or {}).get("weight", 0.0) or 0.0) for hash_value in normalized}

    def apply_v5_relation_action(self, *, action: str, hashes: List[str], strength: float = 1.0) -> Dict[str, Any]:
        act = str(action or "").strip().lower()
        normalized = [str(item or "").strip() for item in hashes if str(item or "").strip()]
        if not normalized:
            return {"success": False, "error": "未命中可维护关系"}

        now = time.time()
        strength_value = max(0.1, float(strength or 1.0))
        prune_threshold = max(0.0, float(self._cfg("memory.prune_threshold", 0.1) or 0.1))
        detail = ""

        if act == "reinforce":
            weights = self.adjust_relation_confidence(normalized, delta=0.5 * strength_value)
            protect_hours = max(1.0, 24.0 * strength_value)
            self._metadata_store.reinforce_relations(normalized)
            self._metadata_store.mark_relations_active(normalized, boost_weight=max(prune_threshold, 0.1))
            self._metadata_store.update_relations_protection(
                normalized,
                protected_until=now + protect_hours * 3600.0,
                last_reinforced=now,
            )
            detail = f"reinforce {len(normalized)} 条关系"
        elif act == "weaken":
            weights = self.adjust_relation_confidence(normalized, delta=-0.5 * strength_value)
            to_freeze = [hash_value for hash_value, weight in weights.items() if weight <= prune_threshold]
            if to_freeze:
                self._metadata_store.mark_relations_inactive(to_freeze, inactive_since=now)
            detail = f"weaken {len(normalized)} 条关系"
        elif act == "remember_forever":
            self._metadata_store.mark_relations_active(normalized, boost_weight=max(prune_threshold, 0.1))
            self._metadata_store.update_relations_protection(normalized, protected_until=0.0, is_pinned=True)
            weights = {hash_value: float((self._metadata_store.get_relation_status_batch([hash_value]).get(hash_value) or {}).get("weight", 0.0) or 0.0) for hash_value in normalized}
            detail = f"remember_forever {len(normalized)} 条关系"
        elif act == "forget":
            weights = self.adjust_relation_confidence(normalized, delta=-2.0 * strength_value)
            self._metadata_store.update_relations_protection(normalized, protected_until=0.0, is_pinned=False)
            self._metadata_store.mark_relations_inactive(normalized, inactive_since=now)
            detail = f"forget {len(normalized)} 条关系"
        else:
            return {"success": False, "error": f"不支持的 V5 动作: {act}"}

        self._rebuild_graph_from_metadata()
        self._set_last_maintenance_at(now)
        self._persist()
        statuses = self._metadata_store.get_relation_status_batch(normalized)
        return {
            "success": True,
            "detail": detail,
            "hashes": normalized,
            "count": len(normalized),
            "weights": weights,
            "statuses": statuses,
        }