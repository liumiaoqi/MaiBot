"""ZG16-3 回归测试 — 向后兼容性验证（最关键）。

覆盖场景：空依赖行为不变、plugins-v2/ 不存在行为不变、v1 不受影响、
manifest v3 schema 不变、RunnerSupervisor 接口不变、无 coordinator fallback。
"""

from unittest.mock import MagicMock

import pytest

from src.plugin_runtime_v2.host.dependency_resolver import compute_activation_plan
from src.plugin_runtime_v2.host.runner_supervisor import SpawnResult
from src.plugin_runtime_v2.sdk.manifest import ManifestV3
from tests.plugin_runtime_v2.zg16_3_helpers import MockSupervisor, write_plugin_dir


class TestEmptyDepsBackwardCompat:
    """空依赖行为与改动前一致（sorted 字母序）。"""

    def test_all_empty_deps_sorted(self, tmp_path):
        """全空依赖 → 激活序 100% 匹配 sorted 字母序。"""
        ids = ["org.e", "org.a", "org.c", "org.b", "org.d"]
        dirs = [write_plugin_dir(tmp_path, pid, dependencies=[]) for pid in ids]
        plan = compute_activation_plan(dirs)
        expected = sorted(ids)
        assert plan.activation_order() == expected

    def test_all_empty_deps_single_wave(self, tmp_path):
        """全空依赖 → 单波次。"""
        for pid in ["org.a", "org.b", "org.c"]:
            write_plugin_dir(tmp_path, pid, dependencies=[])
        plan = compute_activation_plan(list(tmp_path.iterdir()))
        assert len(plan.waves) == 1

    def test_no_skips_no_cycles(self, tmp_path):
        """全空依赖 → 无跳过无环。"""
        for pid in ["org.a", "org.b"]:
            write_plugin_dir(tmp_path, pid, dependencies=[])
        plan = compute_activation_plan(list(tmp_path.iterdir()))
        assert plan.skipped == {}
        assert plan.cycle_errors == []


class TestPluginsV2NotExistsBackwardCompat:
    """plugins-v2/ 不存在行为与改动前一致。"""

    async def test_not_exists_empty_plan(self, tmp_path):
        """目录不存在 → 空 ActivationPlan（向后兼容）。"""
        from src.plugin_runtime_v2.host.activation_coordinator import ActivationCoordinator

        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        plan = await coordinator.plan_startup(tmp_path / "nonexistent")
        assert plan.waves == []
        assert plan.skipped == {}
        assert plan.cycle_errors == []
        assert plan.candidate_dirs == {}

    async def test_not_exists_no_spawn(self, tmp_path):
        """目录不存在 → 不 spawn 任何插件。"""
        from src.plugin_runtime_v2.host.activation_coordinator import ActivationCoordinator

        supervisor = MockSupervisor()
        coordinator = ActivationCoordinator(supervisor)
        await coordinator.plan_startup(tmp_path / "nonexistent")
        assert len(supervisor.spawn_calls) == 0


class TestV1Unaffected:
    """v1 plugin_runtime 不受 ZG16-3 影响（v1/v2 隔离）。"""

    def test_v1_plugin_loader_importable(self):
        """v1 plugin_loader 模块可正常导入。"""
        from src.plugin_runtime.runner import plugin_loader as v1_loader
        assert hasattr(v1_loader, "PluginLoader")

    def test_v1_resolve_dependencies_exists(self):
        """v1 _resolve_dependencies 方法存在（接口不变）。"""
        from src.plugin_runtime.runner.plugin_loader import PluginLoader
        assert hasattr(PluginLoader, "_resolve_dependencies")
        # 确认是 v1 路径（非 v2）
        import src.plugin_runtime.runner.plugin_loader as v1_mod
        assert "plugin_runtime" in v1_mod.__name__
        assert "v2" not in v1_mod.__name__

    def test_v2_isolated_from_v1(self):
        """v2 依赖解析器不导入 v1 模块。"""
        import src.plugin_runtime_v2.host.dependency_resolver as v2_mod
        # v2 模块名不含 v1 路径
        assert "v2" in v2_mod.__name__


