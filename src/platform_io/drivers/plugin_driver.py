"""提供 Platform IO 的插件消息网关驱动实现。"""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Dict, Optional, Protocol
from src.common.logger import get_logger


from src.platform_io.drivers.base import PlatformIODriver
from src.platform_io.types import DeliveryReceipt, DeliveryStatus, DriverDescriptor, DriverKind, RouteKey
from src.plugin_runtime.host.component_timeout import resolve_component_rpc_timeout_ms
logger = get_logger("auto.plugin_driver")

if TYPE_CHECKING:
    from src.common.data_models.session_message_data_model import SessionMessage


class _GatewaySupervisorProtocol(Protocol):
    """消息网关驱动依赖的 Supervisor 最小协议。"""

    async def invoke_message_gateway(
        self,
        plugin_id: str,
        component_name: str,
        args: Optional[Dict[str, Any]] = None,
        timeout_ms: int = 30000,
    ) -> Any:
        """调用插件声明的消息网关方法。"""


def _extract_outbound_text(message: "SessionMessage") -> tuple[str, bool]:
    """取出站消息里的**文本分量**拼接，并报告是否存在非文本分量。

    为什么不让调用方直接用 ``processed_plain_text``：那是"给人看的摘要"——图片会被写成
    ``"[图片]"``（见 `services/send_service.py` 的 `_build_processed_plain_text`），
    当正文发出去就是把占位符当消息内容。网关声明的那个工具
    （``napcat.send_text``）参数表只有 ``session_id`` + ``text``，所以这里只认真正的文本分量。

    Returns:
        ``(文本, 是否有非文本分量)``。文本为空时调用方应当**拒发**（而不是发一条空消息）。
    """
    from src.common.data_models.message_component_data_model import TextComponent

    components = list(getattr(getattr(message, "raw_message", None), "components", []) or [])
    parts: list[str] = []
    has_non_text = False
    for component in components:
        if isinstance(component, TextComponent):
            parts.append(component.text)
        else:
            has_non_text = True
    return "".join(parts).strip(), has_non_text


