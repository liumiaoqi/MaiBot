"""HostEndpoint 单元测试 — gRPC 端点管理生命周期。

覆盖：
- 构造与默认/自定义配置
- 属性访问（listen_address/scope_store/token_service/get_status）
- setter 注入（set_supervisor 双向/set_activation_coordinator/get_supervisor）
- reload_runners（有/无 supervisor）
- stop 逆序卸载（有 coordinator）/原顺序 fallback（无 coordinator）/无 server 直接返回
- stop 取消 cleanup_task
- 值域覆盖（2026-10-17）：坏 manifest 具名入 rejected + 覆盖断言（三栏之外必出声）
"""

import asyncio
import copy
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.plugin_runtime_v2.host.connection import (
    ConnectionState,
    HostEndpointConfig,
    RunnerConnection,
)
from src.plugin_runtime_v2.host.endpoint import HostEndpoint


def _make_connection(runner_id: str, state=ConnectionState.READY) -> RunnerConnection:
    """构造真实 RunnerConnection 用于注册。"""
    return RunnerConnection(
        runner_id=runner_id,
        state=state,
        sdk_version="4.0.0",
        session_token="",
        scopes=[],
    )


class TestHostEndpointConstruct:
    """构造与配置。"""

    def test_default_config(self):
        ep = HostEndpoint()
        assert ep._cfg.listen_address == "127.0.0.1:50051"
        assert ep._server is None
        assert ep._actual_listen_address == ""
        assert ep._activation_coordinator is None
        assert ep._plugin_config_servicer is None

    def test_custom_config(self):
        cfg = HostEndpointConfig(listen_address="0.0.0.0:9999", server_id="sid")
        ep = HostEndpoint(config=cfg)
        assert ep._cfg.listen_address == "0.0.0.0:9999"
        assert ep._cfg.server_id == "sid"

    def test_injected_services(self):
        token = MagicMock()
        scope = MagicMock()
        storage = MagicMock()
        ep = HostEndpoint(
            token_service=token, scope_store=scope, storage_service=storage,
        )
        assert ep._token_service is token
        assert ep._scope_store is scope
        assert ep._storage_service is storage


class TestHostEndpointProperties:
    """属性访问。"""

    def test_listen_address_empty(self):
        ep = HostEndpoint()
        assert ep.listen_address == ""

    def test_scope_store_property(self):
        scope = MagicMock()
        ep = HostEndpoint(scope_store=scope)
        assert ep.scope_store is scope

    def test_token_service_property(self):
        token = MagicMock()
        ep = HostEndpoint(token_service=token)
        assert ep.token_service is token

    def test_get_status_empty(self):
        ep = HostEndpoint()
        assert ep.get_status() == {}

    def test_get_status_with_runner(self):
        ep = HostEndpoint()
        ep._registry.register(_make_connection("r1"))
        status = ep.get_status()
        assert "r1" in status
        assert status["r1"].runner_id == "r1"


class TestHostEndpointSetters:
    """setter 注入。"""

    def test_set_supervisor_bidirectional(self):
        """set_supervisor 双向注入：supervisor.set_servicer + servicer._supervisor。"""
        ep = HostEndpoint()
        sv = MagicMock()
        sv.set_servicer = MagicMock()
        ep.set_supervisor(sv)
        assert ep.get_supervisor() is sv
        sv.set_servicer.assert_called_once_with(ep._servicer)
        assert ep._servicer._supervisor is sv

    def test_set_activation_coordinator(self):
        ep = HostEndpoint()
        coord = MagicMock()
        ep.set_activation_coordinator(coord)
        assert ep._activation_coordinator is coord

    def test_get_supervisor_none(self):
        ep = HostEndpoint()
        assert ep.get_supervisor() is None


class TestHostEndpointReload:
    """reload_runners。"""

    @pytest.mark.asyncio
    async def test_reload_no_supervisor(self):
        ep = HostEndpoint()
        result = await ep.reload_runners(drain_ms=100)
        assert result == {}

    @pytest.mark.asyncio
    async def test_reload_with_supervisor(self):
        ep = HostEndpoint()
        sv = MagicMock()
        sv.set_servicer = MagicMock()
        sv.reload_all = AsyncMock(return_value={"r1": "ok"})
        ep.set_supervisor(sv)
        result = await ep.reload_runners(drain_ms=100)
        assert result == {"r1": "ok"}
        sv.reload_all.assert_awaited_once_with(100)


