"""ZG16-3 bootstrap 集成单元测试 — mock AppConfigPort + RunnerSupervisor。

覆盖场景：拓扑覆盖目录序、空依赖字母序、解析异常 fallback、
runner_spawn_count 切分、plugins-v2/ 不存在。
"""

from unittest.mock import MagicMock


from tests.plugin_runtime_v2.zg16_3_helpers import MockRunnerSupervisorFactory, write_plugin_dir


def _make_app_config_port(spawn_count: int = 10) -> MagicMock:
    """构造 mock AppConfigPort。"""
    port = MagicMock()
    port.get_plugin_runtime_v2_host_listen_address.return_value = "0.0.0.0:0"
    port.get_plugin_runtime_v2_scope_approval_file.return_value = ":memory:"
    port.get_plugin_runtime_v2_default_rpm.return_value = 60
    port.get_plugin_runtime_v2_runner_spawn_count.return_value = spawn_count
    return port


def _patch_supervisor(monkeypatch) -> None:
    """monkeypatch RunnerSupervisor 为 mock 工厂。"""
    MockRunnerSupervisorFactory.reset()
    monkeypatch.setattr(
        "src.plugin_runtime_v2.host.runner_supervisor.RunnerSupervisor",
        MockRunnerSupervisorFactory,
    )


class TestBootstrapActivationOrder:
    """bootstrap 激活顺序集成。"""

    async def test_topo_covers_dir_order(self, tmp_path, monkeypatch):
        """A depends_on B, 目录序 A<B → 激活 B 先于 A。"""
        plugins_root = tmp_path / "plugins-v2"
        plugins_root.mkdir()
        write_plugin_dir(plugins_root, "org.a", dependencies=["org.b"], dir_name="a_dir")
        write_plugin_dir(plugins_root, "org.b", dependencies=[], dir_name="b_dir")
        monkeypatch.chdir(tmp_path)
        _patch_supervisor(monkeypatch)

        from src.plugin_runtime_v2.bootstrap import init_v2_host_endpoint
        port = _make_app_config_port(spawn_count=10)
        endpoint = await init_v2_host_endpoint(port)
        try:
            mock_sup = MockRunnerSupervisorFactory.get_instance()
            spawn_ids = [call[0] for call in mock_sup.spawn_calls]
            assert spawn_ids.index("org.b") < spawn_ids.index("org.a")
        finally:
            await endpoint.stop()

    async def test_empty_deps_alphabetical(self, tmp_path, monkeypatch):
        """全空依赖 → 激活序匹配 sorted 字母序（向后兼容）。"""
        plugins_root = tmp_path / "plugins-v2"
        plugins_root.mkdir()
        write_plugin_dir(plugins_root, "org.c", dependencies=[])
        write_plugin_dir(plugins_root, "org.a", dependencies=[])
        write_plugin_dir(plugins_root, "org.b", dependencies=[])
        monkeypatch.chdir(tmp_path)
        _patch_supervisor(monkeypatch)

        from src.plugin_runtime_v2.bootstrap import init_v2_host_endpoint
        port = _make_app_config_port(spawn_count=10)
        endpoint = await init_v2_host_endpoint(port)
        try:
            mock_sup = MockRunnerSupervisorFactory.get_instance()
            spawn_ids = [call[0] for call in mock_sup.spawn_calls]
            assert spawn_ids == ["org.a", "org.b", "org.c"]
        finally:
            await endpoint.stop()

    async def test_parse_exception_fallback(self, tmp_path, monkeypatch):
        """依赖解析异常 → fallback 字母序 + warning。"""
        plugins_root = tmp_path / "plugins-v2"
        plugins_root.mkdir()
        write_plugin_dir(plugins_root, "org.a", dependencies=[])
        write_plugin_dir(plugins_root, "org.b", dependencies=[])
        monkeypatch.chdir(tmp_path)
        _patch_supervisor(monkeypatch)

        # 让 compute_activation_plan 抛异常
        def raise_compute(plugin_dirs):
            raise RuntimeError("test parse error")
        monkeypatch.setattr(
            "src.plugin_runtime_v2.host.activation_coordinator.compute_activation_plan",
            raise_compute,
        )

        from src.plugin_runtime_v2.bootstrap import init_v2_host_endpoint
        port = _make_app_config_port(spawn_count=10)
        endpoint = await init_v2_host_endpoint(port)
        try:
            mock_sup = MockRunnerSupervisorFactory.get_instance()
            # fallback 用 runner-<dir_name> 作为 id，按目录字母序
            spawn_ids = [call[0] for call in mock_sup.spawn_calls]
            assert len(spawn_ids) == 2
            assert spawn_ids[0] == "runner-org_a"
            assert spawn_ids[1] == "runner-org_b"
        finally:
            await endpoint.stop()

    async def test_runner_spawn_count_limit(self, tmp_path, monkeypatch):
        """runner_spawn_count=2, wave 0 有 3 → 总 spawn 上限 2。"""
        plugins_root = tmp_path / "plugins-v2"
        plugins_root.mkdir()
        write_plugin_dir(plugins_root, "org.a", dependencies=[])
        write_plugin_dir(plugins_root, "org.b", dependencies=[])
        write_plugin_dir(plugins_root, "org.c", dependencies=[])
        monkeypatch.chdir(tmp_path)
        _patch_supervisor(monkeypatch)

        from src.plugin_runtime_v2.bootstrap import init_v2_host_endpoint
        port = _make_app_config_port(spawn_count=2)
        endpoint = await init_v2_host_endpoint(port)
        try:
            mock_sup = MockRunnerSupervisorFactory.get_instance()
            # 代码行为：runner_spawn_count 是总上限 → spawn 2 个
            assert len(mock_sup.spawn_calls) == 2
        finally:
            await endpoint.stop()

    async def test_plugins_v2_not_exists(self, tmp_path, monkeypatch):
        """plugins-v2/ 不存在 → 空 plan + warning（向后兼容）。"""
        monkeypatch.chdir(tmp_path)
        _patch_supervisor(monkeypatch)

        from src.plugin_runtime_v2.bootstrap import init_v2_host_endpoint
        port = _make_app_config_port(spawn_count=10)
        endpoint = await init_v2_host_endpoint(port)
        try:
            mock_sup = MockRunnerSupervisorFactory.get_instance()
            assert len(mock_sup.spawn_calls) == 0
        finally:
            await endpoint.stop()

    async def test_plugins_v2_empty(self, tmp_path, monkeypatch):
        """plugins-v2/ 存在但无有效插件 → 空 plan + warning。"""
        plugins_root = tmp_path / "plugins-v2"
        plugins_root.mkdir()
        (plugins_root / "empty_subdir").mkdir()  # 无 manifest 的子目录
        monkeypatch.chdir(tmp_path)
        _patch_supervisor(monkeypatch)

        from src.plugin_runtime_v2.bootstrap import init_v2_host_endpoint
        port = _make_app_config_port(spawn_count=10)
        endpoint = await init_v2_host_endpoint(port)
        try:
            mock_sup = MockRunnerSupervisorFactory.get_instance()
            assert len(mock_sup.spawn_calls) == 0
        finally:
            await endpoint.stop()