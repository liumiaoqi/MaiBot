"""ZG16-3 激活计划波次计算单元测试 — 拓扑排序 + 波次分波。

专注波次计算的正确性：并行波次、线性/菱形依赖、波次完整性、
同波次字母序、ActivationPlan 接口、空输入。
"""


import pytest

from src.plugin_runtime_v2.host.dependency_resolver import (
    ActivationPlan,
    compute_activation_plan,
)
from tests.plugin_runtime_v2.zg16_3_helpers import write_plugin_dir


class TestWaveComputation:
    """波次计算场景。"""

    def test_no_deps_all_parallel(self, tmp_path):
        """3 插件无依赖 → 单波 3 个（字母序）。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=[])
        d_b = write_plugin_dir(tmp_path, "org.b", dependencies=[])
        d_c = write_plugin_dir(tmp_path, "org.c", dependencies=[])
        plan = compute_activation_plan([d_a, d_b, d_c])
        assert len(plan.waves) == 1
        assert plan.waves[0] == ["org.a", "org.b", "org.c"]

    def test_linear_dependency(self, tmp_path):
        """A depends_on B → wave 0={B}, wave 1={A}。"""
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

    def test_wave_completeness(self, tmp_path):
        """3 无依赖 + 1 依赖 2 个 → wave 0 有 3, wave 1 有 1, 全 4 个出现。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=[])
        d_b = write_plugin_dir(tmp_path, "org.b", dependencies=[])
        d_c = write_plugin_dir(tmp_path, "org.c", dependencies=[])
        d_d = write_plugin_dir(tmp_path, "org.d", dependencies=["org.a", "org.b"])
        plan = compute_activation_plan([d_a, d_b, d_c, d_d])
        assert len(plan.waves[0]) == 3
        assert len(plan.waves[1]) == 1
        all_activated = set(plan.activation_order())
        assert all_activated == {"org.a", "org.b", "org.c", "org.d"}

    def test_same_wave_alphabetical(self, tmp_path):
        """同波次字母序：c.a, a.b, b.c → wave 0 = [a.b, b.c, c.a]。"""
        d1 = write_plugin_dir(tmp_path, "c.a", dependencies=[], dir_name="d1")
        d2 = write_plugin_dir(tmp_path, "a.b", dependencies=[], dir_name="d2")
        d3 = write_plugin_dir(tmp_path, "b.c", dependencies=[], dir_name="d3")
        plan = compute_activation_plan([d1, d2, d3])
        assert plan.waves[0] == ["a.b", "b.c", "c.a"]

    def test_multi_level_linear(self, tmp_path):
        """A→B→C 三级线性 → wave 0={C}, wave 1={B}, wave 2={A}。"""
        d_a = write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        d_b = write_plugin_dir(tmp_path, "org.b", dependencies=["org.c"])
        d_c = write_plugin_dir(tmp_path, "org.c", dependencies=[])
        plan = compute_activation_plan([d_a, d_b, d_c])
        assert plan.waves == [["org.c"], ["org.b"], ["org.a"]]


class TestActivationPlanInterface:
    """ActivationPlan 接口行为。"""

    def test_is_activatable_in_wave(self):
        """在波次中且未跳过 → 可激活。"""
        plan = ActivationPlan(
            waves=[["org.b"], ["org.a"]],
            skipped={},
            cycle_errors=[],
        )
        assert plan.is_activatable("org.a")
        assert plan.is_activatable("org.b")

    def test_is_activatable_skipped(self):
        """在跳过清单中 → 不可激活。"""
        plan = ActivationPlan(
            waves=[["org.a"]],
            skipped={"org.b": "跳过"},
            cycle_errors=[],
        )
        assert not plan.is_activatable("org.b")

    def test_is_activatable_not_present(self):
        """既不在波次也不在跳过 → 不可激活。"""
        plan = ActivationPlan(waves=[["org.a"]], skipped={}, cycle_errors=[])
        assert not plan.is_activatable("org.z")

    def test_activation_order_flatten(self):
        """activation_order 展平多波次。"""
        plan = ActivationPlan(
            waves=[["org.b"], ["org.a"]],
            skipped={},
            cycle_errors=[],
        )
        assert plan.activation_order() == ["org.b", "org.a"]

    def test_activation_order_empty(self):
        """空波次 → 空序。"""
        plan = ActivationPlan(waves=[], skipped={}, cycle_errors=[])
        assert plan.activation_order() == []

    def test_frozen_immutable(self):
        """frozen=True 不可变。"""
        plan = ActivationPlan(waves=[], skipped={}, cycle_errors=[])
        with pytest.raises((AttributeError, TypeError)):
            plan.waves = [["org.a"]]

    def test_candidate_dirs_default_empty(self):
        """candidate_dirs 默认空 dict。"""
        plan = ActivationPlan(waves=[], skipped={}, cycle_errors=[])
        assert plan.candidate_dirs == {}

    def test_empty_input(self, tmp_path):
        """空输入 → 空 ActivationPlan。"""
        plan = compute_activation_plan([])
        assert plan.waves == []
        assert plan.skipped == {}
        assert plan.cycle_errors == []
        assert plan.candidate_dirs == {}