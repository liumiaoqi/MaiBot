"""ZG16-3 依赖解析器单元测试 — 纯逻辑 parse/build/propagate/compute。

覆盖场景：空目录、单插件、manifest 缺失/非法、自依赖、ID 格式、去重、
id 重复、缺失依赖、级联跳过、链式传播、环检测、三角环、环外正常、
ActivationPlan dataclass、compute_activation_plan 波次。
"""

import json

import pytest

from src.plugin_runtime_v2.host.dependency_resolver import (
    ActivationPlan,
    build_dependency_graph,
    compute_activation_plan,
    parse_candidate_manifests,
    propagate_skips,
)
from tests.plugin_runtime_v2.zg16_3_helpers import write_plugin_dir


# ── parse_candidate_manifests ─────────────────────────────


class TestParseCandidateManifests:
    """parse_candidate_manifests 场景。"""

    def test_empty_directory_list(self):
        """空目录列表 → 空 CandidateMap + 空 SkipMap。"""
        candidates, skips = parse_candidate_manifests([])
        assert candidates == {}
        assert skips == {}

    def test_single_plugin_no_dependencies(self, tmp_path):
        """单插件无依赖 → CandidateMap 1 项, SkipMap 空。"""
        d = write_plugin_dir(tmp_path, "org.a", dependencies=[])
        candidates, skips = parse_candidate_manifests([d])
        assert len(candidates) == 1
        assert "org.a" in candidates
        assert skips == {}

    def test_single_plugin_with_dependencies(self, tmp_path):
        """单插件有依赖且依赖在候选中 → CandidateMap 2 项。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        d_b = write_plugin_dir(tmp_path, "org.b", dependencies=[])
        candidates, skips = parse_candidate_manifests([d_a, d_b])
        assert len(candidates) == 2
        assert "org.a" in candidates
        assert "org.b" in candidates

    def test_manifest_missing(self, tmp_path):
        """目录无 manifest → 跳过 + debug 日志，不加入 skips。"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        candidates, skips = parse_candidate_manifests([empty_dir])
        assert candidates == {}
        assert skips == {}

    def test_manifest_invalid_json(self, tmp_path):
        """manifest.json 非法 JSON → skip + report ERROR。"""
        d = write_plugin_dir(tmp_path, "org.a", raw_content="{not valid json")
        candidates, skips = parse_candidate_manifests([d])
        assert candidates == {}
        assert any("manifest 解析失败" in v for v in skips.values())

    def test_dependencies_type_error(self, tmp_path):
        """dependencies 为 dict（非 list[str]）→ ValidationError → skip。"""
        raw = json.dumps({
            "manifest_version": 3,
            "id": "org.a",
            "version": "1.0.0",
            "name": "a",
            "author": {"name": "test"},
            "scopes": ["message:send:text"],
            "dependencies": {"org.b": "strong"},
        })
        d = write_plugin_dir(tmp_path, "org.a", raw_content=raw)
        candidates, skips = parse_candidate_manifests([d])
        assert candidates == {}
        assert any("manifest 校验失败" in v for v in skips.values())

    def test_self_dependency(self, tmp_path):
        """自依赖 → skip "声明了自依赖"。"""
        d = write_plugin_dir(tmp_path, "org.a", dependencies=["org.a"])
        candidates, skips = parse_candidate_manifests([d])
        assert candidates == {}
        assert skips.get("org.a") == "声明了自依赖"

    def test_dependency_id_format_invalid(self, tmp_path):
        """依赖 ID 格式非法 → skip "依赖 ID 格式非法"。"""
        d = write_plugin_dir(tmp_path, "org.a", dependencies=["invalid id!"])
        candidates, skips = parse_candidate_manifests([d])
        assert candidates == {}
        assert "依赖 ID 格式非法" in skips.get("org.a", "")

    def test_duplicate_dependencies_dedup(self, tmp_path):
        """重复依赖去重为单条边。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=["org.b", "org.b"])
        d_b = write_plugin_dir(tmp_path, "org.b", dependencies=[])
        candidates, skips = parse_candidate_manifests([d_a, d_b])
        assert "org.a" in candidates
        _, manifest_a = candidates["org.a"]
        assert manifest_a.dependencies == ["org.b"]

    def test_manifest_id_duplicate(self, tmp_path):
        """两目录同 id → 两者均跳过 "id 重复"。"""
        d1 = write_plugin_dir(tmp_path, "org.a", dir_name="dir1")
        d2 = write_plugin_dir(tmp_path, "org.a", dir_name="dir2")
        candidates, skips = parse_candidate_manifests([d1, d2])
        assert candidates == {}
        assert any("id 重复" in v for v in skips.values())

    def test_underscore_manifest_fallback(self, tmp_path):
        """manifest.json 不存在时回退到 _manifest.json。"""
        d = write_plugin_dir(tmp_path, "org.a", manifest_filename="_manifest.json")
        candidates, skips = parse_candidate_manifests([d])
        assert "org.a" in candidates
        assert skips == {}


# ── build_dependency_graph ─────────────────────────────────


class TestBuildDependencyGraph:
    """build_dependency_graph 场景。"""

    def test_missing_dependency(self, tmp_path):
        """A depends_on B, B 不在候选 → A 跳过 "依赖 B 未发现"。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        candidates, _ = parse_candidate_manifests([d_a])
        graph, skips = build_dependency_graph(candidates)
        assert "org.a" in skips
        assert "依赖 org.b 未发现" in skips["org.a"]

    def test_satisfied_dependency_no_skip(self, tmp_path):
        """A depends_on B, B 在候选 → 无跳过。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        d_b = write_plugin_dir(tmp_path, "org.b", dependencies=[])
        candidates, _ = parse_candidate_manifests([d_a, d_b])
        graph, skips = build_dependency_graph(candidates)
        assert skips == {}


# ── propagate_skips ────────────────────────────────────────


class TestPropagateSkips:
    """propagate_skips 场景。"""

    def test_cascade_skip(self, tmp_path):
        """C depends_on A, A depends_on B, B 缺失 → A 和 C 均跳过, C "依赖 A 级联跳过"。"""
        d_c = write_plugin_dir(tmp_path, "org.c", dependencies=["org.a"])
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        candidates, _ = parse_candidate_manifests([d_c, d_a])
        _, missing_skips = build_dependency_graph(candidates)
        all_skips = propagate_skips(candidates, missing_skips)
        assert "org.a" in all_skips
        assert "org.c" in all_skips
        assert "级联跳过" in all_skips["org.c"]

    def test_chain_propagation(self, tmp_path):
        """A→B→C→D, D 缺失 → A/B/C 均跳过, 有限步收敛。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        d_b = write_plugin_dir(tmp_path, "org.b", dependencies=["org.c"])
        d_c = write_plugin_dir(tmp_path, "org.c", dependencies=["org.d"])
        candidates, _ = parse_candidate_manifests([d_a, d_b, d_c])
        _, missing_skips = build_dependency_graph(candidates)
        all_skips = propagate_skips(candidates, missing_skips)
        assert "org.a" in all_skips
        assert "org.b" in all_skips
        assert "org.c" in all_skips

    def test_no_skips_unchanged(self, tmp_path):
        """无初始跳过 → 传播后仍无跳过。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        d_b = write_plugin_dir(tmp_path, "org.b", dependencies=[])
        candidates, _ = parse_candidate_manifests([d_a, d_b])
        all_skips = propagate_skips(candidates, {})
        assert all_skips == {}


# ── compute_activation_plan 环检测 ─────────────────────────


class TestComputeActivationPlanCycle:
    """compute_activation_plan 环检测场景。"""

    def test_cycle_detection(self, tmp_path):
        """A↔B 环 → 两者不加载, cycle_errors 含 [A,B]。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        d_b = write_plugin_dir(tmp_path, "org.b", dependencies=["org.a"])
        plan = compute_activation_plan([d_a, d_b])
        assert len(plan.cycle_errors) >= 1
        cycle = plan.cycle_errors[0]
        assert "org.a" in cycle
        assert "org.b" in cycle
        assert not plan.is_activatable("org.a")
        assert not plan.is_activatable("org.b")

    def test_triangle_cycle(self, tmp_path):
        """A→B→C→A 三角环 → 全不加载, cycle_errors 含环路径。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        d_b = write_plugin_dir(tmp_path, "org.b", dependencies=["org.c"])
        d_c = write_plugin_dir(tmp_path, "org.c", dependencies=["org.a"])
        plan = compute_activation_plan([d_a, d_b, d_c])
        assert len(plan.cycle_errors) >= 1
        cycle = plan.cycle_errors[0]
        assert set(cycle) == {"org.a", "org.b", "org.c"}

    def test_cycle_outside_normal(self, tmp_path):
        """A↔B 环, C 无依赖 → A/B 不加载, C 正常激活。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        d_b = write_plugin_dir(tmp_path, "org.b", dependencies=["org.a"])
        d_c = write_plugin_dir(tmp_path, "org.c", dependencies=[])
        plan = compute_activation_plan([d_a, d_b, d_c])
        assert plan.is_activatable("org.c")
        assert not plan.is_activatable("org.a")
        assert not plan.is_activatable("org.b")
        assert plan.activation_order() == ["org.c"]

    def test_self_loop_rejected_at_parse(self, tmp_path):
        """自依赖在 parse 阶段拒绝（从 candidates 移除, 不可激活）。"""
        d = write_plugin_dir(tmp_path, "org.a", dependencies=["org.a"])
        # parse 阶段 skips 记录自依赖
        candidates, parse_skips = parse_candidate_manifests([d])
        assert "org.a" not in candidates
        assert parse_skips.get("org.a") == "声明了自依赖"
        # compute_activation_plan 中自依赖插件从 candidates 移除 → 不在 skipped_plugins
        plan = compute_activation_plan([d])
        assert not plan.is_activatable("org.a")


