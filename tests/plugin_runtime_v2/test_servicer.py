"""_PluginHostServicer / PluginConfigServicer 单元测试 — gRPC servicer 核心逻辑。

覆盖：
- 模块级纯函数：_parse_version_tuple / _check_sdk_version
- LoadAlert dataclass + check_scopes_completeness（v1 跳过/scopes 缺失/Tier 1 缺失/检测失败降级）
- _emit_load_alert best-effort
- _PluginHostServicer._validate_hello（各种拒绝原因 + 成功）
- _PluginHostServicer.RegisterComponents（成功/状态非法/缺 plugin_id/重复名/限流）
- _PluginHostServicer.request_shutdown（outbox 背压 QueueFull）
- _PluginHostServicer._resolve_runner_id / _check_plugin_scope
- PluginConfigServicer.UpdatePluginConfig（scope 校验/成功/失败）
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.plugin_runtime_v2.host.connection import (
    ConnectionState,
    HostEndpointConfig,
)
from src.plugin_runtime_v2.host.servicer import (
    LoadAlert,
    PluginConfigServicer,
    _check_sdk_version,
    _emit_load_alert,
    _parse_version_tuple,
    _PluginHostServicer,
    check_scopes_completeness,
)


# ── 辅助构造 ──────────────────────────────────────────────


def _make_servicer(
    *,
    registry=None,
    token_service=None,
    scope_store=None,
    rate_limiter=None,
    host_bridge=None,
    storage_service=None,
) -> _PluginHostServicer:
    """构造 _PluginHostServicer，registry 默认 mock 且 has()=False。"""
    reg = registry or MagicMock()
    if registry is None:
        reg.has.return_value = False
    return _PluginHostServicer(
        registry=reg,
        heartbeat_mgr=MagicMock(),
        config=HostEndpointConfig(),
        host_bridge=host_bridge,
        token_service=token_service,
        scope_store=scope_store,
        rate_limiter=rate_limiter,
        storage_service=storage_service,
    )


def _make_hello(
    runner_id="r1",
    sdk_version="4.0.0",
    session_token="",
    scopes=None,
) -> MagicMock:
    """构造 HelloPayload mock。"""
    return MagicMock(
        runner_id=runner_id,
        sdk_version=sdk_version,
        session_token=session_token,
        scopes=scopes or [],
        runner_listen_address="",
    )


# ── 模块级纯函数 ──────────────────────────────────────────


class TestParseVersionTuple:
    """_parse_version_tuple 版本字符串解析。"""

    def test_normal(self):
        assert _parse_version_tuple("4.1.2") == (4, 1, 2)

    def test_two_parts(self):
        assert _parse_version_tuple("4.1") == (4, 1)

    def test_single_part(self):
        assert _parse_version_tuple("4") == (4,)

    def test_invalid_non_numeric(self):
        assert _parse_version_tuple("4.x.2") == ()

    def test_empty(self):
        assert _parse_version_tuple("") == ()



class TestCheckSdkVersion:
    """_check_sdk_version 范围校验 [4.0.0, 5.0.0)。"""

    def test_at_min_included(self):
        assert _check_sdk_version("4.0.0") is True

    def test_mid_range(self):
        assert _check_sdk_version("4.5.0") is True

    def test_below_min(self):
        assert _check_sdk_version("3.9.9") is False

    def test_at_max_excluded(self):
        assert _check_sdk_version("5.0.0") is False

    def test_above_max(self):
        assert _check_sdk_version("5.1.0") is False

    def test_invalid(self):
        assert _check_sdk_version("invalid") is False


# ── LoadAlert + check_scopes_completeness ─────────────────


class TestLoadAlert:
    """LoadAlert dataclass。"""

    def test_warning_alert(self):
        alert = LoadAlert(
            plugin_id="p1", alert_level="warning", is_tier1=False, timestamp=0.0,
        )
        assert alert.plugin_id == "p1"
        assert alert.alert_level == "warning"
        assert alert.missing_scopes == []

    def test_error_alert_with_missing(self):
        alert = LoadAlert(
            plugin_id="p1",
            alert_level="error",
            is_tier1=True,
            timestamp=0.0,
            missing_scopes=["scope:a"],
        )
        assert alert.is_tier1
        assert alert.missing_scopes == ["scope:a"]


class TestCheckScopesCompleteness:
    """check_scopes_completeness 纯逻辑函数。"""

    def test_v1_skipped(self):
        """v1 插件不触发检测。"""
        result = check_scopes_completeness("p1", {}, is_v2=False)
        assert result is None

    def test_scopes_empty_warning(self):
        """scopes 空 → warning。"""
        result = check_scopes_completeness("p1", {"scopes": []}, is_v2=True)
        assert result is not None
        assert result.alert_level == "warning"
        assert result.plugin_id == "p1"
        assert not result.is_tier1

    def test_scopes_field_absent_warning(self):
        """scopes 字段缺失 → warning。"""
        result = check_scopes_completeness("p1", {}, is_v2=True)
        assert result is not None
        assert result.alert_level == "warning"

    def test_scopes_wrong_type_skipped(self):
        """scopes 字段格式错误 → 跳过返回 None。"""
        result = check_scopes_completeness(
            "p1", {"scopes": "not-a-list"}, is_v2=True,
        )
        assert result is None

    def test_tier1_missing_error(self):
        """Tier 1 scope 缺失 → error。"""
        with patch(
            "src.plugin_runtime_v2.host.servicer.Tier1Detector.detect",
            return_value=["scope:a", "scope:b"],
        ):
            result = check_scopes_completeness(
                "p1", {"scopes": ["scope:a"]}, is_v2=True, plugin_code_path="/fake",
            )
        assert result is not None
        assert result.alert_level == "error"
        assert result.is_tier1
        assert result.missing_scopes == ["scope:b"]

    def test_tier1_detect_failure_degrade(self):
        """Tier 1 检测失败 → 降级返回 None。"""
        with patch(
            "src.plugin_runtime_v2.host.servicer.Tier1Detector.detect",
            side_effect=Exception("boom"),
        ):
            result = check_scopes_completeness(
                "p1", {"scopes": ["scope:a"]}, is_v2=True, plugin_code_path="/fake",
            )
        assert result is None

    def test_no_missing_returns_none(self):
        """scopes 完整无缺失 → None。"""
        with patch(
            "src.plugin_runtime_v2.host.servicer.Tier1Detector.detect",
            return_value=["scope:a"],
        ):
            result = check_scopes_completeness(
                "p1", {"scopes": ["scope:a"]}, is_v2=True, plugin_code_path="/fake",
            )
        assert result is None

    def test_no_code_path_skips_tier1(self):
        """plugin_code_path=None → 跳过 Tier 1 检测，scopes 非空 → None。"""
        result = check_scopes_completeness(
            "p1", {"scopes": ["scope:a"]}, is_v2=True, plugin_code_path=None,
        )
        assert result is None


class TestEmitLoadAlert:
    """_emit_load_alert best-effort 不抛异常。"""

    def test_emit_warning_no_raise(self):
        alert = LoadAlert(
            plugin_id="p1", alert_level="warning", is_tier1=False, timestamp=0.0,
        )
        _emit_load_alert(alert)  # best-effort

    def test_emit_error_no_raise(self):
        alert = LoadAlert(
            plugin_id="p1",
            alert_level="error",
            is_tier1=True,
            timestamp=0.0,
            missing_scopes=["s"],
        )
        _emit_load_alert(alert)  # best-effort


# ── _PluginHostServicer._validate_hello ───────────────────


class TestValidateHello:
    """_validate_hello 握手校验各种分支。"""

    def test_missing_runner_id(self):
        servicer = _make_servicer()
        accept, reason, _ = servicer._validate_hello(_make_hello(runner_id=""))
        assert not accept
        assert "runner_id" in reason

    def test_missing_sdk_version(self):
        servicer = _make_servicer()
        accept, reason, _ = servicer._validate_hello(_make_hello(sdk_version=""))
        assert not accept
        assert "sdk_version" in reason

    def test_missing_session_token_with_token_service(self):
        """有 token_service 但 session_token 空 → 拒绝。"""
        servicer = _make_servicer(token_service=MagicMock())
        accept, reason, _ = servicer._validate_hello(_make_hello(session_token=""))
        assert not accept
        assert "session_token" in reason

    def test_runner_already_connected(self):
        registry = MagicMock()
        registry.has.return_value = True
        servicer = _make_servicer(registry=registry)
        accept, reason, _ = servicer._validate_hello(_make_hello())
        assert not accept
        assert reason == "RUNNER_ALREADY_CONNECTED"

    def test_sdk_version_mismatch(self):
        servicer = _make_servicer()
        accept, reason, _ = servicer._validate_hello(_make_hello(sdk_version="3.0.0"))
        assert not accept
        assert reason == "SDK_VERSION_MISMATCH"

    def test_token_invalid(self):
        token_svc = MagicMock()
        token_svc.validate_session.return_value = (False, "")
        servicer = _make_servicer(token_service=token_svc)
        accept, reason, _ = servicer._validate_hello(
            _make_hello(session_token="bad"),
        )
        assert not accept
        assert reason == "TOKEN_INVALID"

    def test_valid_no_token_service(self):
        """无 token_service 时 session_token 可空，校验通过。"""
        servicer = _make_servicer()
        accept, reason, pid = servicer._validate_hello(_make_hello())
        assert accept
        assert reason == ""
        assert pid == ""

    def test_valid_with_token(self):
        """token 有效 → 返回 plugin_id。"""
        token_svc = MagicMock()
        token_svc.validate_session.return_value = (True, "plugin-1")
        servicer = _make_servicer(token_service=token_svc)
        accept, reason, pid = servicer._validate_hello(
            _make_hello(session_token="good"),
        )
        assert accept
        assert pid == "plugin-1"


# ── _PluginHostServicer.RegisterComponents ────────────────


class TestRegisterComponents:
    """RegisterComponents 一元 RPC。"""

    @staticmethod
    def _setup(peer="peer-1", state=ConnectionState.REGISTERING):
        registry = MagicMock()
        conn = MagicMock()
        conn.state = state
        conn.runner_id = "r1"
        conn.runner_listen_address = ""
        conn._peer = peer
        registry.get.return_value = conn
        registry.get_all.return_value = {"r1": conn}
        servicer = _make_servicer(registry=registry)
        ctx = MagicMock()
        ctx.peer.return_value = peer
        return servicer, registry, conn, ctx

    @pytest.mark.asyncio
    async def test_runner_not_found_no_peer_match(self):
        """_resolve_runner_id 无匹配 → RUNNER_NOT_FOUND。"""
        registry = MagicMock()
        registry.get_all.return_value = {}  # 无连接
        servicer = _make_servicer(registry=registry)
        ctx = MagicMock()
        ctx.peer.return_value = "peer-x"
        request = MagicMock()
        response = await servicer.RegisterComponents(request, ctx)
        assert not response.accepted
        assert response.reasons == ["RUNNER_NOT_FOUND"]

    @pytest.mark.asyncio
    async def test_runner_not_in_registry(self):
        """peer 匹配但 registry.get 返回 None。"""
        registry = MagicMock()
        conn = MagicMock()
        conn._peer = "peer-1"
        registry.get.return_value = None
        registry.get_all.return_value = {"r1": conn}
        servicer = _make_servicer(registry=registry)
        ctx = MagicMock()
        ctx.peer.return_value = "peer-1"
        request = MagicMock()
        response = await servicer.RegisterComponents(request, ctx)
        assert not response.accepted

    @pytest.mark.asyncio
    async def test_invalid_state(self):
        """连接状态非 REGISTERING → 拒绝。"""
        servicer, _, conn, ctx = self._setup(state=ConnectionState.HANDSHAKING)
        request = MagicMock()
        request.plugin_id = "p1"
        response = await servicer.RegisterComponents(request, ctx)
        assert not response.accepted
        assert "INVALID_STATE" in response.reasons[0]

    @pytest.mark.asyncio
    async def test_missing_plugin_id(self):
        servicer, _, _, ctx = self._setup()
        request = MagicMock()
        request.plugin_id = ""
        response = await servicer.RegisterComponents(request, ctx)
        assert not response.accepted
        assert response.reasons == ["MISSING_PLUGIN_ID"]

    @pytest.mark.asyncio
    async def test_rate_limited(self):
        registry = MagicMock()
        conn = MagicMock()
        conn.state = ConnectionState.REGISTERING
        conn._peer = "peer-1"
        registry.get.return_value = conn
        registry.get_all.return_value = {"r1": conn}
        rate_limiter = MagicMock()
        rate_limiter.check.return_value = False
        servicer = _make_servicer(
            registry=registry, rate_limiter=rate_limiter,
        )
        ctx = MagicMock()
        ctx.peer.return_value = "peer-1"
        request = MagicMock()
        request.plugin_id = "p1"
        response = await servicer.RegisterComponents(request, ctx)
        assert not response.accepted
        assert response.reasons == ["RATE_LIMIT_EXCEEDED"]

    @pytest.mark.asyncio
    async def test_duplicate_tool_name(self):
        servicer, _, _, ctx = self._setup()
        tool1 = MagicMock()
        tool1.name = "dup"
        tool2 = MagicMock()
        tool2.name = "dup"
        request = MagicMock()
        request.plugin_id = "p1"
        request.plugin_version = "1.0.0"
        request.tools = [tool1, tool2]
        request.events = []
        response = await servicer.RegisterComponents(request, ctx)
        assert not response.accepted
        assert "DUPLICATE_TOOL_NAME" in response.reasons[0]

    @pytest.mark.asyncio
    async def test_duplicate_event_name(self):
        servicer, _, _, ctx = self._setup()
        ev1 = MagicMock()
        ev1.name = "dup"
        ev2 = MagicMock()
        ev2.name = "dup"
        request = MagicMock()
        request.plugin_id = "p1"
        request.plugin_version = "1.0.0"
        request.tools = []
        request.events = [ev1, ev2]
        response = await servicer.RegisterComponents(request, ctx)
        assert not response.accepted
        assert "DUPLICATE_EVENT_NAME" in response.reasons[0]

    @pytest.mark.asyncio
    async def test_register_success(self):
        """成功注册：状态转 READY，组件存储。"""
        servicer, _, conn, ctx = self._setup()
        tool = MagicMock()
        tool.name = "tool1"
        event = MagicMock()
        event.name = "event1"
        request = MagicMock()
        request.plugin_id = "p1"
        request.plugin_version = "1.0.0"
        request.tools = [tool]
        request.events = [event]
        response = await servicer.RegisterComponents(request, ctx)
        assert response.accepted
        assert conn.plugin_id == "p1"
        assert conn.plugin_version == "1.0.0"
        conn.transition.assert_called_once_with(ConnectionState.READY)

    @pytest.mark.asyncio
    async def test_register_success_with_host_bridge(self):
        """有 host_bridge 时调用 on_runner_registered。"""
        bridge = MagicMock()
        bridge.on_runner_registered = MagicMock()
        registry = MagicMock()
        conn = MagicMock()
        conn.state = ConnectionState.REGISTERING
        conn.runner_id = "r1"
        conn.runner_listen_address = "addr"
        conn._peer = "peer-1"
        registry.get.return_value = conn
        registry.get_all.return_value = {"r1": conn}
        servicer = _make_servicer(registry=registry, host_bridge=bridge)
        ctx = MagicMock()
        ctx.peer.return_value = "peer-1"
        request = MagicMock()
        request.plugin_id = "p1"
        request.plugin_version = "1.0.0"
        request.tools = []
        request.events = []
        await servicer.RegisterComponents(request, ctx)
        bridge.on_runner_registered.assert_called_once()


# ── _PluginHostServicer.request_shutdown + outbox 背压 ───


class TestRequestShutdown:
    """request_shutdown outbox 注入 + 背压。"""

    def test_no_outbox_silent(self):
        """outbox 不存在时静默返回。"""
        servicer = _make_servicer()
        servicer.request_shutdown("nonexistent")  # 不抛异常

    @pytest.mark.asyncio
    async def test_puts_shutdown_in_outbox(self):
        """正常放入 ShutdownRequest。"""
        servicer = _make_servicer()
        outbox: asyncio.Queue = asyncio.Queue(maxsize=64)
        servicer._outboxes["r1"] = outbox
        servicer.request_shutdown("r1", reason="test", drain_ms=100)
        msg = outbox.get_nowait()
        assert msg.shutdown.reason == "test"
        assert msg.shutdown.drain_timeout_ms == 100

    @pytest.mark.asyncio
    async def test_outbox_full_silent(self):
        """P2: outbox 满时 QueueFull 静默忽略，不抛异常。"""
        servicer = _make_servicer()
        outbox: asyncio.Queue = asyncio.Queue(maxsize=1)
        outbox.put_nowait(MagicMock())  # 填满
        servicer._outboxes["r1"] = outbox
        servicer.request_shutdown("r1")  # QueueFull 被捕获，不抛


# ── _PluginHostServicer._resolve_runner_id / _check_plugin_scope ─


class TestResolveRunnerId:
    """_resolve_runner_id peer 匹配。"""

    def test_match_peer(self):
        registry = MagicMock()
        conn = MagicMock()
        conn._peer = "peer-1"
        registry.get_all.return_value = {"r1": conn}
        servicer = _make_servicer(registry=registry)
        ctx = MagicMock()
        ctx.peer.return_value = "peer-1"
        assert servicer._resolve_runner_id(ctx) == "r1"

    def test_no_match(self):
        registry = MagicMock()
        conn = MagicMock()
        conn._peer = "peer-1"
        registry.get_all.return_value = {"r1": conn}
        servicer = _make_servicer(registry=registry)
        ctx = MagicMock()
        ctx.peer.return_value = "peer-2"
        assert servicer._resolve_runner_id(ctx) == ""

    def test_empty_registry(self):
        registry = MagicMock()
        registry.get_all.return_value = {}
        servicer = _make_servicer(registry=registry)
        ctx = MagicMock()
        ctx.peer.return_value = "peer-1"
        assert servicer._resolve_runner_id(ctx) == ""


class TestCheckPluginScope:
    """_check_plugin_scope scope 校验。"""

    def test_no_scope_store(self):
        servicer = _make_servicer()
        assert servicer._check_plugin_scope("p1", "scope:a") is False

    def test_has_scope(self):
        scope_store = MagicMock()
        scope_store.get_granted_scopes.return_value = {"scope:a", "scope:b"}
        servicer = _make_servicer(scope_store=scope_store)
        assert servicer._check_plugin_scope("p1", "scope:a") is True

    def test_missing_scope(self):
        scope_store = MagicMock()
        scope_store.get_granted_scopes.return_value = {"scope:b"}
        servicer = _make_servicer(scope_store=scope_store)
        assert servicer._check_plugin_scope("p1", "scope:a") is False


# ── PluginConfigServicer.UpdatePluginConfig ───────────────


class TestPluginConfigServicer:
    """PluginConfigServicer 配置推送 RPC。"""

    @pytest.mark.asyncio
    async def test_scope_denied(self):
        """scope 校验失败 → 拒绝。"""
        scope_val = MagicMock()
        scope_val.validate.return_value = False
        servicer = PluginConfigServicer(MagicMock(), scope_val)
        request = MagicMock()
        ctx = MagicMock()
        response = await servicer.UpdatePluginConfig(request, ctx)
        assert not response.success

    @pytest.mark.asyncio
    async def test_update_success(self):
        """成功推送配置。"""
        config_mgr = MagicMock()
        config_mgr.handle_file_change = AsyncMock()
        config_mgr._revision_store.get.return_value = 1  # new_revision 是 int 字段
        scope_val = MagicMock()
        scope_val.validate.return_value = True
        servicer = PluginConfigServicer(config_mgr, scope_val)
        request = MagicMock()
        request.plugin_id = "p1"
        request.source = "file"
        ctx = MagicMock()
        response = await servicer.UpdatePluginConfig(request, ctx)
        assert response.success
        assert response.new_revision == 1
        config_mgr.handle_file_change.assert_awaited_once_with("p1", "file")

    @pytest.mark.asyncio
    async def test_update_failure(self):
        """handle_file_change 抛异常 → 返回失败 + error。"""
        config_mgr = MagicMock()
        config_mgr.handle_file_change = AsyncMock(side_effect=Exception("boom"))
        scope_val = MagicMock()
        scope_val.validate.return_value = True
        servicer = PluginConfigServicer(config_mgr, scope_val)
        request = MagicMock()
        request.plugin_id = "p1"
        request.source = "file"
        ctx = MagicMock()
        response = await servicer.UpdatePluginConfig(request, ctx)
        assert not response.success
        assert "boom" in response.error