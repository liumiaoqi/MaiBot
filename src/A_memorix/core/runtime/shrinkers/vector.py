"""ZG-27 向量存储 shrinker V1 占位（spec 5.5.3 决策 3 边界）。

V1 边界：仅注册占位，count_objects 恒返回 0（向量存储由外部管理，V1 不主动回收）。
seeks=8（对标 Linux shrinker 默认 seeks）。
V2 可扩展为真实向量缓存回收。
"""

from src.A_memorix.core.runtime.shrinker import ShrinkControl


class VectorShrinker:
    """向量存储 shrinker V1 占位。"""

    name = "vector_store"
    batch = 0
    seeks = 8
    flags = 0

    def __init__(self, vector_store=None) -> None:
        self._vector_store = vector_store

    async def count_objects(self, sc: ShrinkControl) -> int:
        """V1 占位：恒返回 0（向量存储由外部管理）。"""
        return 0

    async def scan_objects(self, sc: ShrinkControl) -> int:
        """V1 占位：恒返回 0。"""
        return 0