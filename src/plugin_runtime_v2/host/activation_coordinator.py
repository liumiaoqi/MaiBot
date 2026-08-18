"""激活编排器 — 持有依赖图状态，编排启动/热加载/卸载的依赖变更。

ZG16-3：在 DependencyResolver（纯逻辑）之上增加状态管理，
编排 RunnerSupervisor 的 spawn 顺序 + 失败传播 + 热加载/卸载依赖检查。
"""


from pathlib import Path

from src.common.logger import get_logger
from src.core.error_escalation.types import ErrorLevel
from src.core.error_escalation_port_registry import get_error_escalation_port
from src.core.service_manager.dependency_graph import DependencyGraph
from src.core.service_manager.exceptions import DependencyCycleError
from src.core.service_manager.types import DependencyKind, DependencyRelation
from src.plugin_runtime_v2.host.dependency_resolver import (
    ActivationPlan,
    CandidateMap,

    compute_activation_plan,
)
from src.plugin_runtime_v2.sdk.manifest import ManifestV3

logger = get_logger("plugin_runtime_v2.host.activation_coordinator")


def _report_error(message: str, exception: Exception | None = None) -> None:
    """上报错误到 error_escalation_port。"""
    port = get_error_escalation_port()
    if port is not None:
        port.report(ErrorLevel.ERROR, message, exception=exception)
    logger.error(message)


def _report_warning(message: str) -> None:
    """上报告警到 error_escalation_port。"""
    port = get_error_escalation_port()
    if port is not None:
        port.report(ErrorLevel.WARN, message)
    logger.warning(message)