class PluginPlatformDriver(PlatformIODriver):
    """面向插件消息网关链路的 Platform IO 驱动。"""

    def __init__(
        self,
        driver_id: str,
        platform: str,
        supervisor: _GatewaySupervisorProtocol,
        component_name: str,
        *,
        supports_send: bool,
        account_id: Optional[str] = None,
        scope: Optional[str] = None,
        plugin_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """初始化一个插件消息网关驱动。

        Args:
            driver_id: Broker 内的唯一驱动 ID。
            platform: 该消息网关负责的平台名称。
            supervisor: 持有该插件的 Supervisor。
            component_name: 出站时要调用的网关组件名称。
            supports_send: 当前驱动是否具备出站能力。
            account_id: 可选的账号 ID 或 self ID。
            scope: 可选的额外路由作用域。
            plugin_id: 拥有该实现的插件 ID。
            metadata: 可选的额外驱动元数据。
        """

        descriptor = DriverDescriptor(
            driver_id=driver_id,
            kind=DriverKind.PLUGIN,
            platform=platform,
            account_id=account_id,
            scope=scope,
            plugin_id=plugin_id,
            metadata=metadata or {},
        )
        super().__init__(descriptor)
        self._supervisor = supervisor
        self._component_name = component_name
        self._supports_send = supports_send
        self._timeout_ms = resolve_component_rpc_timeout_ms((metadata or {}).get("timeout_ms", 0))

    async def send_message(
        self,
        message: "SessionMessage",
        route_key: RouteKey,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DeliveryReceipt:
        """通过插件消息网关发送消息。

        Args:
            message: 要投递的内部会话消息。
            route_key: Broker 为本次投递选择的路由键。
            metadata: 可选的发送元数据。

        Returns:
            DeliveryReceipt: 规范化后的发送回执。
        """

        if not self._supports_send:
            return DeliveryReceipt(
                internal_message_id=message.message_id,
                route_key=route_key,
                status=DeliveryStatus.FAILED,
                driver_id=self.driver_id,
                driver_kind=self.descriptor.kind,
                error="当前消息网关仅支持接收，不支持发送",
            )

        from src.plugin_runtime.host.message_utils import PluginMessageUtils

        plugin_id = self.descriptor.plugin_id or ""
        if not plugin_id:
            return DeliveryReceipt(
                internal_message_id=message.message_id,
                route_key=route_key,
                status=DeliveryStatus.FAILED,
                driver_id=self.driver_id,
                driver_kind=self.descriptor.kind,
                error="插件消息网关驱动缺少 plugin_id",
            )

        # ⚠️ **载荷形状是对接契约的一部分**（"能听不能说"第三层：路由已通、形状不对）。
        # 插件侧证据 `plugins/maibot-team.napcat-adapter/plugin.py:313-318`：
        #     @Tool(name="napcat.send_text", ...)
        #     async def tool_send_text(self, args): session_id = args["session_id"]; text = args["text"]
        # 而 host 侧 `plugin_runtime_v2/host/gateway_supervisor.py:75-80` 把我们的 `args`
        # **原样** json.dumps 进 `InvokeToolRequest.args` ⇒ 少一个键就是插件侧 KeyError。
        # 真机现场：`RuntimeError: 网关 Tool 调用失败: … tool=napcat.send_text error=EXECUTION_ERROR: KeyError: 'session_id'`
        # 网关声明把发送**钉在一个工具**上（`decl.metadata["tool_name"]`，见 `gateway_registrar.py:100`），
        # 那个工具的参数表是 `session_id` + `text` ⇒ 这两个键必须由我们平铺提供。
        #
        # session_id **不许自行计算**（`AGENTS §五`）：正常路径上它由上游用**真实聊天流**填好
        # （`services/send_service.py:525` `outbound_message.session_id = session_info.session_id`）；
        # 这里取不到就是"上游没解析到真实聊天流" ⇒ **出声**并让这次发送失败得可诊断，
        # 不编一个顶上（编出来的 ID 插件反查不到 QQ 号，发出去也是错的）。
        session_id = str(getattr(message, "session_id", "") or "").strip()
        if not session_id:
            reason = (
                "消息未携带 session_id（上游未解析到真实聊天流）——拒绝投递给插件网关："
                "插件的发送 Tool 要用它反查平台账号/群号，编一个只会发错人或发不出去"
            )
            return self._refuse(reason, message=message, route_key=route_key)

        text, has_non_text = _extract_outbound_text(message)
        if not text:
            # 有分量但不是文本（纯图片/表情/转发…）⇒ 网关照旧发不出去：声明的工具是**纯文本**参数表。
            # 这里明确拒绝并写清原因，胜过把占位符（"[图片]"）当正文发出去。
            return self._refuse(
                "消息没有可发送的文本分量（网关声明的工具 napcat.send_text 是纯文本参数表；"
                "图片/表情/转发/混合分量的出站今天表达不了）",
                message=message,
                route_key=route_key,
            )
        if has_non_text:
            # 部分保真要说出来：文本照发，但非文本分量会被丢掉（同一条消息里的图片/@ 等）。
            logger.warning(
                "网关发送只承载文本分量，消息中的非文本分量被丢弃: driver=%s message_id=%s",
                self.driver_id, message.message_id,
            )

        try:
            message_dict = PluginMessageUtils._session_message_to_dict(message)
            response = await self._supervisor.invoke_message_gateway(
                plugin_id=plugin_id,
                component_name=self._component_name,
                args={
                    # 插件 Tool 的参数表（平铺）：session_id + text
                    "session_id": session_id,
                    "text": text,
                    # 完整消息与路由照旧带上：别的网关插件按 `message`/`route` 取值，
                    # 多给的键对"只读 session_id/text"的工具无害。
                    "message": message_dict,
                    "route": {
                        "platform": route_key.platform,
                        "account_id": route_key.account_id,
                        "scope": route_key.scope,
                    },
                    "metadata": metadata or {},
                },
                timeout_ms=self._timeout_ms,
            )
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "消息发送失败", exception=exc)
            logger.warning("操作异常 in plugin_driver", exc_info=True)
            return DeliveryReceipt(
                internal_message_id=message.message_id,
                route_key=route_key,
                status=DeliveryStatus.FAILED,
                driver_id=self.driver_id,
                driver_kind=self.descriptor.kind,
                error=str(exc),
            )

        return self._build_receipt(message.message_id, route_key, response)

    def _build_receipt(self, internal_message_id: str, route_key: RouteKey, response: Any) -> DeliveryReceipt:
        """将网关调用响应归一化为出站回执。

        ⚠️ **两代 supervisor 的返回形状不一样**（2026-10-16 真机"静默失败"的根因）：
        - legacy `PluginRuntimeSupervisor.invoke_message_gateway` 返回 **`Envelope` 对象**
          （`plugin_runtime/host/supervisor.py:524-549`）⇒ 业务数据在 `.payload`、错误在 `.error`；
        - V2 `V2GatewaySupervisor.invoke_message_gateway` 返回**纯 dict**
          （`plugin_runtime_v2/host/gateway_supervisor.py:98-101`：`json.loads(response.result)`，
          形状就是插件 Tool 自己的返回，如 napcat 适配器 `plugins/…/plugin.py:369-382`）。
        旧实现只认前者的属性 ⇒ 喂进 dict 时 `getattr(response, "payload", {})` 拿到**空字典**
        ⇒ **一律判失败**，文案还是通用的 `消息网关发送失败`：真机上就长成"插件侧零日志、
        宿主说发送失败"（**成功被读成失败 + 出错明细被吃**）。
        两代**载荷内部约定是一样的**（`{success, result, error}`）⇒ 这里只做"拆信封"这一步。

        判据口径（2026-10-16 裁定：**availability 可降级但必须具名**）：
        拆不开的信封 / 缺 `success` 标记 / 载荷不是映射，一律 **fail-closed 且具名**
        （写明形状与键），**不**回落到通用文案——否则下一次还是查不出来。

        Args:
            internal_message_id: 内部消息 ID。
            route_key: 本次投递的路由键。
            response: Supervisor 返回值（legacy 是 Envelope 对象，V2 是 dict）。

        Returns:
            DeliveryReceipt: 标准化后的出站回执。
        """

        # ① 拆信封
        if isinstance(response, Mapping):
            payload: Any = response
        else:
            envelope_error = getattr(response, "error", None)
            if envelope_error:
                detail = (
                    envelope_error.get("message") if isinstance(envelope_error, Mapping) else envelope_error
                )
                return self._failed_receipt(
                    internal_message_id,
                    route_key,
                    f"网关响应携带错误（legacy Envelope）: {detail or '（无 message）'}",
                )
            payload = getattr(response, "payload", None)
            if payload is None:
                return self._failed_receipt(
                    internal_message_id,
                    route_key,
                    f"无法识别的网关响应形状: {type(response).__name__}"
                    "（既不是映射，也没有 payload 属性）",
                )

        if not isinstance(payload, Mapping):
            return self._failed_receipt(
                internal_message_id, route_key, f"网关响应载荷不是映射: {type(payload).__name__}"
            )

        # ② 按两代共同的载荷约定解释：缺 success 标记 ⇒ 形状对不上，**明说**而不是当失败
        if "success" not in payload:
            return self._failed_receipt(
                internal_message_id,
                route_key,
                "网关响应缺少 success 标记，形状对不上，拒绝按成功处理"
                f"（键={sorted(str(key) for key in payload.keys())}）",
            )
        if not payload.get("success"):
            detail = payload.get("error")
            return self._failed_receipt(
                internal_message_id,
                route_key,
                f"插件网关返回失败: {detail if detail else '（插件未给出 error 明细）'}",
            )

        result = payload.get("result") if isinstance(payload, dict) else None
        if isinstance(result, dict):
            if result.get("success") is False:
                return DeliveryReceipt(
                    internal_message_id=internal_message_id,
                    route_key=route_key,
                    status=DeliveryStatus.FAILED,
                    driver_id=self.driver_id,
                    driver_kind=self.descriptor.kind,
                    error=str(result.get("error", "消息网关发送失败")),
                    metadata=result.get("metadata", {}) if isinstance(result.get("metadata"), dict) else {},
                )
            external_message_id = str(result.get("external_message_id") or result.get("message_id") or "") or None
            return DeliveryReceipt(
                internal_message_id=internal_message_id,
                route_key=route_key,
                status=DeliveryStatus.SENT,
                driver_id=self.driver_id,
                driver_kind=self.descriptor.kind,
                external_message_id=external_message_id,
                metadata=result.get("metadata", {}) if isinstance(result.get("metadata"), dict) else {},
            )

        if isinstance(result, str) and result.strip():
            return DeliveryReceipt(
                internal_message_id=internal_message_id,
                route_key=route_key,
                status=DeliveryStatus.SENT,
                driver_id=self.driver_id,
                driver_kind=self.descriptor.kind,
                external_message_id=result.strip(),
            )

        return DeliveryReceipt(
            internal_message_id=internal_message_id,
            route_key=route_key,
            status=DeliveryStatus.SENT,
            driver_id=self.driver_id,
            driver_kind=self.descriptor.kind,
        )

    def _failed_receipt(
        self, internal_message_id: str, route_key: RouteKey, error: str
    ) -> DeliveryReceipt:
        """构造失败回执（出站回执形状的唯一出处，避免各处手拼字段）。"""
        return DeliveryReceipt(
            internal_message_id=internal_message_id,
            route_key=route_key,
            status=DeliveryStatus.FAILED,
            driver_id=self.driver_id,
            driver_kind=self.descriptor.kind,
            error=error,
        )

    def _refuse(
        self, reason: str, *, message: "SessionMessage", route_key: RouteKey
    ) -> DeliveryReceipt:
        """拒发并**双通道出声**（日志 + 错误上报口），返回失败回执（`AGENTS §七` #7）。

        为什么不是"返回一个静默的失败回执"：这类拒绝全是"接缝形状/寻址对不上"，
        现场只留一条 `[SendService] Platform IO 发送失败: … error=<reason>` 不够——
        原因要同时进日志与上报口，否则排障只能靠猜。
        """
        logger.error("Platform IO 插件驱动拒绝发送: driver=%s reason=%s", self.driver_id, reason)

        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port

        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, f"插件网关拒发: driver={self.driver_id} reason={reason}")

        return DeliveryReceipt(
            internal_message_id=message.message_id,
            route_key=route_key,
            status=DeliveryStatus.FAILED,
            driver_id=self.driver_id,
            driver_kind=self.descriptor.kind,
            error=reason,
        )
