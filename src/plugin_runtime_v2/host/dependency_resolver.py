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

# ⚠️ 2026-10-17 (ii)：这里原有一条**从 reason 文案里正则抠目录名**的提取
# （`_DIR_IN_REASON = re.compile(r"目录 ([^ 与\n]+)")`）——**已删除**。
# 病根：文案是给人看的，"目录 <路径>" 一改（措辞/格式/语言）提取就**静默变空**，
# 而"空"与"真没有坏插件"在**值上不可分** ⇒ 覆盖断言看不出缺口（"扫描器看不见自己的瞎"）。
# 现在目录名走结构化字段 `RejectEntry.dir_path`（见下），**任何判定都不解析文案**。


# 类型别名
CandidateMap = dict[str, tuple[Path, ManifestV3]]
"""候选插件映射：插件 ID → (目录路径, manifest 实例)"""

SkipMap = dict[str, str]
"""跳过清单：插件 ID → 跳过原因"""


@dataclass(frozen=True)
class RejectEntry:
    """解析阶段被拒的**一条结构化记录**（第三栏的元素，2026-10-17 (ii) 起）。

    (ii) 之前这里是一个**裸字符串** reason，目录名靠**正则从文案里抠**
    （`_DIR_IN_REASON` 匹配 `目录 <路径>`）——**文案一改，提取就静默变空**，而"空"与
    "真没有坏插件"在**值上不可分** ⇒ 覆盖断言看不出缺口（"扫描器看不见自己的瞎"）。
    现在拆成字段：目录名是**登记下来的事实**，不是从字符串里抠出来/猜出来的。

    Attributes:
        reason: 人类可读的拒绝原因。⚠️ **给人看的**：为不丢投影面信息，它可能仍带着
            目录路径（与旧文案逐字一致），但**任何判定/提取都不许解析它**。
        dir_path: 被拒的插件**目录**（解析阶段如实登记的那一个；不从插件 ID 反推——
            目录名默认是 `id.replace(".", "_")`，但用户可以给任意目录名）。
            ⚠️ **必填**：每条拒绝都发生在某个具体目录上 ⇒ 留空等于给"提取静默变空"
            再留一扇门（见 `rejected_dir_names` 的 `expect_nonempty`）。
    """

    reason: str
    dir_path: Path

    @property
    def dir_name(self) -> str:
        """目录名（`dir_path` 末段）——覆盖断言认的就是它。"""
        return self.dir_path.name