class ActivationCoordinator:
    """激活编排器——持有依赖图状态，编排启动/热加载/卸载的依赖变更。

    内部状态：
    - _graph: DependencyGraph（依赖图，随激活/卸载变更）
    - _activated: set[str]（已激活插件 ID 集合）
    - _skipped: dict[str, str]（跳过清单）
    - _candidate_dirs: dict[str, Path]（插件 ID → 目录路径）
    - _candidates: CandidateMap（候选插件映射，供补全评估用）
    """

    def __init__(self, supervisor) -> None:
        """注入 RunnerSupervisor（实际 spawn Runner 用）。

        Args:
            supervisor: RunnerSupervisor 实例
        """
        self._supervisor = supervisor
        self._graph: DependencyGraph = DependencyGraph()
        self._activated: set[str] = set()
        self._skipped: dict[str, str] = {}
        self._candidate_dirs: dict[str, Path] = {}
        self._candidates: CandidateMap = {}

    # ── 启动激活 ──────────────────────────────────────────────

    async def plan_startup(
        self,
        plugins_root: Path,
        runner_spawn_count: int = -1,
    ) -> ActivationPlan:
        """启动时依赖解析 + 拓扑激活编排。实际 spawn 在本方法内完成。

        Args:
            plugins_root: 插件根目录（如 plugins-v2/）
            runner_spawn_count: Runner spawn 上限（-1=不限，>0=上限）

        Returns:
            激活计划（含波次/跳过/环错误）
        """
        # 1. 扫描候选目录（sorted 字母序，向后兼容 + 确定性）
        if not plugins_root.is_dir():
            logger.warning("插件目录 %s 不存在，跳过激活", plugins_root)
            return ActivationPlan(waves=[], skipped={}, cycle_errors=[])

        plugin_dirs = sorted(
            d for d in plugins_root.iterdir()
            if d.is_dir() and ((d / "manifest.json").is_file() or (d / "_manifest.json").is_file())
        )

        if not plugin_dirs:
            logger.warning("插件目录 %s 下未发现有效插件", plugins_root)
            return ActivationPlan(waves=[], skipped={}, cycle_errors=[])

        # 2. 依赖解析 + 拓扑分波
        plan = compute_activation_plan(plugin_dirs)

        # 3. 重建候选 manifest 映射（供后续热加载/卸载用）
        candidates_map: CandidateMap = {}
        for plugin_id, plugin_dir in plan.candidate_dirs.items():
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.is_file():
                manifest_path = plugin_dir / "_manifest.json"
            if manifest_path.is_file():
                import json
                from pydantic import ValidationError
                try:
                    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest = ManifestV3.model_validate(raw)
                    candidates_map[plugin_id] = (plugin_dir, manifest)
                except (OSError, json.JSONDecodeError, ValidationError) as exc:
                    # P0-2: manifest 加载失败出声（ZG-31）
                    # 对标 Linux kernel/panic.c:77-92 OOPS + dsh defensive-patterns: Contain callback exceptions in the dispatcher
                    logger.warning(
                        "插件 %s manifest 加载失败，跳过该插件: %s", plugin_id, exc,
                        exc_info=True,
                    )

        self._candidates = candidates_map
        self._candidate_dirs = dict(plan.candidate_dirs)
        self._skipped = dict(plan.skipped)

        # 重建依赖图（仅可激活插件，过滤 skipped — P1-3 修复）
        new_graph = DependencyGraph()
        for plugin_id in candidates_map:
            if plugin_id not in self._skipped:
                new_graph.add_node(plugin_id)
        for plugin_id, (_, manifest) in candidates_map.items():
            if plugin_id in self._skipped:
                continue
            for dep_id in manifest.dependencies:
                if dep_id in candidates_map and dep_id not in self._skipped:
                    new_graph.add_relation(
                        DependencyRelation(
                            dependent=plugin_id,
                            dependency=dep_id,
                            kind=DependencyKind.STRONG,
                        )
                    )
        self._graph = new_graph

        # 4. 按波次逐波 spawn
        spawned = 0
        hit_limit = False
        for wave in plan.waves:
            if hit_limit:
                break
            # 波次与 runner_spawn_count 上限交互：切分子波次
            if runner_spawn_count > 0 and len(wave) > runner_spawn_count:
                sub_waves = [
                    wave[i:i + runner_spawn_count]
                    for i in range(0, len(wave), runner_spawn_count)
                ]
            else:
                sub_waves = [wave]

            for sub_wave in sub_waves:
                for plugin_id in sub_wave:
                    # 总 spawn 数上限
                    if runner_spawn_count > 0 and spawned >= runner_spawn_count:
                        logger.info(
                            "达到 runner_spawn_count 上限 %d，停止 spawn",
                            runner_spawn_count,
                        )
                        hit_limit = True
                        break

                    plugin_dir = plan.candidate_dirs.get(plugin_id)
                    if plugin_dir is None:
                        continue

                    try:
                        result = await self._supervisor.spawn_and_wait(
                            plugin_id, str(plugin_dir)
                        )
                        if result.success:
                            self.on_plugin_activated(plugin_id)
                            spawned += 1
                        else:
                            self.on_plugin_failed(plugin_id, f"spawn 失败: {result.reason}")
                    except Exception as exc:
                        self.on_plugin_failed(plugin_id, f"spawn 异常: {exc}")
                        _report_error(f"spawn 插件 {plugin_id} 失败: {exc}", exc)
                if hit_limit:
                    break

        # P2-5：达到上限未 spawn 的插件记入 skipped（运维可见）
        if hit_limit:
            for wave in plan.waves:
                for plugin_id in wave:
                    if plugin_id not in self._activated and plugin_id not in self._skipped:
                        self._skipped[plugin_id] = "达到 runner_spawn_count 上限未激活"

        activated_count = len(self._activated)
        skipped_count = len(self._skipped)
        logger.info(
            "激活编排完成: %d 个激活, %d 个跳过, %d 个环错误",
            activated_count, skipped_count, len(plan.cycle_errors),
        )
        return plan

    # ── 状态回调 ──────────────────────────────────────────────

    def on_plugin_activated(self, plugin_id: str) -> None:
        """标记插件已激活成功（加入已激活集）。"""
        self._activated.add(plugin_id)
        self._skipped.pop(plugin_id, None)

    def on_plugin_failed(self, plugin_id: str, reason: str) -> None:
        """标记插件激活失败，传播跳过依赖该插件的下游。"""
        self._skipped[plugin_id] = f"激活失败: {reason}"
        self._activated.discard(plugin_id)

        # 传播跳过：依赖该插件的下游也跳过
        changed = True
        while changed:
            changed = False
            for pid in list(self._candidates.keys()):
                if pid in self._skipped:
                    continue
                _, manifest = self._candidates[pid]
                for dep_id in manifest.dependencies:
                    if dep_id in self._skipped:
                        self._skipped[pid] = f"依赖 {dep_id} 级联跳过"
                        _report_warning(
                            f"插件 {pid} 跳过：依赖 {dep_id} 级联跳过"
                        )
                        changed = True
                        break

    @property
    def activated(self) -> set[str]:
        """已激活插件 ID 集合。"""
        return self._activated

    @property
    def skipped(self) -> dict[str, str]:
        """跳过清单。"""
        return self._skipped

    # ── 热加载 ────────────────────────────────────────────────

    def check_hot_load(
        self,
        manifest: ManifestV3,
        plugin_dir: Path,
    ) -> tuple[bool, list[str]]:
        """热加载依赖检查。

        检查 manifest.dependencies 是否全部在已激活集中。

        Args:
            manifest: 新插件 manifest
            plugin_dir: 新插件目录

        Returns:
            (可激活, 缺失依赖 ID 列表)
        """
        missing: list[str] = []
        for dep_id in manifest.dependencies:
            if dep_id not in self._activated:
                if dep_id in self._skipped:
                    missing.append(f"{dep_id}(此前被跳过)")
                else:
                    missing.append(dep_id)
        return (len(missing) == 0, missing)

    async def plan_hot_load(
        self,
        manifest: ManifestV3,
        plugin_dir: Path,
    ) -> ActivationPlan:
        """热加载新插件：依赖检查 + 环检查 + spawn + 补全评估。

        Args:
            manifest: 新插件 manifest
            plugin_dir: 新插件目录

        Returns:
            激活计划（单插件）
        """
        plugin_id = manifest.id

        # 1. 依赖检查
        can_activate, missing = self.check_hot_load(manifest, plugin_dir)
        if not can_activate:
            self._skipped[plugin_id] = f"依赖未满足: {missing}"
            _report_warning(f"热加载插件 {plugin_id} 跳过：依赖未满足: {missing}")
            return ActivationPlan(
                waves=[],
                skipped={plugin_id: f"依赖未满足: {missing}"},
                cycle_errors=[],
            )

        # 2. 环检查：增量 add_relation + detect_cycle
        added_relations: list[DependencyRelation] = []
        for dep_id in manifest.dependencies:
            if dep_id in self._activated:
                relation = DependencyRelation(
                    dependent=plugin_id,
                    dependency=dep_id,
                    kind=DependencyKind.STRONG,
                )
                self._graph.add_relation(relation)
                added_relations.append(relation)

        cycle = self._graph.detect_cycle()
        if cycle is not None and plugin_id in cycle:
            # 形成环：回滚 + 拒绝
            # 重建图（回滚 add_relation）
            self._rebuild_graph()
            self._skipped[plugin_id] = "热加载会形成环"
            _report_error(f"热加载插件 {plugin_id} 会形成环: {' → '.join(cycle)}")
            return ActivationPlan(
                waves=[],
                skipped={plugin_id: "热加载会形成环"},
                cycle_errors=[cycle],
            )

        # 3. spawn
        try:
            result = await self._supervisor.spawn_and_wait(plugin_id, str(plugin_dir))
            if result.success:
                self.on_plugin_activated(plugin_id)
                self._candidates[plugin_id] = (plugin_dir, manifest)
                self._candidate_dirs[plugin_id] = plugin_dir
            else:
                self.on_plugin_failed(plugin_id, f"spawn 失败: {result.reason}")
                return ActivationPlan(
                    waves=[],
                    skipped={plugin_id: f"激活失败: {result.reason}"},
                    cycle_errors=[],
                )
        except Exception as exc:
            self.on_plugin_failed(plugin_id, f"spawn 异常: {exc}")
            _report_error(f"热加载 spawn 插件 {plugin_id} 失败: {exc}", exc)
            return ActivationPlan(
                waves=[],
                skipped={plugin_id: f"激活失败: {exc}"},
                cycle_errors=[],
            )

        # 4. 补全评估：重新评估被跳过插件是否可补激活
        await self._complement_evaluate()

        return ActivationPlan(
            waves=[[plugin_id]],
            skipped={},
            cycle_errors=[],
            candidate_dirs={plugin_id: plugin_dir},
        )

    async def _complement_evaluate(self) -> None:
        """补全评估：重新评估被跳过插件是否可补激活。

        仅对因依赖缺失而跳过的插件（非永久跳过如循环依赖/自依赖）重新评估。
        """
        to_activate: list[str] = []
        for pid, reason in list(self._skipped.items()):
            # 永久跳过的不补激活
            if "循环依赖" in reason or "自依赖" in reason or "格式非法" in reason:
                continue
            if "id 重复" in reason:
                continue
            if pid not in self._candidates:
                continue
            _, manifest = self._candidates[pid]
            can_activate, _ = self.check_hot_load(manifest, self._candidate_dirs.get(pid, Path()))
            if can_activate:
                to_activate.append(pid)

        for pid in to_activate:
            plugin_dir = self._candidate_dirs.get(pid)
            if plugin_dir is None:
                continue
            try:
                result = await self._supervisor.spawn_and_wait(pid, str(plugin_dir))
                if result.success:
                    self.on_plugin_activated(pid)
                    logger.info("补全激活插件 %s", pid)
            except Exception as exc:
                _report_error(f"补全激活插件 {pid} 失败: {exc}", exc)

    # ── 卸载 ──────────────────────────────────────────────────

    def plan_unload(
        self,
        plugin_ids: set[str],
    ) -> list[str]:
        """计算卸载逆序（依赖方先于被依赖方）。

        对每个待卸载插件计算其级联停止列表（依赖方），求并集后按拓扑逆序排列。

        Args:
            plugin_ids: 待卸载插件 ID 集合

        Returns:
            逆序卸载列表（依赖方在前，被依赖方在后）
        """
        if not plugin_ids:
            return []

        # 收集所有需卸载的插件（含级联依赖方）
        to_unload: set[str] = set()
        for pid in plugin_ids:
            to_unload.add(pid)
            # 获取依赖该插件的所有传递依赖方
            strong_stop, _ = self._graph.cascade_stop_order(pid)
            to_unload.update(strong_stop)

        # 按拓扑逆序排列（依赖方先于被依赖方）
        try:
            topo = self._graph.topological_sort()
        except DependencyCycleError:
            # 理论上不应发生（环内插件不激活），fallback 按字母序
            return sorted(to_unload)

        topo_rank = {n: i for i, n in enumerate(topo)}
        # 拓扑序中被依赖方在前（index 小），依赖方在后（index 大）
        # 卸载逆序：依赖方先卸（index 大的先），被依赖方后卸
        return sorted(to_unload, key=lambda x: topo_rank.get(x, 0), reverse=True)

    def on_plugin_unloaded(self, plugin_id: str) -> None:
        """标记插件已卸载（从已激活集和依赖图移除）。"""
        self._activated.discard(plugin_id)
        self._candidate_dirs.pop(plugin_id, None)
        self._candidates.pop(plugin_id, None)
        # DependencyGraph 无 remove_node，重建图
        self._rebuild_graph()

    def _rebuild_graph(self) -> None:
        """从剩余已激活插件重建依赖图。"""
        new_graph = DependencyGraph()
        for plugin_id in self._candidates:
            new_graph.add_node(plugin_id)
        for plugin_id, (_, manifest) in self._candidates.items():
            if plugin_id in self._skipped:
                continue
            for dep_id in manifest.dependencies:
                if dep_id in self._candidates and dep_id not in self._skipped:
                    new_graph.add_relation(
                        DependencyRelation(
                            dependent=plugin_id,
                            dependency=dep_id,
                            kind=DependencyKind.STRONG,
                        )
                    )
        self._graph = new_graph