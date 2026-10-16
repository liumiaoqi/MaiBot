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

# 拒绝原因里的"目录名"提取（形如 `... 目录 C:\...\plugins\badnodeid 与 ...`）
# ⚠️ 只用来读**解析器自己写下的**目录名，不从插件 ID 反推（见 rejected_dir_names）
_DIR_IN_REASON = re.compile(r"目录 ([^ 与\n]+)")


# 类型别名
CandidateMap = dict[str, tuple[Path, ManifestV3]]
"""候选插件映射：插件 ID → (目录路径, manifest 实例)"""

SkipMap = dict[str, str]
"""跳过清单：插件 ID → 跳过原因"""

RejectMap = dict[str, str]
"""拒绝清单（**第三栏**）：插件 ID（或 `dir:<目录名>`）→ 拒绝原因。

与 SkipMap 的区别是**结论不同，不是程度不同**：
- **skipped**：解析通过、进入依赖图与波次编排之后**才**被拒（依赖缺失/级联/循环依赖/
  spawn 失败）——"插件本身是好的，这一轮没能上"。
- **rejected**：**解析（parse）阶段就被拒**（manifest 读不出来 / schema 不过 / id 重复 /
  自依赖 / 依赖 ID 格式非法）——"这一份 manifest 不成立"，**从未进入依赖图**。

⚠️ **值域纪律（2026-10-17 立项）**：解析器**看到过的**每个插件目录，必须落进
`candidates`（→ 波次，可激活）／`skipped`／`rejected` **三者之一**；一个都不落 = 投影面
"它不存在"，而**它其实是坏的**。历史上 `dir:<目录名>` 的 key 被
`compute_activation_plan` 的 `pid in candidates` 过滤掉，正是这样掉出值域的
（详见 `_check_value_domain` 与 `ActivationPlan.rejected`）。
"""


def scan_plugin_dirs(plugins_root: Path) -> list[Path]:
    """扫描插件根目录下的候选目录（**解析器的视野**，字母序）。

    判据：`d.is_dir()` 且目录里有 `manifest.json` 或 `_manifest.json`。
    这个判据是**解析器与覆盖断言共用的同一个**——断言要判"解析器看到过的插件都在三栏里"，
    就必须用**和解析器同一把尺子**量"看到过"（否则断言自己会漏掉目录）。

    Args:
        plugins_root: 插件根目录（如 plugins-v2/）

    Returns:
        候选目录路径列表（字母序）；根目录不存在或没有候选时返回空列表。
    """
    if not plugins_root.is_dir():
        return []
    return sorted(
        d for d in plugins_root.iterdir()
        if d.is_dir() and ((d / "manifest.json").is_file() or (d / "_manifest.json").is_file())
    )


