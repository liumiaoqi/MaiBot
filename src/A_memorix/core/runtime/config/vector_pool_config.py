from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VectorPoolConfig:
    """向量池配置 — 一次性从 kernel config dict 读取，替代多处 _cfg 调用。"""

    mode: str = "dual"
    config_enabled: bool = True
    embedding_fallback_enabled: bool = True
    allow_metadata_only_write: bool = True
    embedding_probe_interval_seconds: float = 180.0
    paragraph_vector_backfill_enabled: bool = True
    paragraph_vector_backfill_interval_seconds: float = 60.0
    paragraph_vector_backfill_batch_size: int = 64
    paragraph_vector_backfill_max_retry: int = 5

    @classmethod
    def from_config(cls, config: dict) -> VectorPoolConfig:
        mode = str(config.get("retrieval", {}).get("vector_pools", {}).get("mode", "dual") or "dual").strip().lower()
        if mode not in {"single", "dual"}:
            mode = "single"
        return cls(
            mode=mode,
            config_enabled=(mode == "dual"),
            embedding_fallback_enabled=bool(config.get("embedding", {}).get("fallback", {}).get("enabled", True)),
            allow_metadata_only_write=bool(config.get("embedding", {}).get("fallback", {}).get("allow_metadata_only_write", True)),
            embedding_probe_interval_seconds=max(10.0, float(config.get("embedding", {}).get("fallback", {}).get("probe_interval_seconds", 180) or 180)),
            paragraph_vector_backfill_enabled=bool(config.get("embedding", {}).get("paragraph_vector_backfill", {}).get("enabled", True)),
            paragraph_vector_backfill_interval_seconds=max(10.0, float(config.get("embedding", {}).get("paragraph_vector_backfill", {}).get("interval_seconds", 60) or 60)),
            paragraph_vector_backfill_batch_size=max(1, int(config.get("embedding", {}).get("paragraph_vector_backfill", {}).get("batch_size", 64) or 64)),
            paragraph_vector_backfill_max_retry=max(1, int(config.get("embedding", {}).get("paragraph_vector_backfill", {}).get("max_retry", 5) or 5)),
        )