class TestHostEndpointPluginStates:
    """get_plugin_states() 投影（2026-10-17）— 宿主侧可取事实，不碰 Runner 侧 refcount。"""

    def test_empty_when_nothing_registered(self):
        """一个插件都没登记 ⇒ 空列表（健康检查据此具名出声）。"""
        ep = HostEndpoint()
        assert ep.get_plugin_states() == []

    def test_running_when_activated_and_ready(self):
        """激活 + READY 连接 ⇒ state=running，带 tool_count。"""
        ep = HostEndpoint()
        coord = MagicMock()
        coord.activated = {"p1"}
        coord.skipped = {}
        ep.set_activation_coordinator(coord)
        conn = _make_connection("r1", ConnectionState.READY)
        conn.plugin_id = "p1"
        conn.tools = [object(), object()]
        ep._registry.register(conn)

        states = ep.get_plugin_states()
        assert len(states) == 1
        s = states[0]
        assert s.plugin_id == "p1"
        assert s.state == "running"
        assert s.activated is True
        assert s.connection_state == "ready"
        assert s.tool_count == 2

    def test_skipped_when_activation_failed(self):
        """spawn 失败落 skipped ⇒ state=skipped，reason 透传（运维可见）。"""
        ep = HostEndpoint()
        coord = MagicMock()
        coord.activated = set()
        coord.skipped = {"p_bad": "激活失败: spawn 失败: spawn_timeout"}
        ep.set_activation_coordinator(coord)

        states = ep.get_plugin_states()
        assert len(states) == 1
        assert states[0].plugin_id == "p_bad"
        assert states[0].state == "skipped"
        assert states[0].activated is False
        assert "spawn_timeout" in states[0].skipped_reason

    def test_connecting_when_activated_without_connection(self):
        """已激活但连接面还没登记 ⇒ state=connecting（不假称 running）。"""
        ep = HostEndpoint()
        coord = MagicMock()
        coord.activated = {"p1"}
        coord.skipped = {}
        ep.set_activation_coordinator(coord)

        states = ep.get_plugin_states()
        assert len(states) == 1
        assert states[0].state == "connecting"
        assert states[0].connection_state == ""

    def test_error_when_connection_disconnected(self):
        """连接已断 ⇒ state=error（只报事实，不猜原因）。"""
        ep = HostEndpoint()
        conn = _make_connection("r1", ConnectionState.DISCONNECTED)
        conn.plugin_id = "p1"
        ep._registry.register(conn)

        states = ep.get_plugin_states()
        assert len(states) == 1
        assert states[0].state == "error"
        assert states[0].connection_state == "disconnected"

    def test_no_coordinator_still_projects_connections(self):
        """未注入 coordinator 时仍投影连接面（不因缺一件就全空）。"""
        ep = HostEndpoint()
        conn = _make_connection("r1", ConnectionState.READY)
        conn.plugin_id = "p1"
        ep._registry.register(conn)

        states = ep.get_plugin_states()
        assert [s.plugin_id for s in states] == ["p1"]
        assert states[0].state == "running"