RejectMap = dict[str, RejectEntry]
"""拒绝清单（**第三栏**）：key → `RejectEntry`（**结构化**：原因 + 目录）。

key 是**投影键**：拿得到 id 时是真插件 ID（id 重复 / 自依赖两支，已过 schema），
拿不到时是 `dir:<目录名>`（manifest 读不出 / 不过 schema / 依赖 ID 格式非法）。

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
    - **rejected**：`plan.rejected` 里每条的 `RejectEntry.dir_path`（解析阶段被拒：
      manifest 读不出 / 不过 schema / id 重复 / 自依赖 / 依赖 ID 格式非法）
      —— **读结构化字段，不解析文案**

    ⚠️ 这是**全称**断言，不是抽样：`plugin_dirs` 里**每个**目录都要被上面三栏之一收下。
    三栏都没收它 ⇒ 它**不在投影面里**，而它确实存在过——**这就是值域缺口**
    （"空间本身没覆盖全部结果"，**不是**"抽到 0 条"）。

    ⚠️⚠️ **边界（2026-10-17 (ii) 写明）：这是"值域**覆盖**"，不是"值域**相等**"。**
    - **覆盖**（本函数声称的）：**每个已知类别都有落点**——`plugin_dirs` 里**每一个**
      目录都被上面三栏之一收下；
    - **相等**（本函数**不**声称的）：**反方向也成立**——三栏里的每一项都必须来自
      `plugin_dirs`、且不得有第四栏。下面**没有**检查：① `plan.rejected` 里混进了
      不属于本次扫描的键；② `plan.candidate_dirs` / `plan.skipped` 多出 `plugin_dirs`
      之外的项。⇒ **相等不声称**（要宣称相等，得把"三栏 ⊆ 扫描结果"那半边也断言上，
      本轮不做——覆盖只需要"没有看不见的坏插件"，那才是这条缺陷的正身）。

    ⚠️ **为什么不能拿 `plan.rejected` 的 key 去推目录名**：
    key 在"id 重复 / 自依赖"两支里是**真插件 ID**（已过 schema），而插件目录名默认是
    `id.replace(".", "_")` —— **反推是在猜**（`badnodeid` 会被猜成 `org_badnodeid`，
    于是断言把**真实覆盖**误报成缺口）。**断言不许猜**：目录名由解析阶段写进
    `RejectEntry.dir_path`，是**登记下来的事实**（`None` 时也从同一处现算）。

    Args:
        plan: 待检查的激活计划
        plugin_dirs: 解析器实际看到的候选目录（用 `scan_plugin_dirs` 取，保证同一把尺子）
        rejected_dir_names: 被拒**目录名** → 原因。`None` 时直接从 `plan.rejected`
            的结构化字段现算（两条路径**同源**：都不解析文案）

    Returns:
        未被任何一栏覆盖的目录名列表（空列表 = 全覆盖）。
    """
    if rejected_dir_names is None:
        # 结构化派生（2026-10-17 (ii)）：目录名一律读 `RejectEntry.dir_path`——
        # **不解析 reason 文案、不从插件 ID 反推**。真 ID 的 key 也照样给得出目录。
        rejected_names = {entry.dir_name for entry in plan.rejected.values()}
    else:
        rejected_names = set(rejected_dir_names)

    # ⚠️ 统一取末段（`Path.name`）：显式传入的目录名可能是完整路径（旧调用方式），
    # 归一化后两者才能比。不归一化就会把路径当目录名、断言直接误报。
    covered_dirs = {Path(name).name for name in rejected_names}
    covered_dirs |= {p.name for p in plan.candidate_dirs.values()}
    covered_dirs |= set(plan.skipped)
    missing: list[str] = []
    for plugin_dir in plugin_dirs:
        if plugin_dir.name in covered_dirs:
            continue
        missing.append(plugin_dir.name)
    return missing


def rejected_dir_names(
    plan: "ActivationPlan",
    *,
    expect_nonempty: bool = False,
) -> dict[str, str]:
    """取"被拒的是哪些目录"——**读结构化字段，绝不解析文案、绝不从 ID 反推**。

    2026-10-17 (ii) 之前这里靠**正则从 reason 文案里抠**目录名（`目录 <路径>`），
    三条"来源"（`dir:` 前缀 key / reason 里那句路径 / 上一目录）本质都是**字符串**。
    现在来源只有一个：`RejectEntry.dir_path`（解析阶段**如实登记**的那一个）——
    **文案怎么写都与提取无关**。

    ⚠️ `expect_nonempty=True`（**断言非空**，同案 (b)）：调用方**知道这里应该有
    rejected** 时，**0 条就是红**——那不是"没有坏插件"，是"提取读不到"。否则换了
    字段、提取静默变空之后，"空"与"真没有"在**值上不可分** ⇒ 覆盖断言看不出缺口
    （"扫描器看不见自己的瞎"这个病还在）。

    ⚠️ **为什么不能从插件 ID 反推目录名**：目录名默认是 `id.replace(".", "_")`，
    但用户可以给任意目录名（实测反例：目录 `badnodeid` 里放 id `org.badnodeid` 的
    自依赖 manifest ⇒ 反推得到 `org_badnodeid`，与真目录名不符 ⇒ 把**真实覆盖**
    误报成缺口，并让 `compute_activation_plan` 对**合法**输入抛异常）。
    断言**不许猜**：只认解析器写下来的名字。

    单独成函数是为了**生产代码与测试共用同一份提取逻辑**——两处各写一遍就会漂。

    Args:
        plan: 待提取的激活计划
        expect_nonempty: `True` 时，**提取到 0 条 ⇒ 抛 ValueError**（"应该有却 0 条"）。

    Returns:
        目录名 → 原因（判据只用 key；value 仅供展示/调试）

    Raises:
        ValueError: `expect_nonempty=True` 且提取到 0 条。
    """
    names: dict[str, str] = {entry.dir_name: entry.reason for entry in plan.rejected.values()}
    if expect_nonempty and not names:
        raise ValueError(
            "拒绝栏提取到 0 条，但调用方声明这里**应该有 rejected** ⇒ 这不是"
            "'没有坏插件'，是提取读不到（字段换了/结构不对）。"
            "空与'真没有'在值上不可分，静默给空会让覆盖断言看不出缺口。"
            f"（plan.rejected 现有 {len(plan.rejected)} 条）"
        )
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


