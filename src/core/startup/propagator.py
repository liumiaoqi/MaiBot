"""失败传播器 — STRONG→SKIPPED / WEAK→DEGRADED 递归标记（ZG-10）。

对标 Linux 错误升级梯的"依赖方响应"：强依赖方随失败项跳过（不可运行），
弱依赖方降级（仍可运行但不保证依赖）。failure_chains 记录完整传播路径，
供启动摘要与诊断。
"""

from collections import deque
from dataclasses import dataclass, field

from src.core.service_manager.dependency_graph import DependencyGraph
from src.core.service_manager.types import DependencyKind
from src.core.startup.types import ComponentStatus


@dataclass
class PropagationResult:
    """失败传播结果。"""

    state_updates: dict[str, ComponentStatus] = field(default_factory=dict)
    """name → 更新后的状态"""

    failure_chains: dict[str, str] = field(default_factory=dict)
    """受影响项 → 根因项"""


class FailurePropagator:
    """失败传播器 — BFS 遍历依赖方，STRONG 递归 / WEAK 不递归。

    规则：
    - STRONG 依赖方 → SKIPPED，并递归传播其依赖方（BFS + visited 防环）
    - WEAK 依赖方 → DEGRADED，不递归（降级仍可运行，不影响其下游）
    - 混合依赖（同项同时 STRONG + WEAK on 失败项）→ STRONG 优先
    """

    def propagate(
        self,
        failed_name: str,
        graph: DependencyGraph,
        current_states: dict[str, ComponentStatus],
    ) -> PropagationResult:
        """从失败项出发，递归传播失败状态。

        Args:
            failed_name: 失败项名称（状态应为 FAILED 或 SKIPPED）
            graph: 依赖图
            current_states: 当前项状态映射（只读，更新在返回值中）

        Returns:
            PropagationResult 含状态更新与失败链
        """
        updates: dict[str, ComponentStatus] = {}
        chains: dict[str, str] = {}

        visited: set[str] = set()
        queue: deque[tuple[str, str]] = deque([(failed_name, failed_name)])
        # (current, root)：current 是待传播的失败/跳过项，root 是根因

        while queue:
            current, root = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            for dependent, kind in graph.dependents_with_kind(current).items():
                if dependent in visited:
                    # 已处理节点（含根）：不标记（根是 FAILED 不是被传播的 SKIPPED）
                    continue
                if kind == DependencyKind.STRONG:
                    # STRONG：标记 SKIPPED + 递归传播
                    if updates.get(dependent) != ComponentStatus.SKIPPED:
                        updates[dependent] = ComponentStatus.SKIPPED
                        chains[dependent] = root
                    queue.append((dependent, root))
                else:
                    # WEAK：标记 DEGRADED，不递归
                    if updates.get(dependent) != ComponentStatus.SKIPPED:
                        updates[dependent] = ComponentStatus.DEGRADED
                        chains[dependent] = root

        return PropagationResult(state_updates=updates, failure_chains=chains)
