"""`PluginPlatformDriver` 出站**回执归一化**的判据（"能听不能说"第六层：静默失败）。

## 这一层坏在哪（真机现场，2026-10-16 15:50-15:53）

前五层都修好之后，症状变成：宿主报
`[SendService] Platform IO 发送失败: … driver=plugin.…gateway.qq_gateway
 status=DeliveryStatus.FAILED error=消息网关发送失败`，
而**插件侧一条报错都没有**（插件 `_call_transport` 只在异常时打日志）。

根因是**两代 supervisor 的返回形状不一样**，而驱动只认了其中一代：
- legacy `PluginRuntimeSupervisor.invoke_message_gateway` → **`Envelope` 对象**（`.payload` / `.error`）；
- V2 `V2GatewaySupervisor.invoke_message_gateway` → **纯 dict**（`json.loads(response.result)`）。
⇒ 旧实现 `getattr(response, "payload", {})` 对 dict 拿到空字典 ⇒ **成功被读成失败**，
且文案是通用的 `消息网关发送失败`（明细被吃）——所以现场"插件不吭声、宿主说失败"。

## 判据

1. **正向（V2 dict 形状）**：`{"success": True, "result": {...}}` ⇒ **SENT**（这就是真机上被读错的那一支）。
2. **legacy Envelope 形状**仍要能工作（不许为了修新的把旧的弄坏）。
3. **失败要具名**：`{"success": False, "error": "…"}` ⇒ FAILED 且 `error` 里带**插件给的明细**。
4. **反向（静默改具名）**：形状对不上（缺 `success` 键 / 载荷不是映射 / 完全无法识别）
   ⇒ FAILED 且原因**写明形状与键**，**不许**再回落成通用文案。
"""

from typing import Any

import pytest

from src.platform_io.drivers.plugin_driver import PluginPlatformDriver
from src.platform_io.types import DeliveryStatus, RouteKey


class _StubSupervisor:
    """返回一个**预先造好**的响应（形状由用例给定）。"""

    def __init__(self, response: Any) -> None:
        self._response = response

    async def invoke_message_gateway(
        self,
        plugin_id: str,
        component_name: str,
        args: dict[str, Any] | None = None,
        timeout_ms: int = 30000,
    ) -> Any:
        return self._response


class _LegacyEnvelope:
    """legacy 形状：业务数据在 `.payload`，错误在 `.error`（对标 `plugin_runtime/protocol/envelope.py:65`）。"""

    def __init__(self, payload: dict[str, Any], error: dict[str, Any] | None = None) -> None:
        self.payload = payload
        self.error = error


def _driver(response: Any) -> PluginPlatformDriver:
    return PluginPlatformDriver(
        driver_id="plugin.p.gateway.qq_gateway",
        platform="qq",
        supervisor=_StubSupervisor(response),
        component_name="qq_gateway",
        supports_send=True,
        plugin_id="p",
        metadata={"tool_name": "napcat.send_text"},
    )


def _message() -> Any:
    from datetime import datetime

    from src.common.data_models.mai_message_data_model import MessageInfo, UserInfo
    from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
    from src.common.data_models.session_message_data_model import SessionMessage

    message = SessionMessage(
        message_id="msg-1", timestamp=datetime(2026, 10, 16, 15, 0, 0), platform="qq"
    )
    message.message_info = MessageInfo(user_info=UserInfo(user_id="10001", user_nickname="麦麦"))
    message.raw_message = MessageSequence([TextComponent("在呢")])
    message.session_id = "sess-1"
    return message


_ROUTE = RouteKey(platform="qq", account_id="12345", scope=None)


@pytest.mark.asyncio
async def test_v2_dict_success_is_reported_as_sent() -> None:
    """**真机回归**：V2 supervisor 的 dict 形状 + `success=True` ⇒ SENT（旧实现读成 FAILED）。"""
    driver = _driver({"success": True, "result": {"status": "ok", "data": {"message_id": 42}}})

    receipt = await driver.send_message(_message(), _ROUTE)

    assert receipt.status is DeliveryStatus.SENT, f"dict 形状的成功被读成失败：{receipt.error}"


@pytest.mark.asyncio
async def test_legacy_envelope_shape_still_works() -> None:
    """legacy `Envelope` 形状不许被弄坏（它是旧运行时仍在走的路径）。"""
    driver = _driver(_LegacyEnvelope({"success": True, "result": {"external_message_id": "ext-9"}}))

    receipt = await driver.send_message(_message(), _ROUTE)

    assert receipt.status is DeliveryStatus.SENT
    assert receipt.external_message_id == "ext-9"


@pytest.mark.asyncio
async def test_plugin_error_detail_is_named_not_swallowed() -> None:
    """失败要**具名**：插件给的 `error` 明细必须出现在回执里（旧实现只给通用文案）。"""
    driver = _driver({"success": False, "error": "TRANSPORT_NOT_INITIALIZED"})

    receipt = await driver.send_message(_message(), _ROUTE)

    assert receipt.status is DeliveryStatus.FAILED
    assert "TRANSPORT_NOT_INITIALIZED" in (receipt.error or ""), f"明细被吞：{receipt.error}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("shape", "expect_in_error"),
    [
        # 缺 success 标记（形状对不上）——**这是"静默改具名"的核心反向用例**
        ({"result": {"status": "ok"}}, "success"),
        ({"status": "ok", "retcode": 0}, "success"),
        # 载荷不是映射
        (["not-a-mapping"], "映射"),
        # 完全无法识别（既不是映射也没有 payload 属性）—— P3 后文案升级成 C/T/E/R：
        # 由"无法识别…"改为带 `层=响应形状` / `driver=` / `原始=`（判据强度只增不减，故改期望值）。
        ("just-a-string", "层=响应形状"),
    ],
)
async def test_unrecognised_shapes_fail_closed_and_named(
    shape: Any, expect_in_error: str
) -> None:
    """**反向判据**：形状对不上 ⇒ fail-closed 且**写明形状/键**，不许静默或回落成通用文案。"""
    driver = _driver(shape)

    receipt = await driver.send_message(_message(), _ROUTE)

    assert receipt.status is DeliveryStatus.FAILED, "未知形状被当成功了（availability 降级不得静默）"
    assert expect_in_error in (receipt.error or ""), f"原因没有具名：{receipt.error}"
    assert (receipt.error or "") != "消息网关发送失败", "回落到通用文案了（这次的静默就是它造成的）"


@pytest.mark.asyncio
async def test_legacy_envelope_error_channel_is_named() -> None:
    """legacy 的 `.error` 通道也要给出明细，而不是笼统的失败。"""
    driver = _driver(_LegacyEnvelope({}, {"message": "RUNNER_TIMEOUT"}))

    receipt = await driver.send_message(_message(), _ROUTE)

    assert receipt.status is DeliveryStatus.FAILED
    assert "RUNNER_TIMEOUT" in (receipt.error or "")