# ⚠️ 接口变更：返回 2 元组 → 3 元组（仓内**全部**解包点已同步——本次实测 21 处，
#    复算 `rg '= parse_candidate_manifests\('`；仓外调用方未通告；
#    若将来插件 SDK 面暴露它 ⇒ 必须走版本策略）
def parse_candidate_manifests(
    plugin_dirs: list[Path],
) -> tuple[CandidateMap, SkipMap, RejectMap]:
    """扫描候选插件目录，解析 manifest v3，提取 dependencies。

    逐目录读 manifest.json/_manifest.json → ManifestV3.model_validate →
    校验自依赖/ID 格式/去重/id 唯一性。

    ⚠️ **两类结果分栏**（2026-10-17 值域修复）：解析/校验失败的目录**同时**记两份
    ——`skips`(旧口径，`dir:<目录名>` key）与 `rejects`(新口径，**投影面用**；
    每条形如 `RejectEntry(reason, dir_path)`，2026-10-17 (ii) 起结构化）。旧口径的
    `dir:` key 在 `compute_activation_plan` 的 `pid in candidates` 过滤里必然被丢掉
    ⇒ 只留旧口径 = 这类插件"不存在"。两份都要给：**旧的别动（兼容），新的补上（覆盖）**。
    ⚠️ 解析阶段的**五支**拒绝都必须落 `rejects`：manifest 读不出 / 不过 schema /
    依赖 ID 格式非法 / id 重复 / 自依赖 —— **漏一支，那一支就从投影面消失**
    （见 `_check_value_domain` 的全称覆盖断言）。

    Args:
        plugin_dirs: 候选插件目录路径列表

    Returns:
        (候选插件映射, 解析失败跳过清单, 解析阶段拒绝清单[`RejectEntry` 结构化])
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
            rejects[plugin_key] = RejectEntry(reason=reason, dir_path=plugin_dir)
            _report_error(f"插件目录 {plugin_dir} manifest 解析失败: {exc}", exc)
            continue

        # ManifestV3 schema 验证
        try:
            manifest = ManifestV3.model_validate(raw_dict)
        except ValidationError as exc:
            plugin_key = f"dir:{plugin_dir.name}"
            reason = f"manifest 校验失败: {exc}"
            skips[plugin_key] = reason
            rejects[plugin_key] = RejectEntry(reason=reason, dir_path=plugin_dir)
            _report_error(f"插件目录 {plugin_dir} manifest 校验失败: {exc}", exc)
            continue

        plugin_id = manifest.id

        # manifest id 唯一性校验（dsh 建议项 2：重复 id 两者均跳过）
        if plugin_id in seen_ids:
            existing_dir = seen_ids[plugin_id]
            reason = f"id 重复: 目录 {existing_dir} 与 {plugin_dir}"
            skips[plugin_id] = reason
            # 当前目录：拿得到 id（已过 schema），按 id 记进拒绝清单（带目录名）
            rejects[plugin_id] = RejectEntry(
                reason=f"id 重复: 当前目录 {plugin_dir} 与先前目录 {existing_dir}",
                dir_path=plugin_dir,
            )
            _report_error(
                f"插件 id 重复: {plugin_id}，目录 {existing_dir} 与 {plugin_dir}，两者均跳过"
            )
            # 从候选集移除先前的同名插件
            candidates.pop(plugin_id, None)
            # 标记先前目录也跳过（用 dir key 避免覆盖）
            prev_key = f"dir:{existing_dir.name}"
            skips[prev_key] = reason
            rejects[prev_key] = RejectEntry(reason=reason, dir_path=existing_dir)
            continue
        seen_ids[plugin_id] = plugin_dir

        # 自依赖校验（spec 5.1.1 规则 3）
        if plugin_id in manifest.dependencies:
            # ⚠️ 与 id 重复同理：这里 key 是**真 id**，但插件已被移出 candidates
            # ⇒ 若只记 skips，`pid in candidates` 会把这一条同样过滤掉。
            # 记 rejects 才是"具名拒绝"。⚠️ reason 里**仍带目录**（给人看的），
            # 但覆盖断言**不读文案**——它读 `dir_path`（结构化字段，2026-10-17 (ii)），
            # 绝不从插件 ID 反推（见 rejected_dir_names）。
            skips[plugin_id] = "声明了自依赖"
            rejects[plugin_id] = RejectEntry(
                reason=f"声明了自依赖（manifest 自相矛盾）: 目录 {plugin_dir}",
                dir_path=plugin_dir,
            )
            _report_error(f"插件 {plugin_id} 声明了自依赖")
            candidates.pop(plugin_id, None)
            continue

        # 依赖 ID 格式校验（spec 5.1.1 规则 5）
        invalid_deps = [
            dep for dep in manifest.dependencies if not _PLUGIN_ID_PATTERN.match(dep)
        ]
        if invalid_deps:
            reason = f"依赖 ID 格式非法: {invalid_deps}"
            skips[plugin_id] = reason
            # ⚠️ 2026-10-17 (ii) 补记：本支**同样是解析阶段被拒**（这份 manifest 不成立），
            # 但旧实现只记 `skips`——而本支**不进 candidates**（上面就 continue 了）⇒
            # 第 4 步 `pid in candidates` 必然把它滤掉 ⇒ 它落在三栏之外 ⇒ 覆盖断言把它
            # 报成"值域缺口"，对**合法**输入当场抛 ValueError（实测现场：某个插件把
            # 依赖 ID 打错 ⇒ 整条依赖解析降级为字母序激活）。与另外四支对齐：拒绝栏
            # 必须有它（具名 + 目录），否则"看不见自己"的是断言本身。
            rejects[plugin_id] = RejectEntry(
                reason=f"依赖 ID 格式非法: {invalid_deps}（目录 {plugin_dir}）",
                dir_path=plugin_dir,
            )
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
            value=`RejectEntry`（**结构化**：原因 + 目录，2026-10-17 (ii)）。
            ⚠️ 与 `skipped` 分开是**故意的**：`skipped` 的 key 承诺是合法插件 ID，
            而 `rejected` 里可能有拿不到 id 的目录（用 `dir:` 前缀）⇒ 混进
            `skipped` 会污染那份契约（值是假的"插件 ID"）。
    """

    waves: list[list[str]]
    skipped: dict[str, str]
    cycle_errors: list[list[str]]
    candidate_dirs: dict[str, Path] = field(default_factory=dict)
    rejected: RejectMap = field(default_factory=dict)

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
            坏插件从状态面里消失。⚠️ 该断言是**覆盖**、**不是相等**（反方向不声称，
            见 `_check_value_domain` 的边界段）。
        ValueError: 拒绝栏**提取到 0 条**而解析阶段确实登记过拒绝
            （`expect_nonempty`）——这是"应该有却 0 条"的**红**，不是静默。
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
    #    ⚠️ **覆盖 ≠ 相等**（2026-10-17 (ii) 写明）：这里只声称"解析器看到过的每个目录
    #       都有落点"，**不**声称"三栏里的每一项都来自本次扫描"（反方向不检查）。
    #    ⚠️ 三栏的"目录名"由**解析阶段如实登记**（candidate_dirs 的值 + `RejectEntry`
    #       的 `dir_path`），不从插件 ID 反推——那是猜（`badnodeid` ≠ `org_badnodeid`）。
    #    ⚠️ `expect_nonempty=bool(rejected_plugins)`：解析阶段**确实登记过**拒绝条目
    #       ⇒ 提取出来必须非空；0 条 = 提取读不到（字段换了）⇒ **当场出声**
    #       （"应该有 rejected 却 0 条"必须红——同案 (b)）。
    missing = _check_value_domain(
        plan,
        plugin_dirs,
        rejected_dir_names(plan, expect_nonempty=bool(rejected_plugins)),
    )
    if missing:
        raise ValueError(
            "值域缺口：以下候选目录既不在波次/跳过清单、也不在拒绝清单里 ⇒ "
            f"它们会从状态面消失：{missing}（共 {len(missing)} 个）。"
            "解析器的每个产出都必须落进 activated / skipped / rejected 三栏之一。"
        )

    return plan
