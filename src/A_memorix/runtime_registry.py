from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel

_runtime_kernel: Optional[SDKMemoryKernel] = None


def set_runtime_kernel(kernel: SDKMemoryKernel | None) -> None:
    global _runtime_kernel
    _runtime_kernel = kernel