class TestPluginStatesSpawnFailureE2E:
    """spawn 失败 → 真 ActivationCoordinator → 投影可见（走生产链，非手搓 skipped）。"""

    async def test_spawn_failed_plugin_lands_in_skipped(self, tmp_path):
        from src.plugin_runtime_v2.host.activation_coordinator import ActivationCoordinator
        from tests.plugin_runtime_v2.zg16_3_helpers import MockSupervisor, write_plugin_dir

        write_plugin_dir(tmp_path, "org.good")
        write_plugin_dir(tmp_path, "org.bad")
        supervisor = MockSupervisor(fail_ids={"org.bad"}, reason="spawn_timeout")
        coordinator = ActivationCoordinator(supervisor)

        ep = HostEndpoint()
        ep.set_activation_coordinator(coordinator)
        plan = await coordinator.plan_startup(tmp_path)

        assert set(plan.waves[0]) == {"org.bad", "org.good"}
        assert coordinator.activated == {"org.good"}
        assert "org.bad" in coordinator.skipped

        states = {s.plugin_id: s for s in ep.get_plugin_states()}
        assert states["org.good"].state == "connecting"   # 已激活但无连接
        assert states["org.good"].activated is True
        assert states["org.bad"].state == "skipped"
        assert states["org.bad"].activated is False
        assert "spawn_timeout" in states["org.bad"].skipped_reason

    async def test_all_skipped_still_non_empty(self, tmp_path):
        """全部 spawn 失败 ⇒ 状态面仍非空（0 条的含义留给"真没插件"）。"""
        from src.plugin_runtime_v2.host.activation_coordinator import ActivationCoordinator
        from tests.plugin_runtime_v2.zg16_3_helpers import MockSupervisor, write_plugin_dir

        write_plugin_dir(tmp_path, "org.bad")
        supervisor = MockSupervisor(fail_ids={"org.bad"}, reason="spawn_timeout")
        coordinator = ActivationCoordinator(supervisor)
        ep = HostEndpoint()
        ep.set_activation_coordinator(coordinator)
        await coordinator.plan_startup(tmp_path)

        states = ep.get_plugin_states()
        assert len(states) == 1
        assert states[0].state == "skipped"

    async def test_no_plugin_dir_yields_empty(self, tmp_path):
        """插件目录一个都没有 ⇒ 0 条（健康检查据此具名 UNKNOWN，不是静默绿）。"""
        from src.plugin_runtime_v2.host.activation_coordinator import ActivationCoordinator
        from tests.plugin_runtime_v2.zg16_3_helpers import MockSupervisor

        coordinator = ActivationCoordinator(MockSupervisor())
        ep = HostEndpoint()
        ep.set_activation_coordinator(coordinator)
        await coordinator.plan_startup(tmp_path / "nonexistent")

        assert ep.get_plugin_states() == []


