"""NapCat 插件与新 SDK 对接测试。"""

from importlib import import_module, util
from pathlib import Path
from typing import Any, Dict, List, Tuple

import logging
import sys
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGINS_ROOT = PROJECT_ROOT / "plugins"
SDK_ROOT = PROJECT_ROOT / "packages" / "maibot-plugin-sdk"
NAPCAT_PLUGIN_DIR = PLUGINS_ROOT / "MaiBot-Napcat-Adapter"
NAPCAT_TEST_MODULE = "_test_napcat_adapter"

for import_path in (str(SDK_ROOT),):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)


class _FakeGatewayCapability:
    """用于捕获消息网关状态上报的测试替身。"""

    def __init__(self) -> None:
        """初始化测试替身。"""

        self.calls: List[Dict[str, Any]] = []

    async def update_state(
        self,
        gateway_name: str,
        *,
        ready: bool,
        platform: str = "",
        account_id: str = "",
        scope: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> bool:
        """记录一次状态上报请求。

        Args:
            gateway_name: 网关组件名称。
            ready: 当前是否就绪。
            platform: 平台名称。
            account_id: 账号 ID。
            scope: 路由作用域。
            metadata: 附加元数据。

        Returns:
            bool: 始终返回 ``True``，模拟 Host 接受状态更新。
        """

        self.calls.append(
            {
                "gateway_name": gateway_name,
                "ready": ready,
                "platform": platform,
                "account_id": account_id,
                "scope": scope,
                "metadata": metadata or {},
            }
        )
        return True


class _FakeNapCatQueryService:
    """用于驱动 NapCat 入站编解码测试的查询服务替身。"""

    def __init__(
        self,
        forward_payloads: Dict[str, Any] | None = None,
        group_member_payloads: Dict[tuple[str, str], Dict[str, Any] | None] | None = None,
        stranger_payloads: Dict[str, Dict[str, Any] | None] | None = None,
    ) -> None:
        """初始化查询服务替身。

        Args:
            forward_payloads: 预置的合并转发响应映射。
            group_member_payloads: 预置的群成员资料映射。
            stranger_payloads: 预置的陌生人资料映射。
        """
        self._forward_payloads = forward_payloads or {}
        self._group_member_payloads = group_member_payloads or {}
        self._stranger_payloads = stranger_payloads or {}

    async def download_binary(self, url: str) -> bytes | None:
        """模拟下载远程二进制资源。

        Args:
            url: 资源地址。

        Returns:
            bytes | None: 测试中默认不返回二进制内容。
        """
        del url
        return None

    async def get_message_detail(self, message_id: str) -> Dict[str, Any] | None:
        """模拟获取消息详情。

        Args:
            message_id: 消息 ID。

        Returns:
            Dict[str, Any] | None: 测试中默认不返回详情。
        """
        del message_id
        return None

    async def get_forward_message(
        self,
        message_id: str | None = None,
        forward_id: str | None = None,
    ) -> Any:
        """模拟获取合并转发消息详情。

        Args:
            message_id: 转发消息 ID。
            forward_id: 兼容字段 ``id``。

        Returns:
            Any: 预置的合并转发消息详情。
        """
        return self._forward_payloads.get(forward_id or message_id or "")

    async def get_group_member_info(
        self,
        group_id: str,
        user_id: str,
        no_cache: bool = True,
    ) -> Dict[str, Any] | None:
        """模拟获取群成员资料。"""
        del no_cache
        return self._group_member_payloads.get((group_id, user_id))

    async def get_stranger_info(self, user_id: str, no_cache: bool = False) -> Dict[str, Any] | None:
        """模拟获取 QQ 昵称资料。"""
        del no_cache
        return self._stranger_payloads.get(user_id)

    async def get_record_detail(
        self,
        file_name: str | None = None,
        file_id: str | None = None,
        out_format: str = "wav",
    ) -> Dict[str, Any] | None:
        """模拟获取语音详情。

        Args:
            file_name: 文件名。
            file_id: 文件 ID。
            out_format: 输出格式。

        Returns:
            Dict[str, Any] | None: 测试中默认不返回语音详情。
        """
        del file_name
        del file_id
        del out_format
        return None


class _FakeNapCatActionService:
    """用于驱动 NapCat 查询服务测试的动作服务替身。"""

    def __init__(self, response_data: Any) -> None:
        """初始化动作服务替身。

        Args:
            response_data: 预置的 ``safe_call_action_data`` 返回值。
        """
        self._response_data = response_data
        self.action_calls: List[Dict[str, Any]] = []
        self.action_data_calls: List[Dict[str, Any]] = []

    async def safe_call_action_data(self, action_name: str, params: Dict[str, Any]) -> Any:
        """模拟安全调用 OneBot 动作。

        Args:
            action_name: 动作名称。
            params: 动作参数。

        Returns:
            Any: 预置返回值。
        """
        self.action_data_calls.append({"action_name": action_name, "params": dict(params)})
        return self._response_data

    async def call_action(self, action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """模拟调用 OneBot 动作并记录参数。"""

        self.action_calls.append({"action_name": action_name, "params": dict(params)})
        return {"status": "ok", "retcode": 0, "data": {}}


def _load_napcat_sdk_modules() -> Tuple[Any, Any, Any, Any]:
    """动态加载 NapCat 插件测试所需的模块。

    Returns:
        tuple[Any, Any, Any, Any]:
            依次返回常量模块、配置模块、插件模块和运行时状态模块。
    """

    if NAPCAT_TEST_MODULE not in sys.modules:
        plugin_path = NAPCAT_PLUGIN_DIR / "plugin.py"
        spec = util.spec_from_file_location(
            NAPCAT_TEST_MODULE,
            plugin_path,
            submodule_search_locations=[str(NAPCAT_PLUGIN_DIR)],
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"无法为 NapCat 插件创建模块规格: {plugin_path}")

        module = util.module_from_spec(spec)
        sys.modules[NAPCAT_TEST_MODULE] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(NAPCAT_TEST_MODULE, None)
            raise

    return (
        import_module(f"{NAPCAT_TEST_MODULE}.constants"),
        import_module(f"{NAPCAT_TEST_MODULE}.config"),
        import_module(f"{NAPCAT_TEST_MODULE}.plugin"),
        import_module(f"{NAPCAT_TEST_MODULE}.runtime_state"),
    )


def _load_napcat_sdk_symbols() -> Tuple[Any, Any, Any, Any]:
    """动态加载 NapCat 插件测试所需的符号。

    Returns:
        tuple[Any, Any, Any, Any]:
            依次返回网关名常量、配置类、插件类和运行时状态管理器类。
    """

    constants_module, config_module, plugin_module, runtime_state_module = _load_napcat_sdk_modules()
    return (
        constants_module.NAPCAT_GATEWAY_NAME,
        config_module.NapCatServerConfig,
        plugin_module.NapCatAdapterPlugin,
        runtime_state_module.NapCatRuntimeStateManager,
    )


def _load_napcat_inbound_codec_cls() -> Any:
    """动态加载 NapCat 入站编解码器类。

    Returns:
        Any: ``NapCatInboundCodec`` 类对象。
    """
    _load_napcat_sdk_modules()
    codec_module = import_module(f"{NAPCAT_TEST_MODULE}.codecs.inbound.message_codec")
    return codec_module.NapCatInboundCodec


def _load_napcat_query_service_cls() -> Any:
    """动态加载 NapCat 查询服务类。

    Returns:
        Any: ``NapCatQueryService`` 类对象。
    """
    _load_napcat_sdk_modules()
    query_service_module = import_module(f"{NAPCAT_TEST_MODULE}.services.query_service")
    return query_service_module.NapCatQueryService


def test_napcat_plugin_collects_duplex_message_gateway() -> None:
    """NapCat 插件应声明新的双工消息网关组件。"""

    napcat_gateway_name, _napcat_server_config, napcat_plugin_cls, _runtime_state_cls = _load_napcat_sdk_symbols()
    plugin = napcat_plugin_cls()
    components = plugin.get_components()
    gateway_components = [
        component
        for component in components
        if component.get("type") == "MESSAGE_GATEWAY"
    ]

    assert len(gateway_components) == 1
    gateway_component = gateway_components[0]
    assert gateway_component["name"] == napcat_gateway_name
    assert gateway_component["metadata"]["route_type"] == "duplex"
    assert gateway_component["metadata"]["platform"] == "qq"
    assert gateway_component["metadata"]["protocol"] == "napcat"


def test_napcat_plugin_uses_sdk_config_model() -> None:
    """NapCat 插件应声明 SDK 配置模型并暴露默认配置与 Schema。"""

    constants_module, _config_module, plugin_module, _runtime_state_module = _load_napcat_sdk_modules()
    plugin = plugin_module.NapCatAdapterPlugin()

    default_config = plugin.get_default_config()
    schema = plugin.get_webui_config_schema(plugin_id="maibot-team.napcat-adapter")

    assert default_config["plugin"]["config_version"] == constants_module.SUPPORTED_CONFIG_VERSION
    assert default_config["chat"]["ban_qq_bot"] is False
    assert default_config["filters"]["ignore_self_message"] is True
    assert schema["plugin_id"] == "maibot-team.napcat-adapter"
    assert schema["sections"]["chat"]["fields"]["group_list"]["type"] == "array"
    assert schema["sections"]["chat"]["fields"]["group_list_type"]["choices"] == ["whitelist", "blacklist"]


def test_napcat_plugin_normalizes_legacy_config_values() -> None:
    """NapCat 插件应兼容旧配置字段并输出规范化结果。"""

    constants_module, _config_module, plugin_module, _runtime_state_module = _load_napcat_sdk_modules()
    plugin = plugin_module.NapCatAdapterPlugin()

    plugin.set_plugin_config(
        {
            "plugin": {"enabled": True, "config_version": constants_module.SUPPORTED_CONFIG_VERSION},
            "connection": {
                "access_token": "secret-token",
                "heartbeat_sec": "45",
                "ws_url": "ws://10.0.0.8:3012/onebot/v11/ws",
            },
            "chat": {
                "ban_qq_bot": True,
                "ban_user_id": ["42", 42, ""],
                "group_list": [123, " 456 ", None, "123"],
                "group_list_type": "whitelist",
                "private_list": "invalid",
                "private_list_type": "unexpected",
            },
            "filters": {"ignore_self_message": True},
        }
    )

    config_data = plugin.get_plugin_config_data()

    assert "connection" not in config_data
    assert config_data["plugin"]["config_version"] == constants_module.SUPPORTED_CONFIG_VERSION
    assert config_data["napcat_server"]["host"] == "10.0.0.8"
    assert config_data["napcat_server"]["port"] == 3012
    assert config_data["napcat_server"]["token"] == "secret-token"
    assert config_data["napcat_server"]["heartbeat_interval"] == 45.0
    assert config_data["chat"]["group_list"] == ["123", "456"]
    assert config_data["chat"]["private_list"] == []
    assert config_data["chat"]["private_list_type"] == constants_module.DEFAULT_CHAT_LIST_TYPE
    assert plugin.config.napcat_server.build_ws_url() == "ws://10.0.0.8:3012"


@pytest.mark.asyncio
async def test_runtime_state_reports_via_gateway_capability() -> None:
    """NapCat 运行时状态应通过新的消息网关能力上报。"""

    napcat_gateway_name, napcat_server_config_cls, _napcat_plugin_cls, runtime_state_cls = _load_napcat_sdk_symbols()
    gateway_capability = _FakeGatewayCapability()
    runtime_state_manager = runtime_state_cls(
        gateway_capability=gateway_capability,
        logger=logging.getLogger("test.napcat_adapter"),
        gateway_name=napcat_gateway_name,
    )

    connected = await runtime_state_manager.report_connected(
        "10001",
        napcat_server_config_cls(connection_id="primary"),
    )
    await runtime_state_manager.report_disconnected()

    assert connected is True
    assert gateway_capability.calls[0]["gateway_name"] == napcat_gateway_name
    assert gateway_capability.calls[0]["ready"] is True
    assert gateway_capability.calls[0]["platform"] == "qq"
    assert gateway_capability.calls[0]["account_id"] == "10001"
    assert gateway_capability.calls[0]["scope"] == "primary"
    assert gateway_capability.calls[1]["gateway_name"] == napcat_gateway_name
    assert gateway_capability.calls[1]["ready"] is False
    assert gateway_capability.calls[1]["platform"] == "qq"


@pytest.mark.asyncio
async def test_napcat_plugin_send_result_contains_message_id_echo_callback() -> None:
    """NapCat 插件发送成功后应显式返回消息 ID 回调数据。"""

    _napcat_gateway_name, _napcat_server_config, napcat_plugin_cls, _runtime_state_cls = _load_napcat_sdk_symbols()
    plugin = napcat_plugin_cls()

    class _FakeOutboundCodec:
        """用于测试的出站编码器替身。"""

        @staticmethod
        def build_outbound_action(message: Dict[str, Any], route: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
            """返回固定动作与参数。"""

            del message
            del route
            return "send_msg", {"message": "hello"}

    class _FakeTransport:
        """用于测试的传输层替身。"""

        @staticmethod
        async def call_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
            """返回带平台消息 ID 的成功响应。"""

            del action_name
            del params
            return {
                "status": "ok",
                "data": {
                    "message_id": "platform-message-id",
                },
            }

    plugin._require_runtime_bundle = lambda: SimpleNamespace(  # type: ignore[method-assign]
        outbound_codec=_FakeOutboundCodec(),
        transport=_FakeTransport(),
    )

    result = await plugin.handle_napcat_gateway(
        message={"message_id": "internal-message-id"},
        route={},
    )

    assert result["success"] is True
    assert result["external_message_id"] == "platform-message-id"
    assert result["metadata"]["adapter_callbacks"] == [
        {
            "name": "message_id_echo",
            "payload": {
                "content": {
                    "type": "echo",
                    "echo": "internal-message-id",
                    "actual_id": "platform-message-id",
                }
            },
        }
    ]


@pytest.mark.asyncio
async def test_inbound_codec_parses_forward_nodes_from_legacy_message_field() -> None:
    """入站编解码器应兼容旧版 ``sender + message`` 转发节点结构。"""

    inbound_codec_cls = _load_napcat_inbound_codec_cls()
    codec = inbound_codec_cls(
        logger=logging.getLogger("test.napcat_adapter.forward_legacy"),
        query_service=_FakeNapCatQueryService(
            forward_payloads={
                "forward-1": {
                    "messages": [
                        {
                            "sender": {"user_id": "10001", "nickname": "张三", "card": "群名片"},
                            "message_id": "node-1",
                            "message": [{"type": "text", "data": {"text": "第一条转发"}}],
                        }
                    ]
                }
            }
        ),
    )

    segments, is_at = await codec.convert_segments(
        {"message": [{"type": "forward", "data": {"id": "forward-1"}}]},
        "",
    )

    assert is_at is False
    assert len(segments) == 1
    assert segments[0]["type"] == "forward"
    assert segments[0]["data"][0]["user_id"] == "10001"
    assert segments[0]["data"][0]["user_nickname"] == "张三"
    assert segments[0]["data"][0]["user_cardname"] == "群名片"
    assert segments[0]["data"][0]["content"] == [{"type": "text", "data": "第一条转发"}]


@pytest.mark.asyncio
async def test_inbound_codec_parses_nested_inline_forward_content() -> None:
    """入站编解码器应支持内联 ``content`` 形式的嵌套合并转发。"""

    inbound_codec_cls = _load_napcat_inbound_codec_cls()
    codec = inbound_codec_cls(
        logger=logging.getLogger("test.napcat_adapter.forward_nested"),
        query_service=_FakeNapCatQueryService(
            forward_payloads={
                "forward-outer": {
                    "messages": [
                        {
                            "sender": {"user_id": "10001", "nickname": "张三"},
                            "message_id": "node-outer",
                            "message": [
                                {
                                    "type": "forward",
                                    "data": {
                                        "content": [
                                            {
                                                "sender": {"user_id": "10002", "nickname": "李四"},
                                                "message_id": "node-inner",
                                                "message": [{"type": "text", "data": {"text": "内层消息"}}],
                                            }
                                        ]
                                    },
                                }
                            ],
                        }
                    ]
                }
            }
        ),
    )

    segments, _ = await codec.convert_segments(
        {"message": [{"type": "forward", "data": {"id": "forward-outer"}}]},
        "",
    )

    assert len(segments) == 1
    assert segments[0]["type"] == "forward"
    outer_content = segments[0]["data"][0]["content"]
    assert len(outer_content) == 1
    assert outer_content[0]["type"] == "forward"
    nested_nodes = outer_content[0]["data"]
    assert nested_nodes[0]["user_id"] == "10002"
    assert nested_nodes[0]["user_nickname"] == "李四"
    assert nested_nodes[0]["content"] == [{"type": "text", "data": "内层消息"}]


@pytest.mark.asyncio
async def test_inbound_codec_resolves_at_to_group_cardname() -> None:
    """入站编解码器应优先将 ``at`` 解析为群昵称。"""

    inbound_codec_cls = _load_napcat_inbound_codec_cls()
    codec = inbound_codec_cls(
        logger=logging.getLogger("test.napcat_adapter.at_cardname"),
        query_service=_FakeNapCatQueryService(
            group_member_payloads={
                ("12345", "1206069534"): {
                    "nickname": "QQ昵称",
                    "card": "群昵称",
                }
            }
        ),
    )

    message_dict = await codec.build_message_dict(
        payload={
            "message_type": "group",
            "group_id": "12345",
            "message_id": "msg-1",
            "message": [{"type": "at", "data": {"qq": "1206069534"}}],
            "sender": {"user_id": "10001", "nickname": "发送者"},
            "time": 1710000000,
        },
        self_id="20001",
        sender_user_id="10001",
        sender={"user_id": "10001", "nickname": "发送者"},
    )

    assert message_dict["processed_plain_text"] == "@群昵称"
    assert message_dict["raw_message"] == [
        {
            "type": "at",
            "data": {
                "target_user_id": "1206069534",
                "target_user_nickname": "QQ昵称",
                "target_user_cardname": "群昵称",
            },
        }
    ]


@pytest.mark.asyncio
async def test_inbound_codec_falls_back_to_qq_nickname_when_group_cardname_is_empty() -> None:
    """入站编解码器在群昵称为空时应回退到 QQ 昵称。"""

    inbound_codec_cls = _load_napcat_inbound_codec_cls()
    codec = inbound_codec_cls(
        logger=logging.getLogger("test.napcat_adapter.at_nickname"),
        query_service=_FakeNapCatQueryService(
            group_member_payloads={
                ("12345", "1206069534"): {
                    "nickname": "QQ昵称",
                    "card": "",
                }
            }
        ),
    )

    message_dict = await codec.build_message_dict(
        payload={
            "message_type": "group",
            "group_id": "12345",
            "message_id": "msg-2",
            "message": [{"type": "at", "data": {"qq": "1206069534"}}],
            "sender": {"user_id": "10001", "nickname": "发送者"},
            "time": 1710000000,
        },
        self_id="20001",
        sender_user_id="10001",
        sender={"user_id": "10001", "nickname": "发送者"},
    )

    assert message_dict["processed_plain_text"] == "@QQ昵称"
    assert message_dict["raw_message"] == [
        {
            "type": "at",
            "data": {
                "target_user_id": "1206069534",
                "target_user_nickname": "QQ昵称",
                "target_user_cardname": None,
            },
        }
    ]


@pytest.mark.asyncio
async def test_inbound_codec_falls_back_to_stranger_nickname_when_group_profile_is_missing() -> None:
    """入站编解码器在群资料缺失时应继续回退到 QQ 昵称。"""

    inbound_codec_cls = _load_napcat_inbound_codec_cls()
    codec = inbound_codec_cls(
        logger=logging.getLogger("test.napcat_adapter.at_stranger_nickname"),
        query_service=_FakeNapCatQueryService(
            group_member_payloads={("12345", "1206069534"): None},
            stranger_payloads={"1206069534": {"nickname": "QQ昵称"}},
        ),
    )

    message_dict = await codec.build_message_dict(
        payload={
            "message_type": "group",
            "group_id": "12345",
            "message_id": "msg-3",
            "message": [{"type": "at", "data": {"qq": "1206069534"}}],
            "sender": {"user_id": "10001", "nickname": "发送者"},
            "time": 1710000000,
        },
        self_id="20001",
        sender_user_id="10001",
        sender={"user_id": "10001", "nickname": "发送者"},
    )

    assert message_dict["processed_plain_text"] == "@QQ昵称"
    assert message_dict["raw_message"] == [
        {
            "type": "at",
            "data": {
                "target_user_id": "1206069534",
                "target_user_nickname": "QQ昵称",
                "target_user_cardname": None,
            },
        }
    ]


@pytest.mark.asyncio
async def test_query_service_normalizes_forward_payload_list() -> None:
    """查询服务应兼容 ``get_forward_msg`` 直接返回节点列表。"""

    query_service_cls = _load_napcat_query_service_cls()
    query_service = query_service_cls(
        action_service=_FakeNapCatActionService(
            [
                {
                    "sender": {"user_id": "10001", "nickname": "张三"},
                    "message_id": "node-1",
                    "message": [{"type": "text", "data": {"text": "列表返回"}}],
                }
            ]
        ),
        logger=logging.getLogger("test.napcat_adapter.query_service"),
    )

    forward_payload = await query_service.get_forward_message("forward-1")

    assert forward_payload == {
        "messages": [
            {
                "sender": {"user_id": "10001", "nickname": "张三"},
                "message_id": "node-1",
                "message": [{"type": "text", "data": {"text": "列表返回"}}],
            }
        ]
    }


@pytest.mark.asyncio
async def test_query_service_supports_official_no_cache_for_get_stranger_info() -> None:
    """查询服务应按官方字段下发 ``no_cache``。"""

    action_service = _FakeNapCatActionService({"nickname": "测试用户"})
    query_service_cls = _load_napcat_query_service_cls()
    query_service = query_service_cls(
        action_service=action_service,
        logger=logging.getLogger("test.napcat_adapter.query_service.stranger"),
    )

    payload = await query_service.get_stranger_info("10001", no_cache=True)

    assert payload == {"nickname": "测试用户"}
    assert action_service.action_data_calls[-1] == {
        "action_name": "get_stranger_info",
        "params": {"user_id": "10001", "no_cache": True},
    }


@pytest.mark.asyncio
async def test_query_service_supports_official_forward_id_alias() -> None:
    """查询服务应兼容官方 ``id`` 字段调用 ``get_forward_msg``。"""

    action_service = _FakeNapCatActionService({"messages": []})
    query_service_cls = _load_napcat_query_service_cls()
    query_service = query_service_cls(
        action_service=action_service,
        logger=logging.getLogger("test.napcat_adapter.query_service.forward_alias"),
    )

    payload = await query_service.get_forward_message(forward_id="forward-alias")

    assert payload == {"messages": []}
    assert action_service.action_data_calls[-1] == {
        "action_name": "get_forward_msg",
        "params": {"id": "forward-alias"},
    }


@pytest.mark.asyncio
async def test_query_service_supports_custom_out_format_for_get_record() -> None:
    """查询服务应按官方字段下发自定义 ``out_format``。"""

    action_service = _FakeNapCatActionService({"file": "voice.mp3"})
    query_service_cls = _load_napcat_query_service_cls()
    query_service = query_service_cls(
        action_service=action_service,
        logger=logging.getLogger("test.napcat_adapter.query_service.record"),
    )

    payload = await query_service.get_record_detail(file_id="record-1", out_format="mp3")

    assert payload == {"file": "voice.mp3"}
    assert action_service.action_data_calls[-1] == {
        "action_name": "get_record",
        "params": {"file_id": "record-1", "out_format": "mp3"},
    }


@pytest.mark.asyncio
async def test_query_service_supports_target_id_for_send_poke() -> None:
    """查询服务应按官方字段下发 ``target_id``。"""

    action_service = _FakeNapCatActionService(None)
    query_service_cls = _load_napcat_query_service_cls()
    query_service = query_service_cls(
        action_service=action_service,
        logger=logging.getLogger("test.napcat_adapter.query_service.poke"),
    )

    response = await query_service.send_poke(user_id=10001, group_id=20002, target_id=30003)

    assert response["status"] == "ok"
    assert action_service.action_calls[-1] == {
        "action_name": "send_poke",
        "params": {"user_id": 10001, "group_id": 20002, "target_id": 30003},
    }


@pytest.mark.asyncio
async def test_public_api_send_poke_supports_official_fields_and_legacy_alias() -> None:
    """公开 API 应同时兼容官方字段和旧版 ``qq_id`` 别名。"""

    _napcat_gateway_name, _napcat_server_config, napcat_plugin_cls, _runtime_state_cls = _load_napcat_sdk_symbols()
    plugin = napcat_plugin_cls()
    captured: List[Dict[str, Any]] = []

    class _SpyQueryService:
        async def send_poke(
            self,
            user_id: int,
            group_id: int | None = None,
            target_id: int | None = None,
        ) -> Dict[str, Any]:
            captured.append(
                {
                    "user_id": user_id,
                    "group_id": group_id,
                    "target_id": target_id,
                }
            )
            return {"status": "ok", "data": {}}

    plugin._query_service = _SpyQueryService()
    plugin._ensure_runtime_components = lambda: None  # type: ignore[method-assign]

    await plugin.api_send_poke(user_id="10001", group_id="20002", target_id="30003")
    await plugin.api_send_poke(qq_id="40004")

    assert captured == [
        {"user_id": 10001, "group_id": 20002, "target_id": 30003},
        {"user_id": 40004, "group_id": None, "target_id": None},
    ]


@pytest.mark.asyncio
async def test_public_api_get_forward_msg_and_get_record_support_official_fields() -> None:
    """公开 API 应接受官方 ``id`` 和 ``out_format`` 等字段。"""

    _napcat_gateway_name, _napcat_server_config, napcat_plugin_cls, _runtime_state_cls = _load_napcat_sdk_symbols()
    plugin = napcat_plugin_cls()
    captured: Dict[str, Dict[str, Any]] = {}

    class _SpyQueryService:
        async def get_forward_message(
            self,
            message_id: str | None = None,
            forward_id: str | None = None,
        ) -> Dict[str, Any]:
            captured["forward"] = {"message_id": message_id, "forward_id": forward_id}
            return {"messages": []}

        async def get_record_detail(
            self,
            file_name: str | None = None,
            file_id: str | None = None,
            out_format: str = "wav",
        ) -> Dict[str, Any]:
            captured["record"] = {
                "file_name": file_name,
                "file_id": file_id,
                "out_format": out_format,
            }
            return {"file_id": file_id or "record-1"}

    plugin._query_service = _SpyQueryService()
    plugin._ensure_runtime_components = lambda: None  # type: ignore[method-assign]

    forward_payload = await plugin.api_get_forward_msg(id="forward-1")
    record_payload = await plugin.api_get_record(file_id="record-1", out_format="mp3")

    assert forward_payload == {"messages": []}
    assert record_payload == {"file_id": "record-1"}
    assert captured["forward"] == {"message_id": None, "forward_id": "forward-1"}
    assert captured["record"] == {
        "file_name": None,
        "file_id": "record-1",
        "out_format": "mp3",
    }


@pytest.mark.asyncio
async def test_public_api_send_poke_rejects_conflicting_alias_values() -> None:
    """公开 ``send_poke`` API 应拒绝互相冲突的别名值。"""

    _napcat_gateway_name, _napcat_server_config, napcat_plugin_cls, _runtime_state_cls = _load_napcat_sdk_symbols()
    plugin = napcat_plugin_cls()
    plugin._ensure_runtime_components = lambda: None  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="user_id 与 qq_id 不能同时传递不同的值"):
        await plugin.api_send_poke(user_id="10001", qq_id="20002")


@pytest.mark.asyncio
async def test_public_api_get_forward_msg_rejects_conflicting_fields() -> None:
    """公开 ``get_forward_msg`` API 应拒绝冲突的双字段调用。"""

    _napcat_gateway_name, _napcat_server_config, napcat_plugin_cls, _runtime_state_cls = _load_napcat_sdk_symbols()
    plugin = napcat_plugin_cls()
    plugin._ensure_runtime_components = lambda: None  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="message_id 与 id 不能同时传递不同的值"):
        await plugin.api_get_forward_msg(message_id="forward-a", id="forward-b")


@pytest.mark.asyncio
async def test_public_api_get_record_requires_file_or_file_id() -> None:
    """公开 ``get_record`` API 至少需要一个官方定位字段。"""

    _napcat_gateway_name, _napcat_server_config, napcat_plugin_cls, _runtime_state_cls = _load_napcat_sdk_symbols()
    plugin = napcat_plugin_cls()
    plugin._ensure_runtime_components = lambda: None  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="file 或 file_id 至少提供一个"):
        await plugin.api_get_record()
