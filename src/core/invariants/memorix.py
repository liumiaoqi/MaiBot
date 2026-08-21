"""A_memorix 不变量 — memory service port 已注册。

v2 简化：检查 port 可获取。v3 增强：vector_store 索引大小 == metadata_store active 数。
get_memory_service_port() 未注册时抛 RuntimeError，捕获为违反。
"""

from src.core.invariant_registry import invariant


@invariant("A_memorix")
def check_memorix(fail) -> None:
    """检查 memory service port 可获取。"""
    try:
        from src.core.adapters.memory_service import get_memory_service_port

        get_memory_service_port()
    except RuntimeError as exc:
        fail(f"memory service port 未注册: {exc}")
    except Exception as exc:
        fail(f"memory service port 获取异常: {exc}")