"""P0-a 判据：工具参数 schema 必须**在生产路径**真的生效。

背景（硬发现①，见 `.shared/research/2026-10/msg_seam_dsh_1016.md` §1.3）：
`runner/tool_router.py:141` 的 jsonschema 校验挂在 `declaration is not None and
declaration.parameters_schema is not None` 上，而生产唯一的注册点
`runner/endpoint.py:139-144` **没有传 declaration** ⇒ 校验恒不执行。

本文件两条判据（改动前应当**都是红的**）：
1. `test_endpoint_registration_carries_declaration` —— 接线判据：端点注册工具时必须把
   loader 收集到的 `parameters_schema` 变成 `ToolDeclaration` 传进去；
2. `test_missing_required_arg_is_rejected_not_keyerror` —— 行为判据：缺必需键的调用在
   生产路径返回 `PARAMETER_VALIDATION_FAILED`，**不再**是 `EXECUTION_ERROR: KeyError`；
3. `test_complete_args_pass_validation` —— 方向性可赋值（判据门④）：写者把读者必需的键
   都给全时**必须通过**，证明这条闸不是"一律拒绝"。
"""

from typing import Any

import pytest

from src.plugin_runtime_v2.runner.endpoint import RunnerEndpoint
from src.plugin_runtime_v2.runner.reconnect import RunnerEndpointConfig
from src.plugin_runtime_v2.runner.tool_router import ToolRouter

SEND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "session_id": {"type": "string"},
        "text": {"type": "string"},
    },
    "required": ["session_id", "text"],
}


def _tool_entry(name: str, handler: Any) -> dict[str, Any]:
    """loader 收集出来的条目形状（`runner/plugin_loader.py:174-186`）。"""
    return {"name": name, "description": "测试工具", "handler": handler, "parameters_schema": SEND_SCHEMA}


def _send_handler(plugin: Any, args: dict[str, Any]) -> dict[str, Any]:
    """与适配器同姿态的处理器：**硬索引**必需键（缺了就是 KeyError）。

    签名是 `(plugin, args)`——框架按 `handler(plugin, args)` 调用（`runner/tool_router.py:154`），
    适配器里的 `async def tool_send_text(self, args)` 正是靠这一条把 self 接上。
    """
    del plugin
    return {"ok": True, "session_id": args["session_id"], "text": args["text"]}


def _config() -> RunnerEndpointConfig:
    return RunnerEndpointConfig(
        plugin_id="test-plugin",
        runner_id="test-runner",
        host_address="localhost:9999",
        scopes=[],
    )


class _OnLoadStops(Exception):
    """让 `start()` 在注册之后、连接之前收住（与 rollback 用例同一手法）。"""


class _RecordingLoader:
    """假 loader：返回带 schema 的工具条目；on_load 抛异常以便 `start()` 提前返回。"""

    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self._entries = entries

    async def load(self) -> tuple[Any, ...]:
        from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin

        class _Plugin(MaiBotPlugin):
            async def on_load(self) -> None:
                raise _OnLoadStops()

        plugin = _Plugin()
        return (self._entries, [], None, [], plugin)

    async def unload(self, plugin: Any) -> None:
        return None

    @property
    def is_loaded(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_endpoint_registration_carries_declaration(monkeypatch: pytest.MonkeyPatch) -> None:
    """接线判据：端点注册工具时**必须**把 parameters_schema 装进 ToolDeclaration。

    改动前：`declaration` 恒为 None（`endpoint.py` 不传）⇒ 本用例红。
    """
    captured: list[dict[str, Any]] = []
    original_register = ToolRouter.register

    def _spy(self: ToolRouter, **kwargs: Any) -> None:
        captured.append(kwargs)
        original_register(self, **kwargs)

    monkeypatch.setattr(ToolRouter, "register", _spy)
    endpoint = RunnerEndpoint(_config(), plugin_loader=_RecordingLoader([_tool_entry("napcat.send_text", _send_handler)]))

    await endpoint.start()

    assert len(captured) == 1, f"注册点被调用次数异常: {captured}"
    declaration = captured[0].get("declaration")
    assert declaration is not None, "端点没有把 declaration 传给 ToolRouter.register ⇒ schema 校验恒不执行"
    assert declaration.parameters_schema == SEND_SCHEMA
    assert declaration.parameters_schema["required"] == ["session_id", "text"]


@pytest.mark.asyncio
async def test_missing_required_arg_is_rejected_not_keyerror(monkeypatch: pytest.MonkeyPatch) -> None:
    """行为判据：缺 `session_id` ⇒ `PARAMETER_VALIDATION_FAILED`，不是 KeyError。

    改动前：校验被跳过 ⇒ handler 硬索引缺键 ⇒ `EXECUTION_ERROR: KeyError: 'session_id'` ⇒ 本用例红。
    """
    captured: list[dict[str, Any]] = []
    original_register = ToolRouter.register

    def _spy(self: ToolRouter, **kwargs: Any) -> None:
        captured.append(kwargs)
        original_register(self, **kwargs)

    monkeypatch.setattr(ToolRouter, "register", _spy)
    endpoint = RunnerEndpoint(_config(), plugin_loader=_RecordingLoader([_tool_entry("napcat.send_text", _send_handler)]))
    await endpoint.start()

    # 用**生产注册时实际传下去的参数**重建一张路由表，再走真实执行路径
    # （refcount 置空：本用例只验参数校验，插件活体引用在 on_load 失败后不可用，会抢先短路成 PLUGIN_GOING）
    register_kwargs = dict(captured[0])
    register_kwargs["refcount"] = None
    router = ToolRouter()
    router.register(**register_kwargs)

    response = await router.execute("napcat.send_text", {"text": "hi"})

    assert response.success is False
    assert response.error.startswith("PARAMETER_VALIDATION_FAILED"), (
        f"缺必需键没有被参数校验挡住，而是走到了 handler：{response.error!r}"
    )


@pytest.mark.asyncio
async def test_complete_args_pass_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """方向性可赋值（判据门④）：写者把读者必需的键给全 ⇒ 必须放行。

    只证明"能拒绝"不够——这条闸不能把合法调用一起挡掉。
    """
    captured: list[dict[str, Any]] = []
    original_register = ToolRouter.register

    def _spy(self: ToolRouter, **kwargs: Any) -> None:
        captured.append(kwargs)
        original_register(self, **kwargs)

    monkeypatch.setattr(ToolRouter, "register", _spy)
    endpoint = RunnerEndpoint(_config(), plugin_loader=_RecordingLoader([_tool_entry("napcat.send_text", _send_handler)]))
    await endpoint.start()

    register_kwargs = dict(captured[0])
    register_kwargs["refcount"] = None
    router = ToolRouter()
    router.register(**register_kwargs)

    response = await router.execute("napcat.send_text", {"session_id": "s1", "text": "hi"})

    assert response.success is True, f"键给全却仍被拒: {response.error!r}"