def _check_value_domain(
    plan: "ActivationPlan",
    plugin_dirs: list[Path],
    rejected_dir_names: dict[str, str] | None = None,
) -> list[str]:
    """覆盖断言：**解析器看到过的每个插件，必须落进三栏之一**。

    全称断言（lead 2026-10-17 给的判据）：
    > 每个被解析器看到过的插件，必须落进 `activated` / `skipped` / 具名 `rejected` 三栏之一。

    落到本函数就是一次**值域覆盖检查**（`plan` 的值域必须覆盖解析器的全部产出）：

    - **activated**：解析成功的**目录**（就在 `plan.candidate_dirs` 的**值**里）
    - **skipped**：`plan.skipped` 的 key
    - **rejected**：`rejected_dir_names` 登记的**目录名**（解析阶段被拒：
      manifest 读不出 / 不过 schema / id 重复 / 自依赖）

    ⚠️ 这是**全称**断言，不是抽样：`plugin_dirs` 里**每个**目录都要被上面三栏之一收下。
    三栏都没收它 ⇒ 它**不在投影面里**，而它确实存在过——**这就是值域缺口**
    （"空间本身没覆盖全部结果"，**不是**"抽到 0 条"）。

    ⚠️ **为什么单独要 `rejected_dir_names` 而不是拿 `plan.rejected` 的 key 去推目录名**：
    `rejected` 的 key 在"id 重复 / 自依赖"两支里是**真插件 ID**（已过 schema），而插件
    目录名默认是 `id.replace(".", "_")` —— **反推是在猜**（`badnodeid` 会被猜成
    `org_badnodeid`，于是断言把**真实覆盖**误报成缺口）。**断言不许猜**：目录名由解析
    阶段如实登记。`None` 时退回只看 `dir:` 前缀 key（旧调用方式的兼容路径）。

    Args:
        plan: 待检查的激活计划
        plugin_dirs: 解析器实际看到的候选目录（用 `scan_plugin_dirs` 取，保证同一把尺子）
        rejected_dir_names: 被拒目录名 → 原因（`parse_candidate_manifests` 之外由
            `compute_activation_plan` 从 `plan.rejected` 的 `dir:` key 现算）

    Returns:
        未被任何一栏覆盖的目录名列表（空列表 = 全覆盖）。
    """
    rejected_names = set(rejected_dir_names or ())
    if rejected_dir_names is None:
        # 兼容路径：`dir:` 前缀 key 就是目录名；真 ID 的 key 推不出目录名，只能靠
        # candidates 一栏（id 重复/自依赖那两支的**当前**目录已从 candidates 移除
        # ⇒ 走这条路径会被报成缺口，这正是"不许猜"的代价，宁可出声也不静默放过）
        rejected_names = {
            key[len("dir:"):] for key in plan.rejected if key.startswith("dir:")
        }

    # ⚠️ 拒绝栏拿到的是**解析阶段写下的原文**：`dir:` 的 key 是裸目录名，而 reason 里
    # 那句 `目录 <plugin_dir>` 是**完整路径** ⇒ 统一取末段（`Path.name`，仍是"读下来
    # 的"而不是"推出来的"）。不归一化就会把路径当目录名、断言直接误报。
    covered_dirs = {Path(name).name for name in rejected_names}
    covered_dirs |= {p.name for p in plan.candidate_dirs.values()}
    covered_dirs |= set(plan.skipped)
    missing: list[str] = []
    for plugin_dir in plugin_dirs:
        if plugin_dir.name in covered_dirs:
            continue
        missing.append(plugin_dir.name)
    return missing


