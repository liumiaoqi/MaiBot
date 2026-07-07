from __future__ import annotations

import time
from typing import Any, Dict, Optional

from src.common.logger import get_logger
from src.A_memorix.core.runtime.config.vector_pool_config import VectorPoolConfig

logger = get_logger("a_memorix.services.embedding_health")


class EmbeddingHealthService:
    """Embedding 降级状态管理 — 从 SDKMemoryKernel 提取。"""

    def __init__(
        self,
        *,
        vector_pool_config: VectorPoolConfig,
    ) -> None:
        self._config = vector_pool_config
        self._state: Dict[str, Any] = {
            "active": False,
            "reason": "",
            "since": None,
            "last_check": None,
        }
        self._runtime_self_check_report: Dict[str, Any] = {}

    @property
    def is_degraded(self) -> bool:
        return bool(self._state.get("active", False))

    @property
    def config(self) -> VectorPoolConfig:
        return self._config

    def snapshot(self) -> Dict[str, Any]:
        return {
            "active": bool(self._state.get("active", False)),
            "reason": str(self._state.get("reason", "") or ""),
            "since": self._state.get("since"),
            "last_check": self._state.get("last_check"),
        }

    def set_degraded(self, *, active: bool, reason: str = "", checked_at: Optional[float] = None) -> None:
        now = float(checked_at or time.time())
        prev = self.snapshot()
        if active:
            since = prev.get("since") if bool(prev.get("active", False)) else now
            self._state = {
                "active": True,
                "reason": str(reason or "").strip(),
                "since": since,
                "last_check": now,
            }
        else:
            self._state = {
                "active": False,
                "reason": "",
                "since": None,
                "last_check": now,
            }
        if bool(prev.get("active", False)) != bool(active):
            if active:
                logger.warning(
                    "embedding 进入降级态，将启用 sparse-only 与 metadata-only 写入回退: "
                    f"reason={self._state.get('reason', '')}"
                )
            else:
                logger.info("embedding 已恢复，退出降级态")

    def apply_runtime_sparse_mode(self, retriever: Any) -> None:
        if retriever is None:
            return
        setter = getattr(retriever, "set_runtime_sparse_only", None)
        if not callable(setter):
            return
        try:
            setter(self.is_degraded)
        except Exception as exc:
            logger.warning(f"设置 retriever sparse-only 运行时状态失败: {exc}")

    def mark_startup_self_check_deferred(
        self,
        *,
        configured_dimension: int,
        requested_dimension: int,
        vector_store_dimension: int,
    ) -> None:
        degraded = self.snapshot()
        is_degraded = bool(degraded.get("active", False))
        self._runtime_self_check_report = {
            "ok": not is_degraded,
            "code": "startup_self_check_deferred_degraded" if is_degraded else "startup_self_check_deferred",
            "message": str(degraded.get("reason", "") or "").strip()
            or "启动阶段已跳过真实 embedding encode 自检，将由后台探测或手动 self_check 执行",
            "configured_dimension": configured_dimension,
            "requested_dimension": requested_dimension,
            "vector_store_dimension": vector_store_dimension,
            "detected_dimension": requested_dimension,
            "encoded_dimension": 0,
            "elapsed_ms": 0.0,
            "sample_text": "",
            "checked_at": None,
        }

    def is_startup_self_check_deferred(self) -> bool:
        code = str(self._runtime_self_check_report.get("code", "") or "").strip()
        return code in {"startup_self_check_deferred", "startup_self_check_deferred_degraded"}

    @property
    def runtime_self_check_report(self) -> Dict[str, Any]:
        return dict(self._runtime_self_check_report)

    @runtime_self_check_report.setter
    def runtime_self_check_report(self, value: Dict[str, Any]) -> None:
        self._runtime_self_check_report = dict(value)

    def update_last_check(self, checked_at: float) -> None:
        self._state["last_check"] = checked_at

    @staticmethod
    def self_check_effective_dimension(report: Dict[str, Any]) -> int:
        for key in ("encoded_dimension", "detected_dimension", "requested_dimension"):
            try:
                value = int(report.get(key, 0) or 0)
            except Exception:
                value = 0
            if value > 0:
                return value
        return 0