class TestPluginStatesValueDomain:
    """值域缺口修复（2026-10-17）— 解析器看到过的每个插件必须落进三栏之一。

    立项背景：`dependency_resolver` 对"解析失败/校验失败/id 重复的先前目录"用
    `dir:<目录名>` 当 key 记 skips，而 `compute_activation_plan` 的
    `if pid in candidates` 把 `dir:` key **全滤掉** ⇒ 这类插件既不在 activated
    也不在 skipped ⇒ **投影面看不见它**（= "值域缺口"：**空间本身没覆盖全部结果**，
    **不是**"抽到 0 条"）。
    """

    async def test_bad_manifest_lands_in_rejected_not_absent(self, tmp_path):
        """证红 ①：坏 manifest ⇒ 修前"不存在"，修后必须**具名**出现（真 coordinator 全链）。

        ⚠️ 三个目录名故意都**不是合法插件 ID** —— 不这样写，`dir:<目录名>` 正好
        等于插件 id 时，这个"缺口"会被键名**偶然掩掉**（`pid in candidates` 就过了）。
        """
        from src.plugin_runtime_v2.host.activation_coordinator import ActivationCoordinator
        from src.plugin_runtime_v2.host.dependency_resolver import compute_activation_plan
        from tests.plugin_runtime_v2.zg16_3_helpers import MockSupervisor, write_plugin_dir

        write_plugin_dir(tmp_path, "org.good")
        bad_illegal_json = write_plugin_dir(
            tmp_path, "org.a", raw_content="{not valid json", dir_name="badillegaljson",
        )
        bad_schema = write_plugin_dir(
            tmp_path, "org.b", raw_content='{"manifest_version": 3}', dir_name="badschemadir",
        )

        plan = compute_activation_plan([bad_illegal_json, bad_schema])
        # 修前现场：skips 里只有 dir: key，而 plan.skipped 把它们**全滤掉** ⇒ 空
        assert plan.skipped == {}
        # 修后：第三栏 rejected **具名**（目录名 + 原因）
        assert set(plan.rejected) == {"dir:badillegaljson", "dir:badschemadir"}
        assert "解析失败" in plan.rejected["dir:badillegaljson"]
        assert "校验失败" in plan.rejected["dir:badschemadir"]

        # 全链：真 coordinator → 真投影（走生产路径，不手搓 rejected）
        coordinator = ActivationCoordinator(MockSupervisor())
        ep = HostEndpoint()
        ep.set_activation_coordinator(coordinator)
        await coordinator.plan_startup(tmp_path)

        states = {s.plugin_id: s for s in ep.get_plugin_states()}
        assert "dir:badillegaljson" in states, "坏 manifest 的插件必须在投影面**具名**出现"
        assert states["dir:badillegaljson"].state == "rejected"
        assert states["dir:badillegaljson"].activated is False
        assert "解析失败" in states["dir:badillegaljson"].skipped_reason
        assert states["dir:badschemadir"].state == "rejected"
        assert states["org.good"].state == "connecting"   # 正常插件不受影响
        assert len(states) == 3  # 全部坏也要可见（"0 条"只留给"真没插件"）

    async def test_all_rejected_still_non_empty(self, tmp_path):
        """全部目录都被拒 ⇒ 状态面仍非空（"0 条"只留给"真没插件"）。"""
        from src.plugin_runtime_v2.host.activation_coordinator import ActivationCoordinator
        from tests.plugin_runtime_v2.zg16_3_helpers import MockSupervisor, write_plugin_dir

        write_plugin_dir(tmp_path, "org.a", raw_content="{not valid json", dir_name="badillegaljson")
        coordinator = ActivationCoordinator(MockSupervisor())
        ep = HostEndpoint()
        ep.set_activation_coordinator(coordinator)
        await coordinator.plan_startup(tmp_path)

        states = ep.get_plugin_states()
        assert len(states) == 1
        assert states[0].state == "rejected"
        assert states[0].plugin_id == "dir:badillegaljson"

    def test_coverage_assertion_passes_on_resolver_output(self, tmp_path):
        """解析器真实产出：三栏（candidates/skipped/rejected）**全覆盖**目录。

        用**解析器同一把尺子**（`scan_plugin_dirs`）取"看到过"的目录集合。
        """
        from src.plugin_runtime_v2.host.dependency_resolver import (
            _check_value_domain,
            compute_activation_plan,
            rejected_dir_names,
            scan_plugin_dirs,
        )
        from tests.plugin_runtime_v2.zg16_3_helpers import make_manifest_dict, write_plugin_dir

        write_plugin_dir(tmp_path, "org.good")
        write_plugin_dir(tmp_path, "org.a", raw_content="{not valid json", dir_name="badillegaljson")
        write_plugin_dir(tmp_path, "org.b", raw_content='{"manifest_version": 3}', dir_name="badschemadir")
        # 自依赖：parse 通过、id 拿得到，但被移出 candidates（rejected 的 key 是**真 id**，
        # 目录名要从 rejected_dir_names 的 dir: 那一支拿）
        write_plugin_dir(tmp_path, "org.a", dependencies=["org.a"], dir_name="selfdepdir")
        # 孤儿（1↔2：candidates ∪ skipped 已覆盖）——断言必须**兼容**它，而不是误报
        for orphan_dir in ("orphanone", "orphantwo"):
            d = tmp_path / orphan_dir
            d.mkdir()
            (d / "manifest.json").write_text(
                json.dumps(make_manifest_dict("org." + orphan_dir)), encoding="utf-8",
            )

        dirs = scan_plugin_dirs(tmp_path)
        plan = compute_activation_plan(dirs)
        assert _check_value_domain(plan, dirs, rejected_dir_names(plan)) == [], \
            "解析器自己的产出必须全覆盖"

    def test_coverage_assertion_speaks_on_gap(self, tmp_path):
        """证红 ②：构造"落在三栏之外" ⇒ **全称断言必须出声**（不是静默通过）。

        这是**值域缺口的正身**：`plan` 抽出来的东西**看起来齐**（波次/跳过都有），
        但解析器实际看到过的目录里有一个**落不进任何一栏** ⇒ 它会在投影面消失。
        空源（抽到 0 条）不会这样：空源是"一条都没抽到"，此处是"**有，但空间里没它**"。
        """
        from src.plugin_runtime_v2.host.dependency_resolver import (
            _check_value_domain,
            compute_activation_plan,
            rejected_dir_names,
        )
        from tests.plugin_runtime_v2.zg16_3_helpers import write_plugin_dir

        write_plugin_dir(tmp_path, "org.a", dir_name="pluginalpha")
        write_plugin_dir(tmp_path, "org.b", raw_content="{not valid json", dir_name="orphandir")
        seen = [tmp_path / "pluginalpha", tmp_path / "orphandir"]

        plan = compute_activation_plan(seen)
        assert _check_value_domain(plan, seen, rejected_dir_names(plan)) == []  # 当前实现全覆盖

        # 模拟"修复前"的形态：拒绝栏被丢掉（原实现里 dir: key 正是这样消失的）
        plan_without_rejected = copy.replace(plan, rejected={})
        gap = _check_value_domain(
            plan_without_rejected, seen, rejected_dir_names(plan_without_rejected),
        )
        assert gap == ["orphandir"], "落在三栏之外的目录必须被全称断言抓住（具名）"

        # ⚠️ 断言**不许猜**目录名：真 ID 的 rejected key 不得被反推成目录名。
        # 反例现场：目录名 `badnodeid` + manifest id `org.badnodeid`（自依赖）⇒ 若拿 ID
        # 去推"目录名 = id 换点成下划线"会得到 `org_badnodeid` ≠ 真实目录名 ⇒ 把**真实
        # 覆盖**误报成缺口。这里用同一份提取逻辑（`rejected_dir_names`）钉住它不猜。
        write_plugin_dir(
            tmp_path / "selfdep", "org.badnodeid",
            dependencies=["org.badnodeid"], dir_name="badnodeid",
        )
        seen_self = [tmp_path / "selfdep" / "badnodeid"]
        plan_self = compute_activation_plan(seen_self)
        assert "badnodeid" not in plan_self.candidate_dirs        # 自依赖 ⇒ 移出候选
        assert "org.badnodeid" in plan_self.rejected              # 具名拒绝（**真 id**）
        assert _check_value_domain(
            plan_self, seen_self, rejected_dir_names(plan_self),
        ) == [], "断言不许拿 ID 反推目录名（否则误报真实覆盖）"

    def test_compute_activation_plan_raises_on_gap(self, tmp_path, monkeypatch):
        """证红 ②（生产路径）：遇到值域缺口 ⇒ `compute_activation_plan` **当场 ValueError**。"""
        from src.plugin_runtime_v2.host import dependency_resolver as dr
        from tests.plugin_runtime_v2.zg16_3_helpers import write_plugin_dir

        write_plugin_dir(tmp_path, "org.b", raw_content="{not valid json", dir_name="orphandir")

        real_parse = dr.parse_candidate_manifests
        seen = [tmp_path / "orphandir"]

        def _parse_dropping_rejects(plugin_dirs):
            # 模拟旧口径：解析器看到了，但三栏都没收它（dir: key 被过滤的那个世界）
            candidates, skips, _rejects = real_parse(plugin_dirs)
            return candidates, skips, {}

        monkeypatch.setattr(dr, "parse_candidate_manifests", _parse_dropping_rejects)
        with pytest.raises(ValueError) as excinfo:
            dr.compute_activation_plan(seen)
        assert "值域缺口" in str(excinfo.value)
        assert "orphandir" in str(excinfo.value)