def rejected_dir_names(plan: "ActivationPlan") -> dict[str, str]:
    """取"被拒的是哪些目录"——**只读解析器自己写下的具名信息，绝不从 ID 反推**。

    三条来源（都对得上解析阶段真正登记过的字段）：

    1. **`dir:` 前缀 key** —— 解析/校验失败这一支，键就是 `dir:<目录名>`；
    2. **`Path.name`** —— 这一支的 value 是 `f"... {plugin_dir} ..."`（真路径），
       路径本身**带**目录名（不猜：那是解析阶段打印的那一份）；
    3. **`dir:` 的 value** —— id 重复那一支里"先前目录"也是这样具名的
       （`prev_key = f"dir:{existing_dir.name}"`）。

    ⚠️ **为什么不能从插件 ID 反推目录名**：目录名默认是 `id.replace(".", "_")`，
    但用户可以给任意目录名（实测反例：目录 `badnodeid` 里放 id `org.badnodeid` 的
    自依赖 manifest ⇒ 反推得到 `org_badnodeid`，与真目录名不符 ⇒ 把**真实覆盖**
    误报成缺口，并让 `compute_activation_plan` 对**合法**输入抛异常）。
    断言**不许猜**：只认解析器写下来的名字。

    单独成函数是为了**生产代码与测试共用同一份提取逻辑**——两处各写一遍就会漂。
    """
    names: dict[str, str] = {}
    for key, reason in plan.rejected.items():
        if key.startswith("dir:"):
            names[key[len("dir:"):]] = reason
        for match in _DIR_IN_REASON.finditer(reason):
            names[match.group(1)] = reason
    return names


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
) -> tuple[CandidateMap, SkipMap, RejectMap]:
    """扫描候选插件目录，解析 manifest v3，提取 dependencies。

    逐目录读 manifest.json/_manifest.json → ManifestV3.model_validate →
    校验自依赖/ID 格式/去重/id 唯一性。

    ⚠️ **两类结果分栏**（2026-10-17 值域修复）：解析/校验失败的目录**同时**记两份
    ——`skips`(旧口径，`dir:<目录名>` key）与 `rejects`(新口径，**投影面用**）。
    旧口径的 `dir:` key 在 `compute_activation_plan` 的 `pid in candidates` 过滤里
    必然被丢掉 ⇒ 只留旧口径 = 这类插件"不存在"。两份都要给：**旧的别动（兼容），
    新的补上（覆盖）**。

    Args:
        plugin_dirs: 候选插件目录路径列表

    Returns:
        (候选插件映射, 解析失败跳过清单, 解析失败拒绝清单)
    """
    candidates: CandidateMap = {}
    skips: SkipMap = {}
    rejects: RejectMap = {}
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
            reason = f"manifest 解析失败: {exc}"
            skips[plugin_key] = reason
            rejects[plugin_key] = reason
            _report_error(f"插件目录 {plugin_dir} manifest 解析失败: {exc}", exc)
            continue

        # ManifestV3 schema 验证
        try:
            manifest = ManifestV3.model_validate(raw_dict)
        except ValidationError as exc:
            plugin_key = f"dir:{plugin_dir.name}"
            reason = f"manifest 校验失败: {exc}"
            skips[plugin_key] = reason
            rejects[plugin_key] = reason
            _report_error(f"插件目录 {plugin_dir} manifest 校验失败: {exc}", exc)
            continue

        plugin_id = manifest.id

        # manifest id 唯一性校验（dsh 建议项 2：重复 id 两者均跳过）
        if plugin_id in seen_ids:
            existing_dir = seen_ids[plugin_id]
            reason = f"id 重复: 目录 {existing_dir} 与 {plugin_dir}"
            skips[plugin_id] = reason
            # 当前目录：拿得到 id（已过 schema），按 id 记进拒绝清单（带目录名）
            rejects[plugin_id] = f"id 重复: 当前目录 {plugin_dir} 与先前目录 {existing_dir}"
            _report_error(
                f"插件 id 重复: {plugin_id}，目录 {existing_dir} 与 {plugin_dir}，两者均跳过"
            )
            # 从候选集移除先前的同名插件
            candidates.pop(plugin_id, None)
            # 标记先前目录也跳过（用 dir key 避免覆盖）
            prev_key = f"dir:{existing_dir.name}"
            skips[prev_key] = reason
            rejects[prev_key] = reason
            continue
        seen_ids[plugin_id] = plugin_dir

        # 自依赖校验（spec 5.1.1 规则 3）
        if plugin_id in manifest.dependencies:
            # ⚠️ 与 id 重复同理：这里 key 是**真 id**，但插件已被移出 candidates
            # ⇒ 若只记 skips，`pid in candidates` 会把这一条同样过滤掉。
            # 记 rejects 才是"具名拒绝"。⚠️ reason 里**必须带目录**
            # （`目录 <dir.path>` 是解析器写下的具名信息）——覆盖断言只读这些
            # 由解析器自己登记的目录名，不从插件 ID 反推（见 rejected_dir_names）。
            skips[plugin_id] = "声明了自依赖"
            rejects[plugin_id] = (
                f"声明了自依赖（manifest 自相矛盾）: 目录 {plugin_dir}"
            )
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

    return candidates, skips, rejects


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
        rejected: **解析阶段被拒**清单（第三栏），key=插件 ID 或 `dir:<目录名>`,
            value=拒绝原因。⚠️ 与 `skipped` 分开是**故意的**：`skipped` 的 key 承
            诺是合法插件 ID，而 `rejected` 里可能有拿不到 id 的目录（用 `dir:` 前缀）
            ⇒ 混进 `skipped` 会污染那份契约（值是假的"插件 ID"）。
    """

    waves: list[list[str]]
    skipped: dict[str, str]
    cycle_errors: list[list[str]]
    candidate_dirs: dict[str, Path] = field(default_factory=dict)
    rejected: dict[str, str] = field(default_factory=dict)

    def is_activatable(self, plugin_id: str) -> bool:
        """插件是否可激活（在某个波次中且不在跳过清单中）。

        ⚠️ `rejected`（解析阶段被拒）**不在波次里**，故本判定对它们天然为假。
        """
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

    组合 parse → build → propagate → compute_waves → 环检测 → **值域覆盖断言**。

    ⚠️ **值域修复（2026-10-17）**：此前解析阶段用 `dir:<目录名>` 当 key 记
    `skips`，而第 4 步的 `pid in candidates` 过滤会把这些 key **全滤掉**
    ⇒ 坏 manifest 的插件既不在 `activated` 也不在 `skipped` ⇒ **状态面看不见它**
    （"值域缺口"：空间本身没覆盖全部结果，不是"抽到 0 条"）。现在解析阶段的拒绝
    另记一栏 `rejected`（**具名**，带上原因与目录名），并**当场做覆盖断言**。

    Args:
        plugin_dirs: 候选插件目录路径列表

    Returns:
        ActivationPlan（含波次/跳过/环错误/目录映射/解析阶段拒绝）

    Raises:
        ValueError: **值域缺口**——有候选目录既不在波次/跳过、也不在拒绝栏里。
            这是**全称断言**（覆盖断言）出声，不是抽样告警：宁可起不来，也不许
            坏插件从状态面里消失。
    """
    # 1. 解析候选 manifest（此时**同时**拿到 skip 与 reject 两栏）
    candidates, parse_skips, parse_rejects = parse_candidate_manifests(plugin_dirs)

    # 2. 构建依赖图 + 识别缺失依赖
    graph, missing_skips = build_dependency_graph(candidates)

    # 3. 合并跳过清单 + 传播级联跳过
    all_skips: SkipMap = {}
    all_skips.update(parse_skips)
    all_skips.update(missing_skips)
    all_skips = propagate_skips(candidates, all_skips)

    # 4. 计算可激活子图（剔除跳过项）
    # 只保留以插件 ID 为 key 的跳过项（parse 阶段的 dir:xxx key 不是合法插件 ID
    # ⇒ 在这里被丢掉；它们**不是消失**，而是落进第 7 步的 rejected 栏）
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

    # 7. 第三栏：解析阶段被拒（**值域修复 2026-10-17**）
    #    这些 key 永远不可能出现在 candidates 里（解析都没过），第 4 步的过滤
    #    必然把它们丢掉 —— 那正是"投影面看不见的坏插件"。原样带出来（具名）。
    rejected_plugins: RejectMap = dict(parse_rejects)

    plan = ActivationPlan(
        waves=waves,
        skipped=skipped_plugins,
        cycle_errors=cycle_errors,
        candidate_dirs=candidate_dirs,
        rejected=rejected_plugins,
    )

    # 8. 覆盖断言：**解析器看到过的每个插件，必须落进三栏之一**
    #    （activated=candidate_dirs 的值 / skipped / 具名 rejected）。
    #    ⚠️ 全称断言，不是抽样：缺一个就当场出声，绝不静默返回"看着齐"的计划。
    #    ⚠️ 三栏的"目录名"由**解析阶段如实登记**（can_dirs 的值 + dir: key），
    #       不从插件 ID 反推——那是猜（`badnodeid` ≠ `org_badnodeid`）。
    missing = _check_value_domain(plan, plugin_dirs, rejected_dir_names(plan))
    if missing:
        raise ValueError(
            "值域缺口：以下候选目录既不在波次/跳过清单、也不在拒绝清单里 ⇒ "
            f"它们会从状态面消失：{missing}（共 {len(missing)} 个）。"
            "解析器的每个产出都必须落进 activated / skipped / rejected 三栏之一。"
        )

    return plan
