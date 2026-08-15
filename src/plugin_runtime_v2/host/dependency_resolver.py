"""依赖解析器 — 纯逻辑，无 async（manifest 文件读除外）。

解析候选插件 manifest v3 → 构建依赖图 → 识别缺失依赖 → 传播跳过 → Kahn 拓扑分波 → 环检测。
复用 core 层 DependencyGraph（组件→核心依赖方向，不违反核心隔离）。

ZG16-3：插件 depends_on 激活，复用 ZG-10 的 Kahn 算法哲学（同一哲学不同层）。
"""


import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from src.common.logger import get_logger
from src.core.error_escalation.types import ErrorLevel
from src.core.error_escalation_port_registry import get_error_escalation_port
from src.core.service_manager.dependency_graph import DependencyGraph
from src.core.service_manager.exceptions import DependencyCycleError
from src.core.service_manager.types import DependencyKind, DependencyRelation
from src.plugin_runtime_v2.sdk.manifest import ManifestV3

logger = get_logger("plugin_runtime_v2.host.dependency_resolver")

# 插件 ID 格式正则（与 ManifestV3.id pattern 一致）
_PLUGIN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+$")

# 类型别名
CandidateMap = dict[str, tuple[Path, ManifestV3]]
"""候选插件映射：插件 ID → (目录路径, manifest 实例)"""

SkipMap = dict[str, str]
"""跳过清单：插件 ID → 跳过原因"""


def _report_error(message: str, exception: Exception | None = None) -> None:
    """上报错误到 error_escalation_port（未注册时仅记日志）。"""
    port = get_error_escalation_port()
    if port is not None:
        port.report(ErrorLevel.ERROR, message, exception=exception)
    logger.error(message)


def _report_warning(message: str) -> None:
    """上报告警到 error_escalation_port（未注册时仅记日志）。"""
    port = get_error_escalation_port()
    if port is not None:
        port.report(ErrorLevel.WARN, message)
    logger.warning(message)


def parse_candidate_manifests(
    plugin_dirs: list[Path],
) -> tuple[CandidateMap, SkipMap]:
    """扫描候选插件目录，解析 manifest v3，提取 dependencies。

    逐目录读 manifest.json/_manifest.json → ManifestV3.model_validate →
    校验自依赖/ID 格式/去重/id 唯一性。

    Args:
        plugin_dirs: 候选插件目录路径列表

    Returns:
        (候选插件映射, 解析失败跳过清单)
    """
    candidates: CandidateMap = {}
    skips: SkipMap = {}
    seen_ids: dict[str, Path] = {}

    for plugin_dir in plugin_dirs:
        # 查找 manifest 文件（manifest.json 或 _manifest.json）
        manifest_path = plugin_dir / "manifest.json"
        if not manifest_path.is_file():
            manifest_path = plugin_dir / "_manifest.json"
        if not manifest_path.is_file():
            logger.debug("目录 %s 未发现 manifest，跳过", plugin_dir)
            continue

        # 读取 + JSON 解析
        try:
            raw = manifest_path.read_text(encoding="utf-8")
            raw_dict = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            plugin_key = f"dir:{plugin_dir.name}"
            skips[plugin_key] = f"manifest 解析失败: {exc}"
            _report_error(f"插件目录 {plugin_dir} manifest 解析失败: {exc}", exc)
            continue

        # ManifestV3 schema 验证
        try:
            manifest = ManifestV3.model_validate(raw_dict)
        except ValidationError as exc:
            plugin_key = f"dir:{plugin_dir.name}"
            skips[plugin_key] = f"manifest 校验失败: {exc}"
            _report_error(f"插件目录 {plugin_dir} manifest 校验失败: {exc}", exc)
            continue

        plugin_id = manifest.id

        # manifest id 唯一性校验（dsh 建议项 2：重复 id 两者均跳过）
        if plugin_id in seen_ids:
            existing_dir = seen_ids[plugin_id]
            skips[plugin_id] = f"id 重复: 目录 {existing_dir} 与 {plugin_dir}"
            _report_error(
                f"插件 id 重复: {plugin_id}，目录 {existing_dir} 与 {plugin_dir}，两者均跳过"
            )
            # 从候选集移除先前的同名插件
            candidates.pop(plugin_id, None)
            # 标记先前目录也跳过（用 dir key 避免覆盖）
            prev_key = f"dir:{existing_dir.name}"
            skips[prev_key] = f"id 重复: 目录 {existing_dir} 与 {plugin_dir}"
            continue
        seen_ids[plugin_id] = plugin_dir

        # 自依赖校验（spec 5.1.1 规则 3）
        if plugin_id in manifest.dependencies:
            skips[plugin_id] = "声明了自依赖"
            _report_error(f"插件 {plugin_id} 声明了自依赖")
            candidates.pop(plugin_id, None)
            continue

        # 依赖 ID 格式校验（spec 5.1.1 规则 5）
        invalid_deps = [
            dep for dep in manifest.dependencies if not _PLUGIN_ID_PATTERN.match(dep)
        ]
        if invalid_deps:
            skips[plugin_id] = f"依赖 ID 格式非法: {invalid_deps}"
            _report_error(f"插件 {plugin_id} 依赖 ID 格式非法: {invalid_deps}")
            continue

        # 重复依赖去重（spec 5.1.1 规则 4）
        if len(manifest.dependencies) != len(set(manifest.dependencies)):
            manifest = manifest.model_copy(
                update={"dependencies": list(dict.fromkeys(manifest.dependencies))}
            )

        candidates[plugin_id] = (plugin_dir, manifest)

    return candidates, skips


