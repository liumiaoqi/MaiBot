"""ZG-N5 压缩升级——surface 替换器。

对标 dsh region.ts:427 commitCompactionBody（同步提交 + surface.replaceGeneration 递增）。
在 surface 中用摘要节点替换原始范围，递增 replace_generation。
原始事件不删除——surface 替换仅改变模型可见视图，底层日志保留。
"""


from .ports import MemoryStorePort
from .types import (
    CompactionRange,
    ReplaceResult,
    SummaryNode,
)


class SurfaceReplacer:
    """surface 替换器——摘要节点替换原始范围 + 代数递增。"""

    def __init__(self, memory_store: MemoryStorePort) -> None:
        self._memory_store = memory_store

    async def replace(
        self,
        session_id: str,
        range: CompactionRange,
        summary_node: SummaryNode,
    ) -> ReplaceResult:
        """surface 替换——摘要节点替换原始范围，递增 replace_generation。

        对标 dsh region.ts:427 commitCompactionBody——同步提交，不 yield。
        summary 持久化与 surface 替换同步相邻提交。

        Args:
            session_id: 会话标识
            range: 被替换范围
            summary_node: 摘要节点

        Returns:
            替换结果（含新 replace_generation）
        """
        new_generation = await self._memory_store.replace_surface_range(
            session_id=session_id,
            range=range,
            summary_node_id=summary_node.node_id,
            summary_text=summary_node.summary,
            tx_id=summary_node.tx_id,
        )
        return ReplaceResult(
            new_generation=new_generation,
            replaced_range=range,
            summary_node_id=summary_node.node_id,
        )

    async def current_generation(self, session_id: str) -> int:
        """当前 surface replace_generation。"""
        return await self._memory_store.read_surface_generation(session_id)

    async def assert_surface_unchanged(
        self,
        session_id: str,
        expected_generation: int,
    ) -> bool:
        """校验 surface 在异步摘要期间未变。

        对标 dsh region.ts:387 assertWholeSurfaceUnchanged。
        """
        current = await self.current_generation(session_id)
        return current == expected_generation