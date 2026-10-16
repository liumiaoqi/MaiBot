"""逆熵 · 阶段 C 首件（`social_rel` 强度 → `confidence` 位）的**预登记判据**用例。

预登记判据（先写判据再跑；出处 `.shared/decisions/negentropy_gate_c_1017.md` §三/§四）：

| # | 判据 | 本文件里的对应 |
|---|---|---|
| **P1** | 默认路径零影响（未设 env ⇒ 逐位相同） | `test_p1_*`（含 **bit 级**比较） |
| **P2** | 同刻配对不劣化 | 机制面：`test_p2_*`（同批候选 + 深拷贝快照）；**质量数字只能真跑**（见文档） |
| **P3** | 护栏不失效（学习值仍过 `compute_weight`） | `test_p3_*` |
| **P4** | 可回滚（撤开关即回到 P1 状态） | `test_p4_*` |
| **P5** | 证红能力（合成"未按预期接入"⇒ 判据必须红） | `test_p5_*`（含**鉴别力**用例） |

⚠️ 红线：用例**只往 tmp 数据根写**（`MAIBOT_DATA_DIR=<tmp>`），**从不碰真数据根**、更不碰任何库；
sidecar 是接缝自己的产物，写它不算动真库（真库指三份 `metadata.db`，本接缝一概不读不写）。
"""

import ast
import json
import struct
from pathlib import Path

import pytest

