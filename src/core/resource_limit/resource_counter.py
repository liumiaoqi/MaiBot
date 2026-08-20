"""ResourceCounter — 层级计数引擎，对标 Linux page_counter。

沿插件父链向上累加资源计量，投机充值后回滚。
对标 Linux page_counter_try_charge 的 for (c = counter; c; c = c->parent) 循环。

GIL 保证单线程原子性，无需原子操作（design §3.1.4 D1）。
"""


import time
from typing import Callable, Optional

from src.common.logger import get_logger
from src.core.resource_limit.types import (
    ChargeResult,
    ResourceDimension,
    ResourceUsageSnapshot,
)

logger = get_logger(__name__)

_ROOT_ID = "__root__"


class PluginResourceNode:
    """资源计量树节点，对应 design §3.1.2。"""

    __slots__ = (
        "plugin_id",
        "parent",
        "children",
        "usage",
        "under_oom_count",
        "last_update_time",
    )

    def __init__(self, plugin_id: str, parent: Optional["PluginResourceNode"] = None):
        self.plugin_id = plugin_id
        self.parent = parent
        self.children: list[PluginResourceNode] = []
        self.usage: dict[ResourceDimension, int] = {
            ResourceDimension.TOKEN: 0,
            ResourceDimension.MESSAGE: 0,
            ResourceDimension.CONCURRENT: 0,
            ResourceDimension.MEMORY: 0,
        }
        self.under_oom_count: int = 0
        self.last_update_time: float = time.monotonic()

    def charge(self, dim: ResourceDimension, amount: int) -> None:
        """单节点累加（仅本级，不含父链）。"""
        self.usage[dim] += amount
        self.last_update_time = time.monotonic()

    def uncharge(self, dim: ResourceDimension, amount: int) -> None:
        """单节点递减，用 max(0, ...) 保证非负。"""
        self.usage[dim] = max(0, self.usage[dim] - amount)
        self.last_update_time = time.monotonic()

    def increment_under_oom(self) -> None:
        """under_oom 计数递增。"""
        self.under_oom_count += 1

    def decrement_under_oom(self) -> None:
        """under_oom 计数递减，保证非负。"""
        self.under_oom_count = max(0, self.under_oom_count - 1)

    def to_snapshot(self) -> ResourceUsageSnapshot:
        """生成不可变快照。"""
        return ResourceUsageSnapshot(
            plugin_id=self.plugin_id,
            parent_id=self.parent.plugin_id if self.parent else None,
            token_usage=self.usage[ResourceDimension.TOKEN],
            message_usage=self.usage[ResourceDimension.MESSAGE],
            concurrent_usage=self.usage[ResourceDimension.CONCURRENT],
            memory_usage=self.usage[ResourceDimension.MEMORY],
            under_oom_count=self.under_oom_count,
            last_update_time=self.last_update_time,
        )