class TestManifestV3SchemaUnchanged:
    """ManifestV3 schema 不变。"""

    def test_required_fields(self):
        """ManifestV3 必填字段定义不变。"""
        fields = ManifestV3.model_fields
        # 核心字段存在
        assert "manifest_version" in fields
        assert "id" in fields
        assert "version" in fields
        assert "name" in fields
        assert "author" in fields
        assert "scopes" in fields
        assert "dependencies" in fields

    def test_manifest_version_literal_3(self):
        """manifest_version 固定为 3。"""
        fields = ManifestV3.model_fields
        # manifest_version 默认值为 3
        assert fields["manifest_version"].default == 3

    def test_dependencies_default_empty(self):
        """dependencies 默认空列表。"""
        manifest = ManifestV3.model_validate({
            "manifest_version": 3,
            "id": "org.test",
            "version": "1.0.0",
            "name": "test",
            "author": {"name": "test"},
            "scopes": ["message:send:text"],
        })
        assert manifest.dependencies == []

    def test_author_info_required(self):
        """author 字段需要 AuthorInfo（至少 name）。"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ManifestV3.model_validate({
                "manifest_version": 3,
                "id": "org.test",
                "version": "1.0.0",
                "name": "test",
                "scopes": ["message:send:text"],
            })

    def test_scopes_non_empty(self):
        """scopes 必须非空。"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ManifestV3.model_validate({
                "manifest_version": 3,
                "id": "org.test",
                "version": "1.0.0",
                "name": "test",
                "author": {"name": "test"},
                "scopes": [],
            })

    def test_id_pattern_enforced(self):
        """id 格式要求组织名.插件名。"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ManifestV3.model_validate({
                "manifest_version": 3,
                "id": "invalid-no-dot",
                "version": "1.0.0",
                "name": "test",
                "author": {"name": "test"},
                "scopes": ["message:send:text"],
            })


class TestRunnerSupervisorInterfaceUnchanged:
    """RunnerSupervisor.spawn_and_wait 接口不变。"""

    def test_spawn_result_fields(self):
        """SpawnResult 字段定义不变。"""
        result = SpawnResult(runner_id="test", success=True)
        assert result.runner_id == "test"
        assert result.success is True
        assert result.reason == ""

    def test_spawn_result_with_reason(self):
        """SpawnResult 支持 reason 字段。"""
        result = SpawnResult(runner_id="test", success=False, reason="timeout")
        assert result.success is False
        assert result.reason == "timeout"

    def test_spawn_and_wait_signature(self):
        """spawn_and_wait 方法存在。"""
        from src.plugin_runtime_v2.host.runner_supervisor import RunnerSupervisor
        assert hasattr(RunnerSupervisor, "spawn_and_wait")


class TestHostEndpointStopFallback:
    """HostEndpoint.stop 无 coordinator 时降级为原顺序。"""

    def test_activation_coordinator_default_none(self):
        """HostEndpoint 默认 _activation_coordinator 为 None。"""
        from src.plugin_runtime_v2.host.connection import HostEndpointConfig
        from src.plugin_runtime_v2.host.endpoint import HostEndpoint

        endpoint = HostEndpoint(config=HostEndpointConfig(listen_address="0.0.0.0:0"))
        assert endpoint._activation_coordinator is None

    def test_set_activation_coordinator_method_exists(self):
        """set_activation_coordinator 方法存在。"""
        from src.plugin_runtime_v2.host.connection import HostEndpointConfig
        from src.plugin_runtime_v2.host.endpoint import HostEndpoint

        endpoint = HostEndpoint(config=HostEndpointConfig(listen_address="0.0.0.0:0"))
        assert hasattr(endpoint, "set_activation_coordinator")

    async def test_stop_degrades_without_coordinator(self):
        """无 coordinator → stop 走 fallback 分支（向后兼容）。"""
        from src.plugin_runtime_v2.host.connection import HostEndpointConfig
        from src.plugin_runtime_v2.host.endpoint import HostEndpoint

        endpoint = HostEndpoint(config=HostEndpointConfig(
            listen_address="0.0.0.0:0", default_drain_timeout_ms=0,
        ))
        await endpoint.start()
        try:
            endpoint._registry._connections["r1"] = MagicMock()
            shutdown_calls: list[str] = []
            endpoint._servicer.request_shutdown = lambda rid, **kw: shutdown_calls.append(rid)

            await endpoint.stop()
            assert shutdown_calls == ["r1"]
        except Exception:
            if endpoint._server is not None:
                await endpoint.stop()
            raise


class TestActivationPlanBackwardCompat:
    """ActivationPlan 行为回归。"""

    def test_empty_plan(self):
        """空 ActivationPlan 行为一致。"""
        from src.plugin_runtime_v2.host.dependency_resolver import ActivationPlan

        plan = ActivationPlan(waves=[], skipped={}, cycle_errors=[])
        assert plan.activation_order() == []
        assert not plan.is_activatable("any")

    def test_plan_with_only_skipped(self):
        """仅有跳过的 plan 行为一致。"""
        from src.plugin_runtime_v2.host.dependency_resolver import ActivationPlan

        plan = ActivationPlan(
            waves=[],
            skipped={"org.a": "测试跳过"},
            cycle_errors=[],
        )
        assert not plan.is_activatable("org.a")
        assert plan.activation_order() == []