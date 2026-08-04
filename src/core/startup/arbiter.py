"""启动仲裁引擎 — 相位分级 + 相位内 Kahn 分波（ZG-10）。

对标 Linux initcall：等级（相位）决定大体顺序，相位内拓扑仲裁保证
依赖正确性。核心就绪屏障（__CORE_READINESS_BARRIER__）作为虚拟节点，
确保 SESSION_RESTORE/READY 相位在核心贡献组件全部就绪后才开始。
"""

from dataclasses import dataclass, field

from src.core.service_manager.dependency_graph import DependencyGraph
from src.core.service_manager.exceptions import DependencyCycleError
from src.core.service_manager.types import DependencyKind, DependencyRelation
from src.core.startup.declaration import StartupItemDesc
from src.core.startup.types import ComponentStatus, StartupPhase


@dataclass(frozen=True)
class WavePlan:
    """波次调度计划 — 仲裁输出，供执行层按波次调度。

    phases[phase][wave_index] = [item_names]：每相位的波次列表。
    barrier_wave[phase]：屏障虚拟节点所在波次（-1 = 该相位无屏障）。
    """

    phases: dict[StartupPhase, list[list[str]]] = field(default_factory=dict)
    barrier_wave: dict[StartupPhase, int] = field(default_factory=dict)
    total_waves: int = 0


@dataclass
class CoreReadinessBarrier:
    """核心就绪屏障 — DAG 虚拟节点的运行时表示。

    贡献组件全部 SUCCESS 时屏障就绪；任一贡献组件非 SUCCESS 时未就绪，
    并记录失败贡献者（供诊断）。
    """

    VIRTUAL_NODE_ID: str = "__CORE_READINESS_BARRIER__"

    contributor_ids: set[str] = field(default_factory=lambda: {
        "chat_manager_adapter",  # message_pipeline_ready
        "agent_registry",        # agent_thinking_ready
        "replyer_port",          # reply_capability_ready
    })
    is_ready: bool = False
    failed_contributors: set[str] = field(default_factory=set)

    def check(self, states: dict[str, ComponentStatus]) -> bool:
        """检查屏障是否就绪（贡献组件全部 SUCCESS）。"""
        self.failed_contributors = {
            cid for cid in self.contributor_ids
            if states.get(cid) != ComponentStatus.SUCCESS
        }
        self.is_ready = not self.failed_contributors
        return self.is_ready


class StartupArbiter:
    """启动仲裁引擎 — 构建依赖图、插入屏障、相位内分波。"""

    # 屏障出边覆盖的相位（核心就绪后才开始）
    _BARRIER_GATED_PHASES = (StartupPhase.SESSION_RESTORE, StartupPhase.READY)

    def __init__(self) -> None:
        self.last_graph: DependencyGraph | None = None
        """最近一次仲裁构建的依赖图（供失败传播使用）。"""

    def arbitrate(
        self,
        items: dict[str, StartupItemDesc],
        skip_names: set[str] | None = None,
    ) -> WavePlan:
        """构建依赖图 + 插入屏障 + 相位内分波。

        Args:
            items: name → StartupItemDesc 映射
            skip_names: 跳过项名称集合（不加入图，不出现在波次中）

        Returns:
            WavePlan 波次调度计划

        Raises:
            DependencyCycleError: 依赖声明形成环
        """
        skip = set(skip_names or ())
        active = {n: d for n, d in items.items() if n not in skip}
        if not active:
            return WavePlan()

        graph = DependencyGraph()
        barrier = CoreReadinessBarrier()
        barrier_id = barrier.VIRTUAL_NODE_ID

        # 1. 全部节点 + 依赖边（缺省 STRONG）
        for name, desc in active.items():
            graph.add_node(name)
            for dep_name in desc.depends_on:
                if dep_name not in active:
                    continue  # 跳过被 skip 的依赖（视为已完成）
                kind = desc.dependency_kind.get(dep_name, DependencyKind.STRONG)
                graph.add_relation(DependencyRelation(name, dep_name, kind))

        # 2. 屏障虚拟节点：贡献组件 → 屏障（STRONG）；屏障 → 门控相位全部项（STRONG）
        graph.add_node(barrier_id)
        for cid in barrier.contributor_ids:
            if cid in active:
                graph.add_relation(DependencyRelation(barrier_id, cid, DependencyKind.STRONG))
        for phase in self._BARRIER_GATED_PHASES:
            for name, desc in active.items():
                if desc.phase == phase:
                    graph.add_relation(DependencyRelation(name, barrier_id, DependencyKind.STRONG))

        # 3. 全局环检测（含屏障）
        cycle = graph.detect_cycle()
        if cycle is not None:
            raise DependencyCycleError(f"依赖声明形成环: {cycle}", cycle)

        # 4. 按相位分波
        phases: dict[StartupPhase, list[list[str]]] = {}
        barrier_wave: dict[StartupPhase, int] = {}
        for phase in StartupPhase:
            phase_items = {n for n, d in active.items() if d.phase == phase}
            if not phase_items:
                continue
            # 门控相位：屏障节点参与波次计算（其依赖贡献组件跨相位视为已完成）
            if phase in self._BARRIER_GATED_PHASES:
                phase_items = phase_items | {barrier_id}
            waves = graph.compute_waves(node_filter=phase_items)
            phases[phase] = waves
            if barrier_id in phase_items:
                barrier_wave[phase] = next(
                    (i for i, w in enumerate(waves) if barrier_id in w), -1
                )

        total_waves = max((len(w) for w in phases.values()), default=0)
        self.last_graph = graph
        return WavePlan(phases=phases, barrier_wave=barrier_wave, total_waves=total_waves)
