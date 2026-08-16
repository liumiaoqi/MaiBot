"""ZG16-6a: Host servicer 测试——gRPC PluginConfigService 服务基础设施。

覆盖 PluginConfigServiceServicer 基类 + add_PluginConfigServiceServicer_to_server。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# grpc 生成文件 plugin_config_pb2_grpc.py 使用裸 import plugin_config_pb2，
# 需将 proto 目录加入 sys.path
_proto_dir = str(Path(__file__).resolve().parents[3] / "src" / "plugin_runtime_v2" / "proto")
if _proto_dir not in sys.path:
    sys.path.insert(0, _proto_dir)

from src.plugin_runtime_v2.proto import plugin_config_pb2  # noqa: E402
from src.plugin_runtime_v2.proto.plugin_config_pb2_grpc import (  # noqa: E402
    PluginConfigServiceServicer,
    PluginConfigServiceStub,
    add_PluginConfigServiceServicer_to_server,
)


def test_servicer_base_class_exists():
    """PluginConfigServiceServicer 基类存在。"""
    assert hasattr(PluginConfigServiceServicer, "UpdatePluginConfig")


def test_servicer_base_raises_not_implemented():
    """基类 UpdatePluginConfig 抛 NotImplementedError。"""
    servicer = PluginConfigServiceServicer()
    request = plugin_config_pb2.UpdatePluginConfigRequest(
        plugin_id="X", config_json="{}", revision=1, source="test"
    )
    context = MagicMock()
    with pytest.raises(NotImplementedError):
        servicer.UpdatePluginConfig(request, context)


def test_custom_servicer_override():
    """子类覆盖 UpdatePluginConfig。"""

    class MyServicer(PluginConfigServiceServicer):
        async def UpdatePluginConfig(self, request, context):
            return plugin_config_pb2.UpdatePluginConfigResponse(
                success=True, new_revision=request.revision
            )

    servicer = MyServicer()
    assert servicer is not None
    # 验证方法已覆盖
    assert MyServicer.UpdatePluginConfig is not PluginConfigServiceServicer.UpdatePluginConfig


def test_add_servicer_to_server():
    """add_PluginConfigServiceServicer_to_server 注册到 gRPC server。"""
    server = MagicMock()
    servicer = PluginConfigServiceServicer()
    add_PluginConfigServiceServicer_to_server(servicer, server)
    server.add_generic_rpc_handlers.assert_called_once()
    server.add_registered_method_handlers.assert_called_once()


def test_stub_has_update_method():
    """PluginConfigServiceStub 包含 UpdatePluginConfig 方法。"""
    channel = MagicMock()
    channel.unary_unary.return_value = MagicMock()
    stub = PluginConfigServiceStub(channel)
    assert hasattr(stub, "UpdatePluginConfig")
    channel.unary_unary.assert_called_once()


def test_request_message_fields():
    """UpdatePluginConfigRequest 消息字段。"""
    req = plugin_config_pb2.UpdatePluginConfigRequest()
    req.plugin_id = "org.test"
    req.config_json = '{"port": 3001}'
    req.revision = 5
    req.source = "file_watcher"
    assert req.plugin_id == "org.test"
    assert req.config_json == '{"port": 3001}'
    assert req.revision == 5
    assert req.source == "file_watcher"


def test_response_message_fields():
    """UpdatePluginConfigResponse 消息字段。"""
    resp = plugin_config_pb2.UpdatePluginConfigResponse()
    resp.success = True
    resp.error = ""
    resp.new_revision = 3
    assert resp.success is True
    assert resp.error == ""
    assert resp.new_revision == 3


def test_response_error_case():
    """UpdatePluginConfigResponse 错误场景。"""
    resp = plugin_config_pb2.UpdatePluginConfigResponse(
        success=False, error="插件未加载"
    )
    assert resp.success is False
    assert resp.error == "插件未加载"


def test_request_default_values():
    """UpdatePluginConfigRequest 默认值。"""
    req = plugin_config_pb2.UpdatePluginConfigRequest()
    assert req.plugin_id == ""
    assert req.config_json == ""
    assert req.revision == 0
    assert req.source == ""


def test_response_default_values():
    """UpdatePluginConfigResponse 默认值。"""
    resp = plugin_config_pb2.UpdatePluginConfigResponse()
    assert resp.success is False
    assert resp.error == ""
    assert resp.new_revision == 0
