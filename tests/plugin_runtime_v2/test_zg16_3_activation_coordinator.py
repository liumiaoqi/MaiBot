"""ZG16-3 激活编排器单元测试 — 有状态 plan_startup/回调/spawn 上限。

覆盖场景：波次顺序激活、同波次无序、波次失败传播、拓扑覆盖目录序、
空依赖字母序、spawn 失败传播、runner_spawn_count 切分、状态一致性。
"""



from src.plugin_runtime_v2.host.activation_coordinator import ActivationCoordinator
from tests.plugin_runtime_v2.zg16_3_helpers import ExceptionSupervisor, MockSupervisor, write_plugin_dir


class TestPlanStartup:
    """plan_startup 波次激活。"""

    async def test_wave_order_activation(self, tmp_path):
        """wave 0={B}, wave 1={A} → B 先 spawn 且成功后 A 才 spawn。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        plan = await coordinator.plan_startup(tmp_path)
        # 验证 spawn 顺序：B 在 A 之前
        spawn_ids = [call[0] for call in supervisor.spawn_calls]
        assert spawn_ids.index("org.b") < spawn_ids.index("org.a")
        assert plan.is_activatable("org.a")
        assert plan.is_activatable("org.b")

    async def test_same_wave_no_order(self, tmp_path):
        """wave 0={B,C} → B/C 任意顺序 spawn, 无错误。"""
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        write_plugin_dir(tmp_path, "org.c", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        spawn_ids = {call[0] for call in supervisor.spawn_calls}
        assert spawn_ids == {"org.b", "org.c"}

    async def test_wave_failure_skips_failed(self, tmp_path):
        """wave 0={B,C}, B 失败 → C 正常激活, B 在 skipped 中。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        write_plugin_dir(tmp_path, "org.c", dependencies=[])
        supervisor = MockSupervisor(fail_ids={"org.b"})
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        # C 正常激活
        assert "org.c" in coordinator.activated
        # B 失败，在 skipped 中
        assert "org.b" not in coordinator.activated
        assert "org.b" in coordinator.skipped

    async def test_topo_covers_directory_order(self, tmp_path):
        """A depends_on B, 目录序 A<B → 激活 B 先于 A（拓扑覆盖目录序）。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"], dir_name="a_dir")
        write_plugin_dir(tmp_path, "org.b", dependencies=[], dir_name="b_dir")
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        spawn_ids = [call[0] for call in supervisor.spawn_calls]
        assert spawn_ids.index("org.b") < spawn_ids.index("org.a")

    async def test_empty_deps_alphabetical(self, tmp_path):
        """全空依赖 → 激活序匹配 sorted 字母序。"""
        write_plugin_dir(tmp_path, "org.c", dependencies=[])
        write_plugin_dir(tmp_path, "org.a", dependencies=[])
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        plan = await coordinator.plan_startup(tmp_path)
        assert plan.activation_order() == ["org.a", "org.b", "org.c"]

    async def test_spawn_failure_propagation(self, tmp_path):
        """B spawn 失败 → B 标记失败, B 在 skipped 中。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        supervisor = MockSupervisor(fail_ids={"org.b"})
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        assert "org.b" not in coordinator.activated
        assert "org.b" in coordinator.skipped

    async def test_runner_spawn_count_split(self, tmp_path):
        """limit=2, wave 0 有 3 → 切 [2,1] 子波, 总 spawn 上限 2。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=[])
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        write_plugin_dir(tmp_path, "org.c", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path, runner_spawn_count=2)
        # 代码行为：runner_spawn_count 既是切分粒度又是总上限 → spawn 2 个
        assert len(supervisor.spawn_calls) == 2
        # 切分后前 2 个先 spawn（字母序 org.a, org.b）
        spawned_ids = [call[0] for call in supervisor.spawn_calls]
        assert spawned_ids == ["org.a", "org.b"]

    async def test_runner_spawn_count_unlimited(self, tmp_path):
        """limit=-1（不限）→ 全部 3 个激活。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=[])
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        write_plugin_dir(tmp_path, "org.c", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path, runner_spawn_count=-1)
        assert len(supervisor.spawn_calls) == 3

    async def test_state_consistency(self, tmp_path):
        """plan_startup → activated 包含所有成功 spawn 的插件。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        write_plugin_dir(tmp_path, "org.c", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        # 所有成功 spawn 的在 activated
        assert "org.a" in coordinator.activated
        assert "org.b" in coordinator.activated
        assert "org.c" in coordinator.activated

    async def test_empty_plugins_root(self, tmp_path):
        """插件根目录不存在 → 空 plan。"""
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        plan = await coordinator.plan_startup(tmp_path / "nonexistent")
        assert plan.waves == []
        assert plan.skipped == {}

    async def test_no_valid_plugins(self, tmp_path):
        """插件根目录下无有效插件 → 空 plan。"""
        (tmp_path / "empty_dir").mkdir()
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        plan = await coordinator.plan_startup(tmp_path)
        assert plan.waves == []
        assert plan.skipped == {}

    async def test_spawn_exception_handling(self, tmp_path):
        """spawn_and_wait 抛异常 → on_plugin_failed, 不崩溃。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=[])
        supervisor = ExceptionSupervisor(fail_ids={"org.a"})
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        # A spawn 异常 → 标记失败
        assert "org.a" not in coordinator.activated
        assert "org.a" in coordinator.skipped


class TestOnPluginFailed:
    """on_plugin_failed 跳过传播。"""

    async def test_failed_propagates_to_dependents(self, tmp_path):
        """B 失败 → 依赖 B 的 A 加入 skipped（级联跳过）。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        # 手动标记 B 失败
        coordinator.on_plugin_failed("org.b", "手动失败")
        assert "org.b" in coordinator.skipped
        # A 依赖 B → A 级联跳过
        assert "org.a" in coordinator.skipped
        assert "级联跳过" in coordinator.skipped["org.a"]


class TestActivatedSkippedProperties:
    """activated / skipped 属性。"""

    async def test_activated_property(self, tmp_path):
        """activated 属性返回已激活集合。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        assert coordinator.activated == {"org.a"}

    async def test_skipped_property(self, tmp_path):
        """skipped 属性返回跳过清单。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.missing"])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        assert "org.a" in coordinator.skipped


class TestRunnerIdConsistency:
    """runner_id 一致性——plan_startup 用裸 plugin_id 作 runner_id spawn。

    P0 修复验证：main.py:345 的 kill_runner(plugin_id) 依赖此约定。
    """

    async def test_runner_id_is_bare_plugin_id(self, tmp_path):
        """spawn_and_wait 收到的 runner_id 是裸 plugin_id，无 runner- 前缀。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=[])
        write_plugin_dir(tmp_path, "org.b", dependencies=["org.a"])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        spawn_ids = [call[0] for call in supervisor.spawn_calls]
        # 裸 ID，无 "runner-" 前缀
        assert "org.a" in spawn_ids
        assert "org.b" in spawn_ids
        assert not any(sid.startswith("runner-") for sid in spawn_ids)