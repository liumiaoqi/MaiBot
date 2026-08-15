"""ZG16-3 热加载单元测试 — 依赖检查 + 环检查 + 补全评估。

覆盖场景：依赖满足/未满足、补全评估、永久跳过不补全、热加载成环、
依赖被跳过插件、增量检查性能。
"""

import time


from src.core.service_manager.types import DependencyKind, DependencyRelation
from src.plugin_runtime_v2.host.activation_coordinator import ActivationCoordinator
from tests.plugin_runtime_v2.zg16_3_helpers import (
    ExceptionSupervisor,
    MockSupervisor,
    make_manifest,
    write_plugin_dir,
)


class TestCheckHotLoad:
    """check_hot_load 依赖检查。"""

    async def test_dependency_satisfied(self, tmp_path):
        """已激活 {B}, 热加载 A depends_on B → A 激活成功。"""
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        assert "org.b" in coordinator.activated

        manifest_a = make_manifest("org.a", dependencies=["org.b"])
        plan = await coordinator.plan_hot_load(manifest_a, tmp_path / "org_a")
        assert plan.is_activatable("org.a")
        assert "org.a" in coordinator.activated

    async def test_dependency_not_satisfied(self, tmp_path):
        """已激活 {}, 热加载 A depends_on B → A 跳过 "依赖未满足"。"""
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        # 无初始插件

        manifest_a = make_manifest("org.a", dependencies=["org.b"])
        plan = await coordinator.plan_hot_load(manifest_a, tmp_path / "org_a")
        assert not plan.is_activatable("org.a")
        assert "org.a" in plan.skipped
        assert "依赖未满足" in plan.skipped["org.a"]

    async def test_hot_load_depends_on_skipped(self, tmp_path):
        """热加载 A depends_on B, B 此前被跳过 → A 跳过。"""
        # B 因依赖 C 缺失被跳过
        write_plugin_dir(tmp_path, "org.b", dependencies=["org.c"])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        assert "org.b" in coordinator.skipped

        manifest_a = make_manifest("org.a", dependencies=["org.b"])
        plan = await coordinator.plan_hot_load(manifest_a, tmp_path / "org_a")
        assert not plan.is_activatable("org.a")
        assert "org.a" in plan.skipped

    async def test_check_hot_load_returns_missing(self, tmp_path):
        """check_hot_load 返回缺失依赖列表。"""
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        manifest = make_manifest("org.a", dependencies=["org.b", "org.c"])
        can_activate, missing = coordinator.check_hot_load(manifest, tmp_path)
        assert not can_activate
        assert "org.b" in missing
        assert "org.c" in missing


class TestComplementEvaluate:
    """补全评估。"""

    async def test_complement_evaluation(self, tmp_path):
        """A 因 B 缺失跳过, 热加载 B → B 激活后 A 自动补全。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        # A 因 B 缺失被跳过
        assert "org.a" in coordinator.skipped

        # 热加载 B
        manifest_b = make_manifest("org.b", dependencies=[])
        await coordinator.plan_hot_load(manifest_b, tmp_path / "org_b")
        assert "org.b" in coordinator.activated
        # A 应被补全激活
        assert "org.a" in coordinator.activated

    async def test_permanently_skipped_not_complemented(self, tmp_path):
        """A 因循环依赖永久跳过, 热加载 C → A 不被补全。"""
        # A↔B 环 → 两者跳过（循环依赖）
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        write_plugin_dir(tmp_path, "org.b", dependencies=["org.a"])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        assert "org.a" in coordinator.skipped
        assert "循环依赖" in coordinator.skipped["org.a"]

        # 热加载 C（无依赖）→ A 不被补激活
        manifest_c = make_manifest("org.c", dependencies=[])
        await coordinator.plan_hot_load(manifest_c, tmp_path / "org_c")
        assert "org.a" not in coordinator.activated


class TestHotLoadCycle:
    """热加载环检查。"""

    async def test_hot_load_forms_cycle(self, tmp_path):
        """已激活 B, 热加载 A depends_on B + 图中已有 B→A → 拒绝 A "热加载会形成环"。"""
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        assert "org.b" in coordinator.activated

        # 手动添加 B→A 边（模拟动态依赖场景）
        coordinator._graph.add_relation(DependencyRelation(
            dependent="org.b", dependency="org.a", kind=DependencyKind.STRONG,
        ))

        # 热加载 A depends_on B → 形成 A↔B 环
        manifest_a = make_manifest("org.a", dependencies=["org.b"])
        plan = await coordinator.plan_hot_load(manifest_a, tmp_path / "org_a")
        assert not plan.is_activatable("org.a")
        assert "热加载会形成环" in plan.skipped.get("org.a", "")

    async def test_hot_load_no_cycle_succeeds(self, tmp_path):
        """已激活 B, 热加载 A depends_on B, 无环 → A 激活成功。"""
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)

        manifest_a = make_manifest("org.a", dependencies=["org.b"])
        plan = await coordinator.plan_hot_load(manifest_a, tmp_path / "org_a")
        assert plan.is_activatable("org.a")
        assert len(plan.cycle_errors) == 0


class TestHotLoadPerformance:
    """热加载性能。"""

    async def test_check_hot_load_under_10ms(self, tmp_path):
        """已激活 50 个, 热加载 1 个 → check_hot_load < 10ms。"""
        for i in range(50):
            write_plugin_dir(tmp_path, f"org.p{i:02d}", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        assert len(coordinator.activated) == 50

        manifest = make_manifest("org.new", dependencies=["org.p00"])
        start = time.perf_counter()
        coordinator.check_hot_load(manifest, tmp_path / "org_new")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 10, f"check_hot_load 耗时 {elapsed_ms:.2f}ms 超过 10ms"


class TestPlanHotLoadResult:
    """plan_hot_load 返回的 ActivationPlan。"""

    async def test_success_plan_has_wave(self, tmp_path):
        """热加载成功 → plan.waves 包含新插件。"""
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)

        manifest_a = make_manifest("org.a", dependencies=["org.b"])
        plan = await coordinator.plan_hot_load(manifest_a, tmp_path / "org_a")
        assert plan.waves == [["org.a"]]
        assert plan.candidate_dirs == {"org.a": tmp_path / "org_a"}

    async def test_fail_plan_empty_waves(self, tmp_path):
        """热加载失败 → plan.waves 空, skipped 非空。"""
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)

        manifest_a = make_manifest("org.a", dependencies=["org.missing"])
        plan = await coordinator.plan_hot_load(manifest_a, tmp_path / "org_a")
        assert plan.waves == []
        assert "org.a" in plan.skipped

    async def test_hot_load_spawn_failure(self, tmp_path):
        """热加载时 spawn 返回失败 → plan.waves 空, skipped 含激活失败。"""
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        supervisor = MockSupervisor(fail_ids={"org.a"})
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)

        manifest_a = make_manifest("org.a", dependencies=["org.b"])
        plan = await coordinator.plan_hot_load(manifest_a, tmp_path / "org_a")
        assert not plan.is_activatable("org.a")
        assert "org.a" in plan.skipped
        assert "激活失败" in plan.skipped["org.a"]

    async def test_hot_load_spawn_exception(self, tmp_path):
        """热加载时 spawn 抛异常 → plan.waves 空, skipped 含激活失败。"""
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        supervisor = ExceptionSupervisor(fail_ids={"org.a"})
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)

        manifest_a = make_manifest("org.a", dependencies=["org.b"])
        plan = await coordinator.plan_hot_load(manifest_a, tmp_path / "org_a")
        assert not plan.is_activatable("org.a")
        assert "org.a" in plan.skipped