# ── ActivationPlan dataclass ───────────────────────────────


class TestActivationPlanDataclass:
    """ActivationPlan dataclass 行为。"""

    def test_is_activatable(self):
        """is_activatable 正确判定。"""
        plan = ActivationPlan(
            waves=[["org.b"], ["org.a"]],
            skipped={"org.c": "测试"},
            cycle_errors=[],
        )
        assert plan.is_activatable("org.a")
        assert plan.is_activatable("org.b")
        assert not plan.is_activatable("org.c")
        assert not plan.is_activatable("org.d")

    def test_activation_order(self):
        """activation_order 展平波次。"""
        plan = ActivationPlan(
            waves=[["org.b", "org.c"], ["org.a"]],
            skipped={},
            cycle_errors=[],
        )
        assert plan.activation_order() == ["org.b", "org.c", "org.a"]

    def test_frozen_immutable(self):
        """frozen=True 不可变。"""
        plan = ActivationPlan(waves=[], skipped={}, cycle_errors=[])
        with pytest.raises((AttributeError, TypeError)):
            plan.waves = [["org.a"]]


# ── compute_activation_plan 波次 ───────────────────────────


class TestComputeActivationPlanWaves:
    """compute_activation_plan 波次计算。"""

    def test_linear_dependency(self, tmp_path):
        """A→B 线性 → wave 0={B}, wave 1={A}。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        d_b = write_plugin_dir(tmp_path, "org.b", dependencies=[])
        plan = compute_activation_plan([d_a, d_b])
        assert plan.waves == [["org.b"], ["org.a"]]

    def test_diamond_dependency(self, tmp_path):
        """A→B,C 菱形 → wave 0={B,C}, wave 1={A}。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=["org.b", "org.c"])
        d_b = write_plugin_dir(tmp_path, "org.b", dependencies=[])
        d_c = write_plugin_dir(tmp_path, "org.c", dependencies=[])
        plan = compute_activation_plan([d_a, d_b, d_c])
        assert plan.waves == [["org.b", "org.c"], ["org.a"]]

    def test_three_no_dep_one_dep(self, tmp_path):
        """3 无依赖 + 1 依赖其中 2 个 → wave 0 有 3, wave 1 有 1。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=[])
        d_b = write_plugin_dir(tmp_path, "org.b", dependencies=[])
        d_c = write_plugin_dir(tmp_path, "org.c", dependencies=[])
        d_d = write_plugin_dir(tmp_path, "org.d", dependencies=["org.a", "org.b"])
        plan = compute_activation_plan([d_a, d_b, d_c, d_d])
        assert len(plan.waves[0]) == 3
        assert len(plan.waves[1]) == 1
        assert plan.waves[1] == ["org.d"]

    def test_empty_input(self, tmp_path):
        """空输入 → 空 ActivationPlan。"""
        plan = compute_activation_plan([])
        assert plan.waves == []
        assert plan.skipped == {}
        assert plan.cycle_errors == []

    def test_candidate_dirs_populated(self, tmp_path):
        """candidate_dirs 填充插件 ID → 目录路径映射。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=[])
        plan = compute_activation_plan([d_a])
        assert "org.a" in plan.candidate_dirs
        assert plan.candidate_dirs["org.a"] == d_a

    def test_three_independent_cycles_no_crash(self, tmp_path):
        """3 个独立环 + 1 个非环插件 → 不崩溃，3 个环全检测，非环插件正常激活。

        P1-2 修复验证：while 循环迭代剔除环内节点直到无环。
        """
        # 环 1: A↔B
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        write_plugin_dir(tmp_path, "org.b", dependencies=["org.a"])
        # 环 2: C↔D
        write_plugin_dir(tmp_path, "org.c", dependencies=["org.d"])
        write_plugin_dir(tmp_path, "org.d", dependencies=["org.c"])
        # 环 3: E↔F
        write_plugin_dir(tmp_path, "org.e", dependencies=["org.f"])
        write_plugin_dir(tmp_path, "org.f", dependencies=["org.e"])
        # 非环插件 G
        write_plugin_dir(tmp_path, "org.g", dependencies=[])

        plan = compute_activation_plan([
            tmp_path / "org_a", tmp_path / "org_b",
            tmp_path / "org_c", tmp_path / "org_d",
            tmp_path / "org_e", tmp_path / "org_f",
            tmp_path / "org_g",
        ])

        # 环检测：compute_waves 一次性返回所有环节点（非独立环分组）
        assert len(plan.cycle_errors) >= 1
        # 所有环内插件在 cycle_errors 的某个子列表中
        all_cycle_nodes = {node for cycle in plan.cycle_errors for node in cycle}
        for pid in ["org.a", "org.b", "org.c", "org.d", "org.e", "org.f"]:
            assert pid in all_cycle_nodes
        # 所有环内插件跳过
        for pid in ["org.a", "org.b", "org.c", "org.d", "org.e", "org.f"]:
            assert pid in plan.skipped
            assert plan.skipped[pid] == "循环依赖"
        # 非环插件正常激活
        assert plan.is_activatable("org.g")
        assert plan.activation_order() == ["org.g"]