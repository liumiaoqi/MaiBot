"""MutePlugin SDK 迁移回归测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from maibot_sdk.context import PluginContext
from maibot_sdk.plugin import MaiBotPlugin

from plugins.MutePlugin.plugin import create_plugin
from src.core.tooling import ToolExecutionContext, ToolInvocation
from src.plugin_runtime.component_query import ComponentQueryService
from src.plugin_runtime.runner.manifest_validator import ManifestValidator


def _build_plugin() -> MaiBotPlugin:
    """构造已注入默认配置的插件实例。"""

    plugin = create_plugin()
    plugin.set_plugin_config(plugin.get_default_config())
    return plugin


def test_mute_plugin_manifest_is_valid_v2() -> None:
    """MutePlugin 的 manifest 应符合当前运行时要求。"""

    validator = ManifestValidator(host_version="1.0.0", sdk_version="2.3.0")
    manifest = validator.load_from_plugin_path(Path("plugins/MutePlugin"))

    assert manifest is not None
    assert manifest.id == "sengokucola.mute-plugin"
    assert manifest.manifest_version == 2


def test_create_plugin_returns_sdk_plugin() -> None:
    """插件入口应返回 SDK 插件实例。"""

    plugin = create_plugin()

    assert isinstance(plugin, MaiBotPlugin)


@pytest.mark.asyncio
async def test_mute_command_calls_napcat_group_ban_api() -> None:
    """手动禁言命令应通过 NapCat Adapter 新 API 执行。"""

    plugin = _build_plugin()
    plugin.set_plugin_config(
        {
            **plugin.get_default_config(),
            "components": {
                "enable_smart_mute": True,
                "enable_mute_command": True,
            },
        }
    )

    capability_calls: List[Dict[str, Any]] = []

    async def fake_rpc_call(method: str, plugin_id: str = "", payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        assert method == "cap.call"
        assert payload is not None
        capability_calls.append(payload)

        capability = payload["capability"]
        if capability == "person.get_id_by_name":
            return {"success": True, "person_id": "person-1"}
        if capability == "person.get_value":
            return {"success": True, "value": "123456"}
        if capability == "api.call":
            return {"success": True, "result": {"status": "ok", "retcode": 0}}
        if capability == "send.text":
            return {"success": True}
        raise AssertionError(f"unexpected capability: {capability}")

    plugin._set_context(PluginContext(plugin_id="mute", rpc_call=fake_rpc_call))

    success, message, intercept = await plugin.handle_mute_command(
        stream_id="group-10001",
        group_id="10001",
        user_id="42",
        matched_groups={
            "target": "张三",
            "duration": "120",
            "reason": "刷屏",
        },
    )

    assert success is True
    assert message == "成功禁言 张三"
    assert intercept is True

    api_call = next(call for call in capability_calls if call["capability"] == "api.call")
    assert api_call["args"]["api_name"] == "adapter.napcat.group.set_group_ban"
    assert api_call["args"]["version"] == "1"
    assert api_call["args"]["args"] == {
        "group_id": "10001",
        "user_id": "123456",
        "duration": 120,
    }


@pytest.mark.asyncio
async def test_mute_tool_requires_target_person_name() -> None:
    """禁言工具在缺少目标时应直接失败并提示。"""

    plugin = _build_plugin()
    capability_calls: List[Dict[str, Any]] = []

    async def fake_rpc_call(method: str, plugin_id: str = "", payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        assert method == "cap.call"
        assert payload is not None
        capability_calls.append(payload)
        return {"success": True}

    plugin._set_context(PluginContext(plugin_id="mute", rpc_call=fake_rpc_call))

    success, message = await plugin.handle_mute_tool(
        stream_id="group-10001",
        group_id="10001",
        target="",
        duration="60",
        reason="测试",
    )

    assert success is False
    assert message == "禁言目标不能为空"
    assert capability_calls[-1]["capability"] == "send.text"
    assert capability_calls[-1]["args"]["text"] == "没有指定禁言对象哦"


def test_tool_invocation_payload_injects_group_and_user_context() -> None:
    """插件工具执行时应自动补齐群聊上下文字段。"""

    entry = SimpleNamespace(invoke_method="plugin.invoke_tool")
    anchor_message = SimpleNamespace(
        message_info=SimpleNamespace(
            group_info=SimpleNamespace(group_id="10001"),
            user_info=SimpleNamespace(user_id="20002"),
        )
    )
    invocation = ToolInvocation(tool_name="mute", arguments={"target": "张三"}, stream_id="session-1")
    context = ToolExecutionContext(
        session_id="session-1",
        stream_id="session-1",
        reasoning="test",
        metadata={"anchor_message": anchor_message},
    )

    payload = ComponentQueryService._build_tool_invocation_payload(entry, invocation, context)

    assert payload["target"] == "张三"
    assert payload["stream_id"] == "session-1"
    assert payload["chat_id"] == "session-1"
    assert payload["group_id"] == "10001"
    assert payload["user_id"] == "20002"