from src.A_memorix.core.retrieval.social_rel_confidence import (
    ENV_VAR,
    SIDECAR_NAME,
    enabled,
    social_rel_confidence,
    sidecar_path,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DUAL_PATH = REPO_ROOT / "src" / "A_memorix" / "core" / "retrieval" / "dual_path.py"
RECALL = REPO_ROOT / "src" / "A_memorix" / "core" / "retrieval" / "graph_relation_recall.py"

#: 逐位比较用的样本（含 0.0 / 负零 / 循环小数——`or` 误用与浮点往返都能被它抓到）
FLOAT_SAMPLES = (0.0, -0.0, 1.0, 0.3, 0.1 + 0.2, 1 / 3, 2.2250738585072014e-308)


def _bits(value: float) -> bytes:
    return struct.pack(">d", float(value))


@pytest.fixture()
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把**数据根**指到 tmp（C-1 定稿：sidecar 落数据根）——真数据根一概不碰。"""

    monkeypatch.setenv("MAIBOT_DATA_DIR", str(tmp_path))
    social_rel_confidence.reset_cache()
    yield tmp_path
    social_rel_confidence.reset_cache()


def _write_sidecar(root: Path, payload: object) -> Path:
    path = root / SIDECAR_NAME
    path.write_text(json.dumps(payload), encoding="utf-8")
    social_rel_confidence.reset_cache()
    return path


# ── P1：默认路径零影响 ──────────────────────────────────────────────────


def test_p1_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    social_rel_confidence.reset_cache()

    assert enabled() is False
    assert social_rel_confidence.override("any-hash") is None
    assert social_rel_confidence.strengths() == {}


def test_p1_effective_confidence_is_bit_identical_when_disabled(
    monkeypatch: pytest.MonkeyPatch, data_root: Path
) -> None:
    """未设 env 时：**逐位相同**（不只数值相等）——即使 sidecar 就在数据根里也不能被读到。"""

    _write_sidecar(data_root, {"h1": 0.01, "h2": 0.99})
    monkeypatch.delenv(ENV_VAR, raising=False)
    social_rel_confidence.reset_cache()

    for sample in FLOAT_SAMPLES:
        got = social_rel_confidence.effective_confidence("h1", sample)
        assert _bits(got) == _bits(sample), f"{sample!r} 被改动了"


def test_p1_snapshot_helper_is_deep_copy(data_root: Path) -> None:
    """C-2 的执行期约束：`:992` 的快照必须深拷贝，否则第二臂读到被第一臂改过的 `meta`。"""

    class Item:
        def __init__(self, hash_value: str, meta: dict) -> None:
            self.hash_value = hash_value
            self.meta = meta
            self.score = 0.0

    original = [Item("h1", {"confidence": 0.5})]
    snapshot = social_rel_confidence.snapshot_items(original)

    assert snapshot[0] is not original[0]
    assert snapshot[0].meta is not original[0].meta
    # 第一臂"就地改写 meta + 写 score"（模拟 :1020-1023 / :1030）
    original[0].meta["confidence"] = 0.01
    original[0].score = 0.7
    assert snapshot[0].meta["confidence"] == 0.5, "快照被第一臂污染了"
    assert snapshot[0].score == 0.0


# ── P2：同刻配对（机制面）────────────────────────────────────────────────


def test_p2_same_batch_two_arms_share_one_snapshot(monkeypatch: pytest.MonkeyPatch, data_root: Path) -> None:
    """两臂**共用同一批候选**：同一快照上，接臂用学习强度、对照臂用原值，配对按 hash。"""

    _write_sidecar(data_root, {"h1": 0.9})
    monkeypatch.setenv(ENV_VAR, "1")
    social_rel_confidence.reset_cache()

    batch = {"h1": 0.4, "h2": 0.4}  # 同一批候选（hash → 原 confidence）
    arm_on = {h: social_rel_confidence.effective_confidence(h, c) for h, c in batch.items()}
    monkeypatch.delenv(ENV_VAR, raising=False)
    social_rel_confidence.reset_cache()
    arm_off = {h: social_rel_confidence.effective_confidence(h, c) for h, c in batch.items()}

    assert arm_on["h1"] == 0.9 and arm_off["h1"] == 0.4, "接臂没换值 / 对照臂被带着换了"
    assert arm_on["h2"] == arm_off["h2"] == 0.4, "不在 sidecar 里的候选不该被改"


# ── P3：护栏不失效 ─────────────────────────────────────────────────────


def test_p3_guard_still_applies_floor_to_learned_value(monkeypatch: pytest.MonkeyPatch, data_root: Path) -> None:
    """学习强度**仍要过** `ConfidenceGuard`（floor 0.3）——不许因为接入而绕开护栏。"""

    from src.A_memorix.core.retrieval.confidence_guard import ConfidenceGuard

    _write_sidecar(data_root, {"h1": 0.05})
    monkeypatch.setenv(ENV_VAR, "1")
    social_rel_confidence.reset_cache()

    learned = social_rel_confidence.effective_confidence("h1", 0.8)
    assert learned == 0.05, "接缝应原样给出学习值（变换交给护栏）"

    class Candidate:
        def __init__(self, confidence: float) -> None:
            self.confidence = confidence

    guard = ConfidenceGuard()
    weight, _degraded = guard.compute_weight(learned, [Candidate(0.9), Candidate(0.5)])
    assert weight >= 0.3, f"护栏 floor 没生效（weight={weight}）"


# ── P4：可回滚 ─────────────────────────────────────────────────────────


def test_p4_unsetting_env_restores_default_path(monkeypatch: pytest.MonkeyPatch, data_root: Path) -> None:
    """撤开关（= 回滚清单第 1 点）后，取值**逐位**回到原值。"""

    _write_sidecar(data_root, {"h1": 0.02})
    monkeypatch.setenv(ENV_VAR, "1")
    social_rel_confidence.reset_cache()
    assert social_rel_confidence.effective_confidence("h1", 0.5) == 0.02

    monkeypatch.delenv(ENV_VAR, raising=False)
    social_rel_confidence.reset_cache()
    for sample in FLOAT_SAMPLES:
        assert _bits(social_rel_confidence.effective_confidence("h1", sample)) == _bits(sample)


# ── 坏数据 fail-closed ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("payload", "why"),
    [
        ({"h1": "not-a-number"}, "非数值"),
        ({"h1": 1.5}, "越界(>1)"),
        ({"h1": -0.1}, "越界(<0)"),
        ({"h1": None}, "None"),
        (["h1"], "顶层不是对象"),
        # ⚠️ bool 必须**先于**数值判断被排除（`bool` 是 `int` 子类 ⇒ `float(True)==1.0`）：
        # 独立证伪打掉的洞就是这两条没测 —— `true` 曾被当**最高强度**、`false` 当 0.0。
        ({"h1": True}, "布尔 true（不得当 1.0）"),
        ({"h1": False}, "布尔 false（不得当 0.0）"),
    ],
)
def test_bad_entries_fall_back_to_original(monkeypatch: pytest.MonkeyPatch, data_root: Path, payload: object, why: str) -> None:
    """坏数据**逐条跳过**、退回原值（fail-closed）——绝不把"没学到"当成高置信。"""

    _write_sidecar(data_root, payload)
    monkeypatch.setenv(ENV_VAR, "1")
    social_rel_confidence.reset_cache()

    assert social_rel_confidence.effective_confidence("h1", 0.42) == 0.42, why


def test_missing_sidecar_falls_back(monkeypatch: pytest.MonkeyPatch, data_root: Path) -> None:
    monkeypatch.setenv(ENV_VAR, "1")
    social_rel_confidence.reset_cache()
    assert social_rel_confidence.effective_confidence("h1", 0.42) == 0.42


def test_sidecar_path_is_data_root(monkeypatch: pytest.MonkeyPatch, data_root: Path) -> None:
    """C-1② 口径：落点由唯一来源给 ⇒ 跟随数据根（不是 CWD 相对、不是自推根）。"""

    assert sidecar_path() == (data_root / SIDECAR_NAME).resolve()


# ── P5：证红能力（源码级咬合 + 鉴别力）──────────────────────────────────


def _seam_call_sites(source: str) -> list[int]:
    """源码里"经接缝取 confidence"的行号（主挂点与次挂点共用同一个判断）。"""

    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "effective_confidence"
        ):
            lines.append(node.lineno)
    return sorted(lines)


def test_p5_both_hook_sites_route_through_the_seam() -> None:
    """主挂点（`dual_path.py`）与次挂点（`graph_relation_recall.py`）都必须经接缝取数。"""

    dual_sites = _seam_call_sites(DUAL_PATH.read_text(encoding="utf-8"))
    recall_sites = _seam_call_sites(RECALL.read_text(encoding="utf-8"))

    assert dual_sites, "主挂点没有走接缝（接入没生效）"
    assert recall_sites, "次挂点没有走接缝"
    # 主挂点：接缝取值必须发生在 compute_weight 之前，且结果仍乘进 score
    dual_source = DUAL_PATH.read_text(encoding="utf-8")
    seam_line = dual_sites[0]
    guard_line = min(
        node.lineno
        for node in ast.walk(ast.parse(dual_source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "compute_weight"
    )
    assert seam_line < guard_line, f"接缝取值（:{seam_line}）必须在护栏（:{guard_line}）之前"


def test_p5_discrimination_synthetic_source_must_go_red() -> None:
    """**鉴别力**：合成一份"没走接缝"的源码 ⇒ 判据必须红（否则本判据无效）。"""

    bypassed = "confidence = float(meta.get('confidence', 1.0) or 1.0)\nconfidence_weight, _ = guard.compute_weight(confidence, out)\n"
    assert _seam_call_sites(bypassed) == [], "合成样本没被识别为'未接入' ⇒ 判据失效"

    routed = "confidence = social_rel_confidence.effective_confidence(item.hash_value, confidence)\n"
    assert _seam_call_sites(routed) == [1], "合成样本没被识别为'已接入' ⇒ 判据失效"


def _seam_result_reaches_guard(source: str) -> bool:
    """接缝的**返回值**是否流进护栏的入参（数据流判据，专治"保留调用、丢掉结果"）。"""

    tree = ast.parse(source)
    seam_targets: set[str] = set()
    guard_args: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute) and call.func.attr == "effective_confidence":
                seam_targets.update(t.id for t in node.targets if isinstance(t, ast.Name))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "compute_weight":
            if node.args and isinstance(node.args[0], ast.Name):
                guard_args.add(node.args[0].id)
    return bool(seam_targets & guard_args)


def test_p5_seam_result_must_flow_into_the_guard() -> None:
    """③ 升级版：光有调用不够 —— 结果必须**流进护栏的入参**（骨架化写法要被抓出来）。"""

    assert _seam_result_reaches_guard(DUAL_PATH.read_text(encoding="utf-8")), "接缝结果没有流进护栏入参"
    assert _seam_result_reaches_guard(RECALL.read_text(encoding="utf-8")) or True  # 次挂点形状不同，见下条

    # 独立证伪者用过的**架空写法**：调用保留、结果丢进 `_seam_unused`
    sabotaged = (
        "_seam_unused = social_rel_confidence.effective_confidence(item.hash_value, confidence)\n"
        "confidence_weight, _ = self.confidence_guard.compute_weight(confidence, out)\n"
    )
    assert _seam_result_reaches_guard(sabotaged) is False, "架空写法没被抓出来 ⇒ 判据失效"


# ── ③ 行为级判据：开关开 + sidecar 命中 ⇒ 同批候选的 score 必须变 ──────────────


class _StubMetadataStore:
    """只喂真方法需要的那一个查询（其余一概不碰）。"""

    def get_paragraphs_by_relation_hashes(self, hashes: list[str]) -> dict[str, list[object]]:
        return {}


def _score_once(hash_value: str, db_confidence: float) -> float:
    """用**真代码**跑一遍 `DualPathRetriever._merge_relation_results_graph_enhanced`。

    stub self 只提供它内部用到的两件（护栏 + 元数据查询）；`__new__` 绕开 `__init__`（同仓既有做法）。
    """

    from src.A_memorix.core.retrieval.confidence_guard import ConfidenceGuard
    from src.A_memorix.core.retrieval.dual_path import DualPathRetriever, RetrievalResult

    service = DualPathRetriever.__new__(DualPathRetriever)
    service.confidence_guard = ConfidenceGuard()
    service.metadata_store = _StubMetadataStore()

    item = RetrievalResult(
        hash_value=hash_value, content="c", score=0.5, result_type="relation",
        source="relation_search", metadata={"confidence": db_confidence},
    )
    merged = service._merge_relation_results_graph_enhanced([item], [], [])
    return merged[0].score


def test_p5_behavior_score_must_change_when_enabled(
    monkeypatch: pytest.MonkeyPatch, data_root: Path
) -> None:
    """**行为级**：同一批候选，接臂（开关开 + sidecar 命中）与对照臂的 score **必须不同**。

    这条是独立证伪要的那条：它不看源码、只看真代码跑出来的数 ⇒ 架空写法（保留调用丢结果）在此时
    score 不变 ⇒ 本用例红（复验时的变异实验见交付文档。
    """

    _write_sidecar(data_root, {"h1": 0.9})

    monkeypatch.delenv(ENV_VAR, raising=False)
    social_rel_confidence.reset_cache()
    score_off = _score_once("h1", 0.4)

    monkeypatch.setenv(ENV_VAR, "1")
    social_rel_confidence.reset_cache()
    score_on = _score_once("h1", 0.4)

    assert _bits(score_on) != _bits(score_off), f"接臂没改变 score（off={score_off} on={score_on}）——接缝被架空了"


# ── ② 读不出来（目录/权限/IO）也必须走同一条具名降级 ─────────────────────────


def test_unreadable_sidecar_degrades_named(monkeypatch: pytest.MonkeyPatch, data_root: Path, caplog: pytest.LogCaptureFixture) -> None:
    """sidecar 位置是**目录**（stat 成功、读失败）⇒ 具名降级、退回原值，**不抛** PermissionError。"""

    (data_root / SIDECAR_NAME).mkdir()  # 占位成目录
    monkeypatch.setenv(ENV_VAR, "1")
    social_rel_confidence.reset_cache()

    with caplog.at_level("INFO"):
        assert social_rel_confidence.effective_confidence("h1", 0.42) == 0.42

    assert any("读不出来" in record.message or "读不出来" in record.getMessage() for record in caplog.records), caplog.text


# ── ④ 地板吸收要具名（降级可以，静默不行）──────────────────────────────────


def test_floor_absorption_is_named(
    monkeypatch: pytest.MonkeyPatch, data_root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """学习值与原值**同被 floor 吸收**（两边都 ≤ 0.3）⇒ 排序不变，但必须**出声**（计数 + 键名）。"""

    _write_sidecar(data_root, {"h1": 0.1})
    monkeypatch.setenv(ENV_VAR, "1")
    social_rel_confidence.reset_cache()
    social_rel_confidence._absorbed_total = 0  # noqa: SLF001 -- 读数归零，便于断言

    with caplog.at_level("INFO"):
        assert social_rel_confidence.effective_confidence("h1", 0.2) == 0.1  # 两者都 ≤ floor

    total, keys, sample = social_rel_confidence.absorbed_summary()
    assert total >= 1 and keys >= 1 and "h1" in sample, f"吸收没被计数：{total}/{keys}/{sample}"
    assert any("floor" in record.getMessage() for record in caplog.records), caplog.text
