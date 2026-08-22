"""PluginLLMClient 单元测试（ZG 批 6 T6.2）。

覆盖：构造函数配置透传、get_response/get_embedding/get_audio_transcriptions
插件调用契约、_invoke_provider 错误处理（supervisor 异常/response.error/success=False/
result 非 dict → RespParseException）、_build_api_response/_build_usage_record 静态方法。
所有插件 RPC 通过 MagicMock supervisor 实现，不实际调用外部服务。
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config.model_configs import APIProvider, ModelInfo
from src.llm_models.exceptions import RespParseException
from src.llm_models.model_client.base_client import (

    AudioTranscriptionRequest,
    EmbeddingRequest,
    ResponseRequest,
    UsageRecord,
)
from src.llm_models.model_client.plugin_client import PluginLLMClient
from src.llm_models.payload_content.message import Message, RoleType, TextMessagePart


# ---------- 测试辅助 ----------


def _make_provider() -> APIProvider:
    """构造测试用 APIProvider。"""
    return APIProvider(name="plugin_test", base_url="http://localhost:11434", api_key="sk-test", client_type="custom")


def _make_model_info() -> ModelInfo:
    """构造测试用 ModelInfo。"""
    return ModelInfo(name="p_model", model_identifier="custom-model", api_provider="plugin_test")


def _make_message_list() -> list[Message]:
    """构造测试用消息列表。"""
    return [Message(role=RoleType.User, parts=[TextMessagePart(text="hello")])]


def _make_supervisor() -> MagicMock:
    """构造 mock supervisor。"""
    return MagicMock()


def _make_client() -> tuple[PluginLLMClient, MagicMock]:
    """构造 PluginLLMClient 及其 mock supervisor。"""
    supervisor = _make_supervisor()
    client = PluginLLMClient(_make_provider(), supervisor, "plugin-1", "custom")
    return client, supervisor


def _make_success_response(result: dict[str, Any]) -> MagicMock:
    """构造成功的插件 RPC 响应 mock。"""
    response = MagicMock()
    response.error = None
    response.payload = {"success": True, "result": result}
    return response


def _make_error_response(message: str) -> MagicMock:
    """构造带 error 的插件 RPC 响应 mock。"""
    response = MagicMock()
    response.error = {"message": message}
    response.payload = None
    return response


# ---------- 构造函数测试 ----------


class TestPluginLLMClientInit:
    """PluginLLMClient 构造函数配置透传测试。"""

    def test_init_propagates_api_provider(self) -> None:
        """构造函数透传 api_provider。"""
        provider = _make_provider()
        supervisor = _make_supervisor()
        client = PluginLLMClient(provider, supervisor, "plugin-1", "custom")
        assert client.api_provider is provider

    def test_init_propagates_supervisor_and_ids(self) -> None:
        """构造函数透传 supervisor/plugin_id/client_type。"""
        supervisor = _make_supervisor()
        client = PluginLLMClient(_make_provider(), supervisor, "plugin-1", "custom")
        assert client._supervisor is supervisor
        assert client._plugin_id == "plugin-1"
        assert client._client_type == "custom"

    def test_get_support_image_formats(self) -> None:
        """get_support_image_formats 返回默认格式列表。"""
        client, _ = _make_client()
        assert client.get_support_image_formats() == ["jpeg", "jpg", "png", "webp"]


# ---------- get_response 测试 ----------


class TestPluginLLMClientGetResponse:
    """get_response 插件调用契约测试。"""

    @pytest.mark.asyncio
    async def test_success_returns_api_response_with_content(self) -> None:
        """成功响应构建带 content 的 APIResponse。"""
        client, supervisor = _make_client()
        supervisor.invoke_llm_provider = AsyncMock(
            return_value=_make_success_response({"content": "hello", "usage": {"prompt_tokens": 5}})
        )
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        response = await client.get_response(request)
        assert response.content == "hello"
        assert response.usage is not None
        assert response.usage.prompt_tokens == 5

    @pytest.mark.asyncio
    async def test_success_invokes_supervisor_with_plugin_id(self) -> None:
        """成功路径以正确 plugin_id/client_type 调用 supervisor。"""
        client, supervisor = _make_client()
        supervisor.invoke_llm_provider = AsyncMock(return_value=_make_success_response({"content": "ok"}))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        await client.get_response(request)
        call_kwargs = supervisor.invoke_llm_provider.call_args.kwargs
        assert call_kwargs["plugin_id"] == "plugin-1"
        assert call_kwargs["client_type"] == "custom"
        assert call_kwargs["operation"] == "response"

    @pytest.mark.asyncio
    async def test_custom_stream_handler_rejected(self) -> None:
        """request 自带 stream_response_handler 时拒绝。"""
        client, supervisor = _make_client()
        supervisor.invoke_llm_provider = AsyncMock(return_value=_make_success_response({"content": "ok"}))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())
        request.stream_response_handler = lambda raw, flag: None  # type: ignore[assignment]

        with pytest.raises(RespParseException):
            await client.get_response(request)

    @pytest.mark.asyncio
    async def test_custom_response_parser_rejected(self) -> None:
        """request 自带 async_response_parser 时拒绝。"""
        client, supervisor = _make_client()
        supervisor.invoke_llm_provider = AsyncMock(return_value=_make_success_response({"content": "ok"}))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())
        request.async_response_parser = lambda raw: None  # type: ignore[assignment]

        with pytest.raises(RespParseException):
            await client.get_response(request)

    @pytest.mark.asyncio
    async def test_supervisor_exception_wrapped_to_resp_parse_exception(self) -> None:
        """supervisor 抛异常时包装为 RespParseException。"""
        client, supervisor = _make_client()
        supervisor.invoke_llm_provider = AsyncMock(side_effect=RuntimeError("RPC 挂了"))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(RespParseException):
            await client.get_response(request)

    @pytest.mark.asyncio
    async def test_response_error_wrapped_to_resp_parse_exception(self) -> None:
        """插件返回 error 字段时抛出 RespParseException。"""
        client, supervisor = _make_client()
        supervisor.invoke_llm_provider = AsyncMock(return_value=_make_error_response("插件内部错误"))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(RespParseException):
            await client.get_response(request)

    @pytest.mark.asyncio
    async def test_success_false_wrapped_to_resp_parse_exception(self) -> None:
        """插件返回 success=False 时抛出 RespParseException。"""
        client, supervisor = _make_client()
        response = MagicMock()
        response.error = None
        response.payload = {"success": False, "result": "执行失败"}
        supervisor.invoke_llm_provider = AsyncMock(return_value=response)
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(RespParseException):
            await client.get_response(request)

    @pytest.mark.asyncio
    async def test_non_dict_result_wrapped_to_resp_parse_exception(self) -> None:
        """插件返回 result 非 dict 时抛出 RespParseException。"""
        client, supervisor = _make_client()
        response = MagicMock()
        response.error = None
        response.payload = {"success": True, "result": "not-a-dict"}
        supervisor.invoke_llm_provider = AsyncMock(return_value=response)
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(RespParseException):
            await client.get_response(request)


# ---------- get_embedding / get_audio_transcriptions 测试 ----------


class TestPluginLLMClientEmbeddingAndAudio:
    """get_embedding / get_audio_transcriptions 插件调用契约测试。"""

    @pytest.mark.asyncio
    async def test_get_embedding_success(self) -> None:
        """get_embedding 成功返回带 embedding 的 APIResponse。"""
        client, supervisor = _make_client()
        supervisor.invoke_llm_provider = AsyncMock(
            return_value=_make_success_response({"embedding": [0.1, 0.2, 0.3]})
        )
        request = EmbeddingRequest(model_info=_make_model_info(), embedding_input="hello")

        response = await client.get_embedding(request)
        assert response.embedding == [0.1, 0.2, 0.3]
        call_kwargs = supervisor.invoke_llm_provider.call_args.kwargs
        assert call_kwargs["operation"] == "embedding"

    @pytest.mark.asyncio
    async def test_get_embedding_supervisor_error_wrapped(self) -> None:
        """get_embedding supervisor 异常包装为 RespParseException。"""
        client, supervisor = _make_client()
        supervisor.invoke_llm_provider = AsyncMock(side_effect=RuntimeError("挂"))
        request = EmbeddingRequest(model_info=_make_model_info(), embedding_input="hello")

        with pytest.raises(RespParseException):
            await client.get_embedding(request)

    @pytest.mark.asyncio
    async def test_get_audio_transcriptions_success(self) -> None:
        """get_audio_transcriptions 成功返回带 content 的 APIResponse。"""
        client, supervisor = _make_client()
        supervisor.invoke_llm_provider = AsyncMock(
            return_value=_make_success_response({"content": "转录文本"})
        )
        request = AudioTranscriptionRequest(model_info=_make_model_info(), audio_base64="dGVzdA==")

        response = await client.get_audio_transcriptions(request)
        assert response.content == "转录文本"
        call_kwargs = supervisor.invoke_llm_provider.call_args.kwargs
        assert call_kwargs["operation"] == "audio_transcription"


# ---------- _build_usage_record 静态方法测试 ----------


class TestPluginLLMClientBuildUsageRecord:
    """PluginLLMClient._build_usage_record 使用量记录构建测试。"""

    def test_dict_input_builds_usage_record(self) -> None:
        """dict 输入构建 UsageRecord。"""
        record = PluginLLMClient._build_usage_record(
            {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            model_name="m",
            provider_name="p",
        )
        assert isinstance(record, UsageRecord)
        assert record.prompt_tokens == 10
        assert record.completion_tokens == 20
        assert record.total_tokens == 30
        assert record.model_name == "m"
        assert record.provider_name == "p"

    def test_non_dict_input_returns_none(self) -> None:
        """非 dict 输入返回 None。"""
        assert PluginLLMClient._build_usage_record(None, "m", "p") is None
        assert PluginLLMClient._build_usage_record("not-dict", "m", "p") is None
        assert PluginLLMClient._build_usage_record([1, 2], "m", "p") is None

    def test_missing_fields_default_to_zero(self) -> None:
        """缺失字段默认为 0。"""
        record = PluginLLMClient._build_usage_record({}, model_name="m", provider_name="p")
        assert record is not None
        assert record.prompt_tokens == 0
        assert record.completion_tokens == 0
        assert record.total_tokens == 0
        assert record.prompt_cache_hit_tokens == 0
        assert record.prompt_cache_miss_tokens == 0

    def test_cache_tokens_preserved(self) -> None:
        """缓存命中/未命中 token 被保留。"""
        record = PluginLLMClient._build_usage_record(
            {"prompt_cache_hit_tokens": 40, "prompt_cache_miss_tokens": 60},
            model_name="m",
            provider_name="p",
        )
        assert record is not None
        assert record.prompt_cache_hit_tokens == 40
        assert record.prompt_cache_miss_tokens == 60


# ---------- _build_api_response 静态方法测试 ----------


class TestPluginLLMClientBuildApiResponse:
    """PluginLLMClient._build_api_response 响应构建测试。"""

    def test_content_field_takes_precedence(self) -> None:
        """content 字段优先于 response 字段。"""
        response = PluginLLMClient._build_api_response(
            {"content": "primary", "response": "fallback"}, "m", "p"
        )
        assert response.content == "primary"

    def test_response_field_fallback(self) -> None:
        """无 content 时回退到 response 字段。"""
        response = PluginLLMClient._build_api_response({"response": "fallback"}, "m", "p")
        assert response.content == "fallback"

    def test_reasoning_content_field(self) -> None:
        """reasoning_content 字段被读取。"""
        response = PluginLLMClient._build_api_response({"reasoning_content": "thinking"}, "m", "p")
        assert response.reasoning_content == "thinking"

    def test_reasoning_field_fallback(self) -> None:
        """无 reasoning_content 时回退到 reasoning 字段。"""
        response = PluginLLMClient._build_api_response({"reasoning": "thinking"}, "m", "p")
        assert response.reasoning_content == "thinking"

    def test_embedding_list_converted(self) -> None:
        """embedding 列表被转换为 float 列表。"""
        response = PluginLLMClient._build_api_response({"embedding": [1, 2, 3]}, "m", "p")
        assert response.embedding == [1.0, 2.0, 3.0]

    def test_non_list_embedding_yields_none(self) -> None:
        """非 list embedding 置为 None。"""
        response = PluginLLMClient._build_api_response({"embedding": "not-list"}, "m", "p")
        assert response.embedding is None

    def test_raw_data_defaults_to_result(self) -> None:
        """无 raw_data 时回退到整个 result。"""
        result = {"content": "hi", "extra": 1}
        response = PluginLLMClient._build_api_response(result, "m", "p")
        assert response.raw_data == result

    def test_raw_data_explicit(self) -> None:
        """显式 raw_data 被保留。"""
        response = PluginLLMClient._build_api_response(
            {"content": "hi", "raw_data": {"custom": True}}, "m", "p"
        )
        assert response.raw_data == {"custom": True}

    def test_non_string_content_yields_none(self) -> None:
        """非字符串 content 置为 None。"""
        response = PluginLLMClient._build_api_response({"content": 123}, "m", "p")
        assert response.content is None

    def test_usage_attached(self) -> None:
        """usage dict 被挂载为 UsageRecord。"""
        response = PluginLLMClient._build_api_response(
            {"content": "hi", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            "m",
            "p",
        )
        assert response.usage is not None
        assert response.usage.prompt_tokens == 10