def build_dependency_graph(
    candidates: CandidateMap,
) -> tuple[DependencyGraph, SkipMap]:
    """构建依赖图，识别缺失依赖并跳过声明方。

    先 add_node 确保每个候选插件节点存在，再逐插件检查 depends_on：
    - 依赖在候选集中 → add_relation（STRONG）
    - 依赖不在候选集中 → 跳过声明方 + 告警（不 add_relation，避免自动加缺失节点）

    Args:
        candidates: 候选插件映射

    Returns:
        (依赖图, 缺失依赖跳过清单)
    """
    graph = DependencyGraph()
    skips: SkipMap = {}

    # 先添加所有候选节点
    for plugin_id in candidates:
        graph.add_node(plugin_id)

    # 逐插件检查依赖
    for plugin_id, (_, manifest) in candidates.items():
        for dep_id in manifest.dependencies:
            if dep_id not in candidates:
                # 缺失依赖：跳过声明方 + 告警（不 add_relation）
                if plugin_id not in skips:
                    skips[plugin_id] = f"依赖 {dep_id} 未发现"
                    _report_warning(
                        f"插件 {plugin_id} 跳过：依赖 {dep_id} 未发现"
                    )

    # 对可满足依赖添加边（跳过的插件不添加边）
    for plugin_id, (_, manifest) in candidates.items():
        if plugin_id in skips:
            continue
        for dep_id in manifest.dependencies:
            if dep_id in candidates:
                graph.add_relation(
                    DependencyRelation(
                        dependent=plugin_id,
                        dependency=dep_id,
                        kind=DependencyKind.STRONG,
                    )
                )

    return graph, skips


def propagate_skips(
    candidates: CandidateMap,
    initial_skips: SkipMap,
) -> SkipMap:
    """迭代传播跳过：依赖被跳过插件的插件也跳过。

    重复检查直到无新跳过项收敛（有限步，最多传播 N 轮，N=候选插件数）。

    Args:
        candidates: 候选插件映射
        initial_skips: 初始跳过清单

    Returns:
        完整跳过清单（含级联跳过）
    """
    skips: SkipMap = dict(initial_skips)

    # 迭代传播
    changed = True
    while changed:
        changed = False
        for plugin_id, (_, manifest) in candidates.items():
            if plugin_id in skips:
                continue
            for dep_id in manifest.dependencies:
                if dep_id in skips:
                    skips[plugin_id] = f"依赖 {dep_id} 级联跳过"
                    _report_warning(
                        f"插件 {plugin_id} 跳过：依赖 {dep_id} 级联跳过"
                    )
                    changed = True
                    break

    return skips


