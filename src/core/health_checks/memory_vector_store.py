"""memory.vector_store 健康检查 — 向量索引一致性。

v2 简化：检查 memory service port 可获取。v3 增强：向量索引计数对比。
port 未注册返回 UNKNOWN（A_memorix 可能未启用）。
"""

from src.core.health_check import BaseHealthCheck, HealthResult, HealthStatus


class MemoryVectorStoreHealthCheck(BaseHealthCheck):
    """向量索引一致性健康检查。"""

    def __init__(self, timeout: float | None = None) -> None:
        super().__init__(name="memory.vector_store", timeout=timeout)

    async def _do_check(self) -> HealthResult:
        try:
            from src.core.adapters.memory_service import get_memory_service_port

            port = get_memory_service_port()
            # v3：向量索引计数对比
            stats = port.get_vector_store_stats()
            if stats["index_size"] == stats["active_count"]:
                return HealthResult(HealthStatus.UP, stats)
            return HealthResult(HealthStatus.DEGRADED, {"reason": "索引不一致", **stats})
        except RuntimeError as exc:
            return HealthResult(
                HealthStatus.UNKNOWN,
                {"reason": "memory service port 未注册（A_memorix 可能未启用）", "error": str(exc)},
            )
        except Exception as exc:
            return HealthResult(
                HealthStatus.UNKNOWN,
                {"reason": "memory service port 获取异常", "error": str(exc)},
            )