class TestHostEndpointStop:
    """stop 生命周期：逆序卸载/fallback/无 server/cleanup_task。"""

    @pytest.mark.asyncio
    async def test_stop_no_server(self):
        """无 server 时 stop 直接返回。"""
        ep = HostEndpoint()
        await ep.stop()  # 不抛异常

    @pytest.mark.asyncio
    async def test_stop_with_coordinator_reverse_unload(self):
        """有 coordinator 时按依赖图逆序卸载。"""
        ep = HostEndpoint()
        ep._server = MagicMock()
        ep._server.stop = AsyncMock()
        ep._registry.register(_make_connection("r1"))
        ep._registry.register(_make_connection("r2"))
        # mock heartbeat.stop + servicer.request_shutdown
        ep._heartbeat_mgr.stop = MagicMock()
        ep._servicer.request_shutdown = MagicMock()
        # coordinator 返回逆序
        coord = MagicMock()
        coord.plan_unload = MagicMock(return_value=["r2", "r1"])
        coord.on_plugin_unloaded = MagicMock()
        ep.set_activation_coordinator(coord)
        ep._cfg = HostEndpointConfig(default_drain_timeout_ms=0)
        server = ep._server  # stop 末尾会置 None，先保存引用

        await ep.stop()

        # 验证逆序卸载
        plan_unload_arg = coord.plan_unload.call_args[0][0]
        assert plan_unload_arg == {"r1", "r2"}
        # request_shutdown 按逆序调用
        shutdown_calls = [c.args[0] for c in ep._servicer.request_shutdown.call_args_list]
        assert shutdown_calls == ["r2", "r1"]
        coord.on_plugin_unloaded.assert_any_call("r2")
        coord.on_plugin_unloaded.assert_any_call("r1")
        server.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_without_coordinator_fallback_order(self):
        """无 coordinator 时按原顺序卸载（向后兼容）。"""
        ep = HostEndpoint()
        ep._server = MagicMock()
        ep._server.stop = AsyncMock()
        ep._registry.register(_make_connection("r1"))
        ep._registry.register(_make_connection("r2"))
        ep._heartbeat_mgr.stop = MagicMock()
        ep._servicer.request_shutdown = MagicMock()
        ep._cfg = HostEndpointConfig(default_drain_timeout_ms=0)
        server = ep._server

        await ep.stop()

        # 无 coordinator → 原顺序（registry 插入序）
        shutdown_calls = [c.args[0] for c in ep._servicer.request_shutdown.call_args_list]
        assert set(shutdown_calls) == {"r1", "r2"}
        server.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_cancels_cleanup_task(self):
        """stop 取消 token cleanup 后台任务。"""
        ep = HostEndpoint(token_service=MagicMock())
        ep._server = MagicMock()
        ep._server.stop = AsyncMock()

        async def cleanup():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                pass

        ep._cleanup_task = asyncio.create_task(cleanup())
        ep._cfg = HostEndpointConfig(default_drain_timeout_ms=0)

        await ep.stop()
        assert ep._cleanup_task is None

    @pytest.mark.asyncio
    async def test_stop_drain_waits(self):
        """drain_ms > 0 时 stop 等待排空。"""
        ep = HostEndpoint()
        ep._server = MagicMock()
        ep._server.stop = AsyncMock()
        ep._registry.register(_make_connection("r1"))
        ep._heartbeat_mgr.stop = MagicMock()
        ep._servicer.request_shutdown = MagicMock()
        ep._cfg = HostEndpointConfig(default_drain_timeout_ms=50)

        import time as time_mod
        start = time_mod.monotonic()
        await ep.stop()
        elapsed = time_mod.monotonic() - start
        # 至少等待了 50ms
        assert elapsed >= 0.04  # 留点容差


class TestHostEndpointCleanupLoop:
    """_cleanup_loop 后台任务。"""

    @pytest.mark.asyncio
    async def test_cleanup_loop_cancelled_silent(self):
        """_cleanup_loop 被 cancel 时静默退出。"""
        ep = HostEndpoint(token_service=MagicMock())
        task = asyncio.create_task(ep._cleanup_loop())
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass  # 正常取消静默

    @pytest.mark.asyncio
    async def test_cleanup_loop_calls_cleanup(self, monkeypatch):
        """_cleanup_loop 定期调用 token_service.cleanup_expired。"""
        token = MagicMock()
        token.cleanup_expired = MagicMock()
        ep = HostEndpoint(token_service=token)

        real_sleep = asyncio.sleep
        call_count = 0

        async def fast_sleep(_seconds):
            nonlocal call_count
            call_count += 1
            if call_count > 2:
                raise asyncio.CancelledError()
            await real_sleep(0.01)

        monkeypatch.setattr(asyncio, "sleep", fast_sleep)
        task = asyncio.create_task(ep._cleanup_loop())
        try:
            await task
        except asyncio.CancelledError:
            pass
        token.cleanup_expired.assert_called()