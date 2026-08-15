"""ZG16-5: ToolRouter 审计钩子测试。

覆盖 Tier 1 触计触发、非 Tier 1 不审计、审计不阻断、
审计模块未初始化跳过、既有逻辑不变、无 scopes 不审计。
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.plugin_runtime_v2.runner.tool_router import ToolRouter
from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin


class FakePlugin(MaiBotPlugin):
    plugin_id = "test.plugin"
    scopes: list[str] = []


@pytest.fixture
def router() -> ToolRouter:
    return ToolRouter()


@pytest.fixture
def plugin() -> FakePlugin:
    return FakePlugin()


class TestTier1TriggersAudit:
    """Tier 1 scope → 触发审计。"""

    async def test_tier1_triggers_audit(self, router, plugin):
        """插件 scopes 含 Tier 1 → record 被调用。"""
        plugin.scopes = ["system:execute:cli"]
        plugin.plugin_id = "org.test.cli"

        mock_recorder = MagicMock()
        mock_recorder.record = AsyncMock()
        with patch(
            "src.plugin_runtime_v2.runner.tool_router.get_scope_audit_recorder",
            return_value=mock_recorder,
        ):
            async def handler(plg, args):
                return {"ok": True}
            router.register("t1", plugin, handler)
            resp = await router.execute("t1", {"cmd": "ls"})
            assert resp.success
            mock_recorder.record.assert_called_once()
            call_kwargs = mock_recorder.record.call_args.kwargs
            assert call_kwargs["plugin_id"] == "org.test.cli"
            assert call_kwargs["scope"] == "system:execute:cli"

    async def test_multiple_tier1_all_audited(self, router, plugin):
        """多个 Tier 1 scope → 均审计。"""
        plugin.scopes = ["system:execute:cli", "network:fetch:url"]
        plugin.plugin_id = "org.test.multi"

        mock_recorder = MagicMock()
        mock_recorder.record = AsyncMock()
        with patch(
            "src.plugin_runtime_v2.runner.tool_router.get_scope_audit_recorder",
            return_value=mock_recorder,
        ):
            async def handler(plg, args):
                return {"ok": True}
            router.register("t1", plugin, handler)
            await router.execute("t1", {})
            assert mock_recorder.record.call_count == 2


class TestNonTier1NoAudit:
    """非 Tier 1 scope → 不审计。"""

    async def test_non_tier1_no_audit(self, router, plugin):
        plugin.scopes = ["message:send:text"]
        plugin.plugin_id = "org.test.msg"

        mock_recorder = MagicMock()
        mock_recorder.record = AsyncMock()
        with patch(
            "src.plugin_runtime_v2.runner.tool_router.get_scope_audit_recorder",
            return_value=mock_recorder,
        ):
            async def handler(plg, args):
                return {"ok": True}
            router.register("t1", plugin, handler)
            resp = await router.execute("t1", {})
            assert resp.success
            mock_recorder.record.assert_not_called()


class TestAuditNotBlocking:
    """审计异常不阻断执行。"""

    async def test_record_raises_execute_still_succeeds(self, router, plugin):
        """record 抛异常 → execute 仍返回成功结果。"""
        plugin.scopes = ["system:execute:cli"]
        plugin.plugin_id = "org.test.boom"

        mock_recorder = MagicMock()
        mock_recorder.record = AsyncMock(side_effect=RuntimeError("audit boom"))
        with patch(
            "src.plugin_runtime_v2.runner.tool_router.get_scope_audit_recorder",
            return_value=mock_recorder,
        ):
            async def handler(plg, args):
                return {"ok": True}
            router.register("t1", plugin, handler)
            resp = await router.execute("t1", {})
            assert resp.success
            assert json.loads(resp.result) == {"ok": True}


class TestAuditModuleNotInitialized:
    """审计模块未初始化 → 跳过审计，正常执行。"""

    async def test_recorder_none_skip_audit(self, router, plugin):
        plugin.scopes = ["system:execute:cli"]
        plugin.plugin_id = "org.test.noinit"

        with patch(
            "src.plugin_runtime_v2.runner.tool_router.get_scope_audit_recorder",
            return_value=None,
        ):
            async def handler(plg, args):
                return {"ok": True}
            router.register("t1", plugin, handler)
            resp = await router.execute("t1", {})
            assert resp.success


class TestPluginWithoutScopes:
    """插件无 scopes → 不审计。"""

    async def test_empty_scopes_no_audit(self, router, plugin):
        plugin.scopes = []
        plugin.plugin_id = "org.test.noscope"

        mock_recorder = MagicMock()
        mock_recorder.record = AsyncMock()
        with patch(
            "src.plugin_runtime_v2.runner.tool_router.get_scope_audit_recorder",
            return_value=mock_recorder,
        ):
            async def handler(plg, args):
                return {"ok": True}
            router.register("t1", plugin, handler)
            resp = await router.execute("t1", {})
            assert resp.success
            mock_recorder.record.assert_not_called()

    async def test_no_scopes_attr_no_audit(self, router):
        """插件无 scopes 属性 → 不审计。"""
        plugin_obj = MagicMock()
        plugin_obj.plugin_id = "org.test.noattr"
        # 不设 scopes 属性 → getattr 默认 []
        del plugin_obj.scopes

        mock_recorder = MagicMock()
        mock_recorder.record = AsyncMock()
        with patch(
            "src.plugin_runtime_v2.runner.tool_router.get_scope_audit_recorder",
            return_value=mock_recorder,
        ):
            async def handler(plg, args):
                return {"ok": True}
            router.register("t1", plugin_obj, handler)
            resp = await router.execute("t1", {})
            assert resp.success
            mock_recorder.record.assert_not_called()


class TestExistingLogicUnchanged:
    """既有逻辑不变。"""

    async def test_tool_not_found(self, router):
        resp = await router.execute("ghost", {})
        assert not resp.success
        assert resp.error == "TOOL_NOT_FOUND"

    async def test_execution_error(self, router, plugin):
        plugin.scopes = []
        async def broken(plg, args):
            raise RuntimeError("boom")
        router.register("broken", plugin, broken)
        resp = await router.execute("broken", {})
        assert not resp.success
        assert "EXECUTION_ERROR" in resp.error

    async def test_timeout(self, router, plugin):
        plugin.scopes = []
        async def slow(plg, args):
            await asyncio.sleep(10)
        router.register("slow", plugin, slow)
        resp = await router.execute("slow", {}, timeout_ms=10)
        assert not resp.success
        assert resp.error == "TIMEOUT"

    async def test_success_result(self, router, plugin):
        plugin.scopes = []
        async def handler(plg, args):
            return {"data": 42}
        router.register("ok", plugin, handler)
        resp = await router.execute("ok", {"x": 1})
        assert resp.success
        assert json.loads(resp.result) == {"data": 42}

    async def test_refcount_acquire_release(self, router, plugin):
        """refcount acquire/release 逻辑不变。"""
        plugin.scopes = []
        refcount = MagicMock()
        refcount.try_acquire.return_value = True
        refcount.release = MagicMock()

        async def handler(plg, args):
            return {"ok": True}
        router.register("rc", plugin, handler, refcount=refcount)
        resp = await router.execute("rc", {})
        assert resp.success
        refcount.try_acquire.assert_called_once()
        refcount.release.assert_called_once()

    async def test_refcount_going(self, router, plugin):
        """插件 GOING 中 → 拒绝。"""
        plugin.scopes = []
        refcount = MagicMock()
        refcount.try_acquire.return_value = False

        async def handler(plg, args):
            return {"ok": True}
        router.register("going", plugin, handler, refcount=refcount)
        resp = await router.execute("going", {})
        assert not resp.success
        assert resp.error == "PLUGIN_GOING"