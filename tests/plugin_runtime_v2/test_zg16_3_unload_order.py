"""ZG16-3 卸载顺序单元测试 — 逆序卸载 + refcount 协调。

覆盖场景：逆序卸载、被依赖方先卸载级联、无 coordinator fallback、
菱形逆序、多插件并集、on_plugin_unloaded 移除。
"""

from unittest.mock import MagicMock


from src.plugin_runtime_v2.host.activation_coordinator import ActivationCoordinator
from tests.plugin_runtime_v2.zg16_3_helpers import MockSupervisor, write_plugin_dir


class TestPlanUnload:
    """plan_unload 逆序卸载。"""

    async def test_reverse_unload(self, tmp_path):
        """A depends_on B, unload {A,B} → A 先卸 B 后卸。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)

        order = coordinator.plan_unload({"org.a", "org.b"})
        assert order.index("org.a") < order.index("org.b")

    async def test_depended_on_auto_unload_first(self, tmp_path):
        """A depends_on B, A 仍 LIVE, 直接卸 B → 自动先卸 A。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)

        order = coordinator.plan_unload({"org.b"})
        # A 应在 B 之前（级联卸载依赖方）
        assert "org.a" in order
        assert order.index("org.a") < order.index("org.b")

    async def test_diamond_reverse(self, tmp_path):
        """菱形 A→B,C; unload {A,B,C} → A 先, B/C 后。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b", "org.c"])
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        write_plugin_dir(tmp_path, "org.c", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)

        order = coordinator.plan_unload({"org.a", "org.b", "org.c"})
        # A 在 B/C 之前
        assert order.index("org.a") < order.index("org.b")
        assert order.index("org.a") < order.index("org.c")

    async def test_multi_plugin_union(self, tmp_path):
        """unload {A,B,C,D} (A→B, D→C) → A/D 先, B/C 后, 无重复。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        write_plugin_dir(tmp_path, "org.d", dependencies=["org.c"])
        write_plugin_dir(tmp_path, "org.c", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)

        order = coordinator.plan_unload({"org.a", "org.b", "org.c", "org.d"})
        # 无重复
        assert len(order) == len(set(order))
        # A/D 在 B/C 之前
        assert order.index("org.a") < order.index("org.b")
        assert order.index("org.d") < order.index("org.c")

    async def test_empty_unload(self, tmp_path):
        """空卸载集 → 空列表。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)

        order = coordinator.plan_unload(set())
        assert order == []

    async def test_single_unload(self, tmp_path):
        """单插件卸载 → 列表含该插件。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)

        order = coordinator.plan_unload({"org.a"})
        assert order == ["org.a"]


class TestOnPluginUnloaded:
    """on_plugin_unloaded 状态移除。"""

    async def test_removes_from_activated(self, tmp_path):
        """on_plugin_unloaded 从 activated 移除。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        assert "org.a" in coordinator.activated

        coordinator.on_plugin_unloaded("org.a")
        assert "org.a" not in coordinator.activated

    async def test_removes_from_candidate_dirs(self, tmp_path):
        """on_plugin_unloaded 从 candidate_dirs 移除。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        assert "org.a" in coordinator._candidate_dirs

        coordinator.on_plugin_unloaded("org.a")
        assert "org.a" not in coordinator._candidate_dirs

    async def test_removes_from_candidates(self, tmp_path):
        """on_plugin_unloaded 从 candidates 移除。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)
        assert "org.a" in coordinator._candidates

        coordinator.on_plugin_unloaded("org.a")
        assert "org.a" not in coordinator._candidates

    async def test_graph_rebuilt_after_unload(self, tmp_path):
        """on_plugin_unloaded 后图重建, 卸载的插件不在图中。"""
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.b"])
        write_plugin_dir(tmp_path, "org.b", dependencies=[])
        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path)

        coordinator.on_plugin_unloaded("org.a")
        # 图中不应再有 org.a 的依赖边
        assert "org.a" not in coordinator._graph.dependents_of("org.b")


class TestNoCoordinatorFallback:
    """无 coordinator 时 HostEndpoint.stop fallback。"""

    async def test_stop_without_coordinator_uses_original_order(self):
        """coordinator 未注入 → stop 按原顺序卸载（向后兼容）。"""
        from src.plugin_runtime_v2.host.connection import HostEndpointConfig
        from src.plugin_runtime_v2.host.endpoint import HostEndpoint

        endpoint = HostEndpoint(config=HostEndpointConfig(
            listen_address="0.0.0.0:0", default_drain_timeout_ms=0,
        ))
        await endpoint.start()
        try:
            # 注册 runner（直接操作内部字典）
            endpoint._registry._connections["runner-a"] = MagicMock()
            endpoint._registry._connections["runner-b"] = MagicMock()

            # 不注入 coordinator
            assert endpoint._activation_coordinator is None

            # 记录 request_shutdown 顺序
            shutdown_calls: list[str] = []
            endpoint._servicer.request_shutdown = lambda rid, **kw: shutdown_calls.append(rid)

            await endpoint.stop()

            # fallback 按 registry 原顺序
            assert shutdown_calls == ["runner-a", "runner-b"]
        except Exception:
            if endpoint._server is not None:
                await endpoint.stop()
            raise

    async def test_stop_with_coordinator_uses_plan_unload(self, tmp_path):
        """coordinator 注入 → stop 用 plan_unload 逆序卸载。"""
        from src.plugin_runtime_v2.host.connection import HostEndpointConfig
        from src.plugin_runtime_v2.host.endpoint import HostEndpoint

        endpoint = HostEndpoint(config=HostEndpointConfig(
            listen_address="0.0.0.0:0", default_drain_timeout_ms=0,
        ))
        await endpoint.start()
        try:
            # 注册 runner
            endpoint._registry._connections["org.a"] = MagicMock()
            endpoint._registry._connections["org.b"] = MagicMock()

            # 注入 coordinator（mock plan_unload 返回逆序）
            coordinator = MagicMock()
            coordinator.plan_unload.return_value = ["org.a", "org.b"]
            endpoint.set_activation_coordinator(coordinator)

            shutdown_calls: list[str] = []
            endpoint._servicer.request_shutdown = lambda rid, **kw: shutdown_calls.append(rid)

            await endpoint.stop()

            # 用 plan_unload 返回的顺序
            assert shutdown_calls == ["org.a", "org.b"]
            coordinator.plan_unload.assert_called_once_with({"org.a", "org.b"})
        except Exception:
            if endpoint._server is not None:
                await endpoint.stop()
            raise


class TestSetActivationCoordinator:
    """set_activation_coordinator 注入。"""

    def test_default_none(self):
        """默认 _activation_coordinator 为 None。"""
        from src.plugin_runtime_v2.host.connection import HostEndpointConfig
        from src.plugin_runtime_v2.host.endpoint import HostEndpoint

        endpoint = HostEndpoint(config=HostEndpointConfig(listen_address="0.0.0.0:0"))
        assert endpoint._activation_coordinator is None

    def test_inject_coordinator(self):
        """set_activation_coordinator 注入 coordinator。"""
        from src.plugin_runtime_v2.host.connection import HostEndpointConfig
        from src.plugin_runtime_v2.host.endpoint import HostEndpoint

        endpoint = HostEndpoint(config=HostEndpointConfig(listen_address="0.0.0.0:0"))
        coordinator = MagicMock()
        endpoint.set_activation_coordinator(coordinator)
        assert endpoint._activation_coordinator is coordinator