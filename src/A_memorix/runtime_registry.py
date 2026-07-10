from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel

_runtime_kernel: Optional[SDKMemoryKernel] = None


def set_runtime_kernel(kernel: SDKMemoryKernel | None) -> None:
    global _runtime_kernel
    _runtime_kernel = kernel


def get_runtime_kernel() -> SDKMemoryKernel | None:
    return _runtime_kernel


def get_runtime_components() -> Dict[str, Any]:
    kernel = get_runtime_kernel()
    if kernel is None:
        return {}
    return {
        "vector_store": kernel.vector_store,
        "paragraph_vector_store": kernel.paragraph_vector_store,
        "graph_vector_store": kernel.graph_vector_store,
        "graph_store": kernel.graph_store,
        "metadata_store": kernel.metadata_store,
        "embedding_manager": kernel.embedding_manager,
        "sparse_index": kernel.sparse_index,
        "vector_pools_ready": bool(kernel._dual_vector_pools_enabled()),
    }
