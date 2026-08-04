"""依赖图引擎 — 纯逻辑，无 I/O，无 async。

管理组件间依赖关系，提供拓扑排序、环检测、级联顺序计算。
为生命周期管理提供级联停止/启动顺序。
"""


from collections import deque

from src.core.service_manager.exceptions import DependencyCycleError
from src.core.service_manager.types import DependencyKind, DependencyRelation


class DependencyGraph:
    """组件依赖图 — 维护正反向邻接表，提供拓扑排序和级联顺序计算。

    内部维护：
    - _dependencies: dependent → {dependency: kind}（依赖方 → 被依赖方集合）
    - _dependents: dependency → {dependent: kind}（被依赖方 → 依赖方集合）
    - _topo_cache: 拓扑排序缓存，add_relation 后失效
    """

    def __init__(self) -> None:
        # dependent → {dependency: kind}
        self._dependencies: dict[str, dict[str, DependencyKind]] = {}
        # dependency → {dependent: kind}
        self._dependents: dict[str, dict[str, DependencyKind]] = {}
        self._topo_cache: list[str] | None = None

    def add_relation(self, relation: DependencyRelation) -> None:
        """添加依赖边，同时维护正反向邻接表。

        Args:
            relation: 依赖关系声明
        """
        dep_map = self._dependencies.setdefault(relation.dependent, {})
        dep_map[relation.dependency] = relation.kind

        rev_map = self._dependents.setdefault(relation.dependency, {})
        rev_map[relation.dependent] = relation.kind

        # 确保两个节点都在依赖图中
        self._dependencies.setdefault(relation.dependency, {})
        self._dependents.setdefault(relation.dependent, {})

        self._topo_cache = None

    def _all_nodes(self) -> set[str]:
        """返回图中所有节点。"""
        return set(self._dependencies.keys()) | set(self._dependents.keys())

    def add_node(self, node_id: str) -> None:
        """添加独立节点（无依赖边，ZG-10 T8）。

        Args:
            node_id: 节点唯一标识（重复添加幂等）
        """
        self._dependencies.setdefault(node_id, {})
        self._dependents.setdefault(node_id, {})
        self._topo_cache = None

    def compute_waves(self, node_filter: set[str] | None = None) -> list[list[str]]:
        """Kahn 零入度分波（ZG-10 T9）。

        按零入度分层：同一波次内任意两项无直接/间接依赖（可并行），
        波次间按依赖关系串行。对标 Linux initcall 等级 + 相位内仲裁。

        Args:
            node_filter: 仅计算这些节点的波次（None=全部节点）。
                子集内节点的入度只统计"依赖也在子集内"的边——
                不在子集内的节点视为已完成，其出边不贡献入度。

        Returns:
            波次列表，waves[i] = 第 i 波的节点名列表（同波次字母序）

        Raises:
            DependencyCycleError: 存在环时抛出（含环上节点）
        """
        nodes = self._all_nodes() if node_filter is None else set(node_filter)
        if not nodes:
            return []

        # 入度：仅统计依赖也在子集内的边
        in_degree: dict[str, int] = {}
        for n in nodes:
            deps = self._dependencies.get(n, {})
            in_degree[n] = sum(1 for dep in deps if dep in nodes)

        queue = deque(sorted(n for n in nodes if in_degree[n] == 0))
        waves: list[list[str]] = []
        remaining = len(nodes)

        while queue:
            wave: list[str] = []
            for _ in range(len(queue)):
                node = queue.popleft()
                wave.append(node)
                remaining -= 1
                for dependent in self._dependents.get(node, {}):
                    if dependent not in nodes:
                        continue
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
            waves.append(sorted(wave))

        if remaining > 0:
            cycle_nodes = sorted(n for n in nodes if in_degree[n] > 0)
            raise DependencyCycleError(
                f"依赖声明形成环: {cycle_nodes}", cycle_nodes
            )
        return waves

    def detect_cycle(self) -> list[str] | None:
        """Kahn 算法环检测。

        Returns:
            环上的节点列表，无环返回 None
        """
        nodes = self._all_nodes()
        # 计算入度（被依赖次数）
        in_degree: dict[str, int] = {n: 0 for n in nodes}
        for dependent, deps in self._dependencies.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dependent] = in_degree.get(dependent, 0)
                in_degree[dependent] = len(deps)

        # 重新算入度：每个节点的入度 = 它依赖的节点数
        in_degree = {n: len(self._dependencies.get(n, {})) for n in nodes}

        queue = deque(n for n in nodes if in_degree[n] == 0)
        sorted_count = 0

        while queue:
            node = queue.popleft()
            sorted_count += 1
            # node 的被依赖方（依赖 node 的组件）入度减 1
            for dependent in self._dependents.get(node, {}):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if sorted_count < len(nodes):
            # 存在环，找出环上的节点
            cycle_nodes = [n for n in nodes if in_degree[n] > 0]
            return cycle_nodes
        return None

    def topological_sort(self) -> list[str]:
        """返回拓扑序（被依赖方在前）。

        Returns:
            拓扑排序后的节点列表

        Raises:
            DependencyCycleError: 存在环时抛出
        """
        if self._topo_cache is not None:
            return self._topo_cache

        cycle = self.detect_cycle()
        if cycle is not None:
            raise DependencyCycleError(f"依赖声明形成环: {cycle}", cycle)

        nodes = self._all_nodes()
        in_degree = {n: len(self._dependencies.get(n, {})) for n in nodes}
        queue = deque(n for n in nodes if in_degree[n] == 0)
        result: list[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for dependent in self._dependents.get(node, {}):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        self._topo_cache = result
        return result

    def cascade_stop_order(self, component_id: str) -> tuple[list[str], list[str]]:
        """返回停止组件时需级联处理的组件列表。

        停止顺序：依赖方先于被依赖方（拓扑序逆序）。
       F       强依赖方级联停止，弱依赖方降级。

        Args:
            component_id: 被停止的组件 ID

        Returns:
            (强依赖级联停止列表, 弱依赖降级列表)
        """
        strong_stop: list[str] = []
        weak_degrade: list[str] = []

        # BFS 收集所有传递依赖方
        visited: set[str] = set()
        queue = deque([component_id])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            for dependent, kind in self._dependents.get(current, {}).items():
                if kind == DependencyKind.STRONG:
                    if dependent not in strong_stop:
                        strong_stop.append(dependent)
                    queue.append(dependent)
                else:
                    if dependent not in weak_degrade:
                        weak_degrade.append(dependent)

        # 强依赖按拓扑序逆序排列（依赖方先停）
        topo = self.topological_sort()
        topo_rank = {n: i for i, n in enumerate(topo)}
        strong_stop.sort(key=lambda x: topo_rank.get(x, 0), reverse=True)

        return strong_stop, weak_degrade

    def cascade_start_order(self, component_id: str) -> list[str]:
        """返回启动组件时需校验就绪的依赖列表。

        启动顺序：被依赖方先于依赖方（拓扑序正序）。

        Args:
            component_id: 被启动的组件 ID

        Returns:
            需校验就绪的依赖组件列表（被依赖方在前）
        """
        result: list[str] = []
        visited: set[str] = set()
        queue = deque([component_id])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            for dep in self._dependencies.get(current, {}):
                if dep not in result:
                    result.append(dep)
                queue.append(dep)

        # 按拓扑序正序排列（被依赖方在前）
        topo = self.topological_sort()
        topo_rank = {n: i for i, n in enumerate(topo)}
        result.sort(key=lambda x: topo_rank.get(x, 0))

        return result

    def dependents_of(self, component_id: str) -> set[str]:
        """查询直接依赖该组件的组件集合。"""
        return set(self._dependents.get(component_id, {}).keys())

    def dependencies_of(self, component_id: str) -> set[str]:
        """查询该组件直接依赖的组件集合。"""
        return set(self._dependencies.get(component_id, {}).keys())

    def dependencies_with_kind(self, component_id: str) -> dict[str, DependencyKind]:
        """查询该组件直接依赖及其类型。"""
        return dict(self._dependencies.get(component_id, {}))