class ResourceCounter:
    """资源计量树管理 + 投机充值回滚，对应 design §3.1。

    max_limit_provider: (plugin_id, dimension) -> Optional[int]，返回该插件该维度的 max 硬限。
    pressure_sample_callback: (scanned, reclaimed) -> None，charge 内部调用做压力采样。
    """

    def __init__(
        self,
        max_limit_provider: Optional[Callable[[str, ResourceDimension], Optional[int]]] = None,
        pressure_sample_callback: Optional[Callable[[int, int], None]] = None,
    ):
        self._nodes: dict[str, PluginResourceNode] = {}
        self._max_limit_provider = max_limit_provider
        self._pressure_sample_callback = pressure_sample_callback

        # 根节点始终存在
        root = PluginResourceNode(_ROOT_ID, None)
        self._nodes[_ROOT_ID] = root

    @property
    def root(self) -> PluginResourceNode:
        return self._nodes[_ROOT_ID]

    def register_plugin(self, plugin_id: str, parent_id: Optional[str] = None) -> None:
        """注册插件到资源计量树。

        Args:
            plugin_id: 插件标识
            parent_id: 父插件标识，None 则挂根

        Raises:
            ValueError: plugin_id 已注册或检测到环
        """
        if plugin_id in self._nodes:
            raise ValueError(f"插件已注册: {plugin_id}")

        parent = self._nodes.get(parent_id or _ROOT_ID, self.root)

        # 环检测：沿父链向上查找，确保 plugin_id 不在祖先链中
        # （新节点不会有子节点，只需检查 parent 链不包含 plugin_id）
        # 由于 plugin_id 是新的（不在 _nodes 中），不可能形成环

        node = PluginResourceNode(plugin_id, parent)
        parent.children.append(node)
        self._nodes[plugin_id] = node
        logger.debug("注册插件 %s，父节点 %s", plugin_id, parent.plugin_id)

    def unregister_plugin(self, plugin_id: str) -> None:
        """注销插件，孤儿子节点挂根。

        Args:
            plugin_id: 插件标识

        Raises:
            KeyError: plugin_id 未注册
        """
        if plugin_id == _ROOT_ID:
            raise ValueError("不能注销根节点")
        node = self._nodes.get(plugin_id)
        if node is None:
            raise KeyError(f"插件未注册: {plugin_id}")

        # 孤节点中移除
        if node.parent:
            node.parent.children = [c for c in node.parent.children if c.plugin_id != plugin_id]

        # 孤儿子节点挂根
        for child in node.children:
            child.parent = self.root
            self.root.children.append(child)
            logger.warning(
                "插件 %s 注销，孤儿 %s 挂根",
                plugin_id,
                child.plugin_id,
            )

        del self._nodes[plugin_id]
        logger.debug("注销插件 %s", plugin_id)

    def charge(
        self, plugin_id: str, dimension: ResourceDimension, amount: int
    ) -> ChargeResult:
        """投机充值（同步，热路径纯内存无 I/O）。

        沿父链逐级投机累加，任一级超该级 max 则回滚已充级别。
        对标 Linux page_counter_try_charge。

        Args:
            plugin_id: 插件标识
            dimension: 资源维度
            amount: 充值量（正整数）

        Returns:
            ChargeResult

        Raises:
            KeyError: plugin_id 未注册
            ValueError: amount 非正
        """
        if amount <= 0:
            raise ValueError(f"充值量必须为正整数: {amount}")

        node = self._nodes.get(plugin_id)
        if node is None:
            raise KeyError(f"插件未注册: {plugin_id}")

        # 投机累加：沿父链逐级累加
        charged_chain: list[PluginResourceNode] = []
        current: Optional[PluginResourceNode] = node
        while current is not None:
            current.usage[dimension] += amount
            current.last_update_time = time.monotonic()
            charged_chain.append(current)

            # 检查本级 max
            if self._max_limit_provider:
                limit = self._max_limit_provider(current.plugin_id, dimension)
                if limit is not None and current.usage[dimension] > limit:
                    # 超限，回滚已充级别
                    for n in charged_chain:
                        n.usage[dimension] = max(0, n.usage[dimension] - amount)
                        n.last_update_time = time.monotonic()

                    # 压力采样：charge 拒绝时 scanned+1
                    if self._pressure_sample_callback:
                        self._pressure_sample_callback(1, 0)

                    return ChargeResult(
                        accepted=False,
                        overflow_node_id=current.plugin_id,
                        overflow_dimension=dimension,
                    )
            current = current.parent

        # 全部成功
        # 压力采样：charge 成功时 reclaimed+1
        if self._pressure_sample_callback:
            self._pressure_sample_callback(0, 1)

        return ChargeResult(accepted=True)

    def uncharge(
        self, plugin_id: str, dimension: ResourceDimension, amount: int
    ) -> None:
        """递减计量（同步，热路径纯内存无 I/O）。

        沿父链向上递减，用 max(0, ...) 保证非负。
        """
        if amount <= 0:
            return

        node = self._nodes.get(plugin_id)
        if node is None:
            raise KeyError(f"插件未注册: {plugin_id}")

        current: Optional[PluginResourceNode] = node
        while current is not None:
            current.usage[dimension] = max(0, current.usage[dimension] - amount)
            current.last_update_time = time.monotonic()
            current = current.parent

    def get_usage_snapshot(self, plugin_id: str) -> Optional[ResourceUsageSnapshot]:
        """查询单插件资源计量快照。"""
        node = self._nodes.get(plugin_id)
        if node is None:
            return None
        return node.to_snapshot()

    def get_node(self, plugin_id: str) -> Optional[PluginResourceNode]:
        """获取节点引用（内部使用）。"""
        return self._nodes.get(plugin_id)

    def all_nodes(self) -> list[PluginResourceNode]:
        """获取所有非根节点。"""
        return [n for pid, n in self._nodes.items() if pid != _ROOT_ID]