@dataclass(frozen=True)
class ActivationPlan:
    """激活计划——拓扑波次 + 跳过清单 + 环错误。

    不可变数据结构（frozen=True），承载依赖解析结果。

    Attributes:
        waves: 激活波次，waves[i] = 第 i 波插件 ID 列表（同波次字母序）
        skipped: 跳过清单，key=插件 ID, value=跳过原因
        cycle_errors: 环错误，每个子列表为一个环的插件 ID 序列
        candidate_dirs: 插件 ID → 目录路径映射（供 spawn 用）
    """

    waves: list[list[str]]
    skipped: dict[str, str]
    cycle_errors: list[list[str]]
    candidate_dirs: dict[str, Path] = field(default_factory=dict)

    def is_activatable(self, plugin_id: str) -> bool:
        """插件是否可激活（在某个波次中且不在跳过清单中）。"""
        if plugin_id in self.skipped:
            return False
        return any(plugin_id in wave for wave in self.waves)

    def activation_order(self) -> list[str]:
        """波次展平为线性序（波次内字母序）。"""
        result: list[str] = []
        for wave in self.waves:
            result.extend(wave)
        return result


def compute_activation_plan(
    plugin_dirs: list[Path],
) -> ActivationPlan:
    """完整依赖解析 + 拓扑排序，返回激活计划。

    组合 parse → build → propagate → compute_waves → 环检测。

    Args:
        plugin_dirs: 候选插件目录路径列表

    Returns:
        ActivationPlan（含波次/跳过/环错误/目录映射）
    """
    # 1. 解析候选 manifest
    candidates, parse_skips = parse_candidate_manifests(plugin_dirs)

    # 2. 构建依赖图 + 识别缺失依赖
    graph, missing_skips = build_dependency_graph(candidates)

    # 3. 合并跳过清单 + 传播级联跳过
    all_skips: SkipMap = {}
    all_skips.update(parse_skips)
    all_skips.update(missing_skips)
    all_skips = propagate_skips(candidates, all_skips)

    # 4. 计算可激活子图（剔除跳过项）
    # 只保留以插件 ID 为 key 的跳过项（parse 阶段的 dir:xxx key 不是合法插件 ID）
    skipped_plugins = {
        pid: reason
        for pid, reason in all_skips.items()
        if pid in candidates
    }

    activatable = set(candidates.keys()) - set(skipped_plugins.keys())
    cycle_errors: list[list[str]] = []

    # 5. Kahn 拓扑分波 + 环检测（while 循环迭代剔除环内节点直到无环）
    waves: list[list[str]] = []
    remaining = set(activatable)
    while remaining:
        try:
            waves = graph.compute_waves(node_filter=remaining)
            break
        except DependencyCycleError as exc:
            cycle_nodes = exc.cycle
            cycle_errors.append(cycle_nodes)
            _report_error(
                f"循环依赖: {' → '.join(cycle_nodes)} → {cycle_nodes[0]}"
            )
            # 环内插件加入跳过清单，从剩余集合剔除
            for node in cycle_nodes:
                skipped_plugins[node] = "循环依赖"
            remaining -= set(cycle_nodes)

    # 6. 构造目录映射
    candidate_dirs = {
        plugin_id: plugin_dir
        for plugin_id, (plugin_dir, _) in candidates.items()
    }

    return ActivationPlan(
        waves=waves,
        skipped=skipped_plugins,
        cycle_errors=cycle_errors,
        candidate_dirs=candidate_dirs,
    )