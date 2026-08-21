"""A_memorix 不变量 — memory service port 已注册。

v2 简化：检查 port 可获取。v3 增强：vector_store 索引大小 == metadata_store active 数。
get_memory_service_port() 未注册时抛 RuntimeError，捕获为违反。
"""

from src.core.invariant_registry import invariant


@invariant("A_memorix")
def check_memorix(fail) -> None:
    """检查 memory service port 可获取 + vector_store 索引一致性。"""
    try:
        from src.core.adapters.memory_service import get_memory_service_port

        port = get_memory_service_port()
        # v3：vector_store 索引一致性
        stats = port.get_vector_store_stats()
        if stats["index_size"] != stats["active_count"]:
            fail(f"vector_store 不一致: index={stats['index_size']} active={stats['active_count']}")
    except RuntimeError as exc:
        fail(f"memory service port 未注册: {exc}")
    except Exception as exc:
        fail(f"memory service port 获取异常: {exc}")