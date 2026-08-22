"""OpenaiClient 单元测试（ZG 批 6 T6.2）。

覆盖：构造函数配置透传、_execute_response_request/_execute_embedding_request/
_execute_audio_transcription_request 错误处理路径（APIConnectionError/APIStatusError/
ReqAbortException/EmptyResponseException/通用异常 → 对应统一异常 + snapshot 挂载）。
所有外部 API 调用通过替换 client.client 为 AsyncMock 实现，不实际请求外部服务。
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from src.config.model_configs import APIProvider, ModelInfo, ReasoningParseMode, ToolArgumentParseMode
from src.llm_models.exceptions import (
    EmptyResponseException,
    NetworkConnectionError,
    ReqAbortException,
    RespNotOkException,
    RespParseException,
)
from src.llm_models.model_client.base_client import (
    APIResponse,
    AudioTranscriptionRequest,
    EmbeddingRequest,
    ResponseRequest,
)
from src.llm_models.model_client.openai_client import OpenaiClient
from src.llm_models.payload_content.message import Message, RoleType, TextMessagePart


# ---------- 测试辅助 ----------


def _make_provider(**overrides: Any) -> APIProvider:
    """构造测试用 OpenAI APIProvider。"""
    params: dict[str, Any] = {
        "name": "openai_test",
        "base_url": "http://localhost:11434",
        "api_key": "sk-test",
        "client_type": "openai",
    }
    params.update(overrides)
    return APIProvider(**params)


def _make_model_info() -> ModelInfo:
    """构造测试用 ModelInfo。"""
    return ModelInfo(name="test_model", model_identifier="gpt-4", api_provider="openai_test")


def _make_message_list() -> list[Message]:
    """构造测试用消息列表。"""
    return [Message(role=RoleType.User, parts=[TextMessagePart(text="hello")])]


def _make_api_status_error(status_code: int = 500, message: str = "boom") -> APIStatusError:
    """构造 OpenAI APIStatusError。"""
    response = httpx.Response(status_code=status_code, request=httpx.Request("POST", "http://localhost"))
    return APIStatusError(message, response=response, body=None)


def _make_api_connection_error(message: str = "conn fail") -> APIConnectionError:
    """构造 OpenAI APIConnectionError。"""
    return APIConnectionError(message=message, request=httpx.Request("POST", "http://localhost"))


def _make_client_with_mock() -> tuple[OpenaiClient, AsyncMock]:
    """构造 OpenaiClient 并替换底层 client 为 AsyncMock。"""
    client = OpenaiClient(_make_provider())
    mock = AsyncMock()
    client.client = mock
    return client, mock


@pytest.fixture
def snapshot_recorder(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """记录 save_failed_request_snapshot 调用，避免写文件。"""
    calls: list[dict[str, Any]] = []

    def _save(**kwargs: Any) -> None:
        calls.append(kwargs)
        return None

    monkeypatch.setattr("src.llm_models.model_client.openai_client.save_failed_request_snapshot", _save)
    monkeypatch.setattr("src.llm_models.model_client.openai_client.attach_request_snapshot", lambda exc, path: None)
    monkeypatch.setattr("src.llm_models.model_client.openai_client.has_request_snapshot", lambda exc: False)
    return calls


# ---------- 构造函数测试 ----------


class TestOpenaiClientInit:
    """OpenaiClient 构造函数配置透传测试。"""

    def test_init_creates_async_openai_instance(self) -> None:
        """构造函数创建 AsyncOpenAI 实例。"""
        client = OpenaiClient(_make_provider())
        assert isinstance(client.client, AsyncOpenAI)

    def test_init_propagates_api_provider(self) -> None:
        """构造函数透传 api_provider。"""
        provider = _make_provider()
        client = OpenaiClient(provider)
        assert client.api_provider is provider

    def test_init_normalizes_reasoning_parse_mode(self) -> None:
        """构造函数规范化 reasoning_parse_mode 为枚举。"""
        client = OpenaiClient(_make_provider(reasoning_parse_mode="native"))
        assert client.reasoning_parse_mode == ReasoningParseMode.NATIVE

    def test_init_invalid_reasoning_parse_mode_falls_back_to_auto(self) -> None:
        """无效 reasoning_parse_mode 回退为 AUTO。"""
        client = OpenaiClient(_make_provider(reasoning_parse_mode="bogus"))
        assert client.reasoning_parse_mode == ReasoningParseMode.AUTO

    def test_init_normalizes_tool_argument_parse_mode(self) -> None:
        """构造函数规范化 tool_argument_parse_mode 为枚举。"""
        client = OpenaiClient(_make_provider(tool_argument_parse_mode="strict"))
        assert client.tool_argument_parse_mode == ToolArgumentParseMode.STRICT

    def test_init_invalid_tool_argument_parse_mode_falls_back_to_auto(self) -> None:
        """无效 tool_argument_parse_mode 回退为 AUTO。"""
        client = OpenaiClient(_make_provider(tool_argument_parse_mode="bogus"))
        assert client.tool_argument_parse_mode == ToolArgumentParseMode.AUTO

    def test_init_reasoning_key_default_for_unknown_domain(self) -> None:
        """未知域名 reasoning_key 默认为 reasoning_content。"""
        client = OpenaiClient(_make_provider(base_url="http://unknown.example.com"))
        assert client.reasoning_key == "reasoning_content"

    def test_get_support_image_formats(self) -> None:
        """get_support_image_formats 返回支持的格式列表。"""
        client = OpenaiClient(_make_provider())
        formats = client.get_support_image_formats()
        assert "png" in formats
        assert "jpeg" in formats
        assert "webp" in formats
        assert "gif" in formats


# ---------- _execute_response_request 错误处理测试 ----------


class TestOpenaiClientResponseErrors:
    """_execute_response_request 错误处理路径测试。"""

    @pytest.mark.asyncio
    async def test_api_connection_error_wrapped_to_network_error(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """APIConnectionError 被包装为 NetworkConnectionError 并保存 snapshot。"""
        client, mock = _make_client_with_mock()
        mock.chat.completions.create = AsyncMock(side_effect=_make_api_connection_error())
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(NetworkConnectionError):
            await client._execute_response_request(
                request,
                client._build_default_stream_response_handler(request),
                client._build_default_response_parser(request),
            )
        assert len(snapshot_recorder) == 1
        assert snapshot_recorder[0]["client_type"] == "openai"
        assert snapshot_recorder[0]["operation"] == "chat.completions.create"

    @pytest.mark.asyncio
    async def test_api_status_error_wrapped_to_resp_not_ok(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """APIStatusError 被包装为 RespNotOkException 并保存 snapshot。"""
        client, mock = _make_client_with_mock()
        mock.chat.completions.create = AsyncMock(side_effect=_make_api_status_error(status_code=429))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(RespNotOkException) as exc_info:
            await client._execute_response_request(
                request,
                client._build_default_stream_response_handler(request),
                client._build_default_response_parser(request),
            )
        assert exc_info.value.status_code == 429
        assert len(snapshot_recorder) == 1

    @pytest.mark.asyncio
    async def test_req_abort_exception_propagates(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """ReqAbortException 直接透传，不保存 snapshot。"""
        client, mock = _make_client_with_mock()
        mock.chat.completions.create = AsyncMock(side_effect=ReqAbortException("中断"))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(ReqAbortException):
            await client._execute_response_request(
                request,
                client._build_default_stream_response_handler(request),
                client._build_default_response_parser(request),
            )
        # ReqAbortException 走 `except ReqAbortException: raise`，不经过 snapshot 分支
        assert len(snapshot_recorder) == 0

    @pytest.mark.asyncio
    async def test_empty_response_exception_snapshot_attached(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """EmptyResponseException 保存 snapshot 后透传。"""
        client, mock = _make_client_with_mock()
        mock.chat.completions.create = AsyncMock(side_effect=EmptyResponseException(None, "空响应"))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(EmptyResponseException):
            await client._execute_response_request(
                request,
                client._build_default_stream_response_handler(request),
                client._build_default_response_parser(request),
            )
        assert len(snapshot_recorder) == 1

    @pytest.mark.asyncio
    async def test_resp_parse_exception_snapshot_attached(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """RespParseException 保存 snapshot 后透传。"""
        client, mock = _make_client_with_mock()
        mock.chat.completions.create = AsyncMock(side_effect=RespParseException(None, "解析失败"))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(RespParseException):
            await client._execute_response_request(
                request,
                client._build_default_stream_response_handler(request),
                client._build_default_response_parser(request),
            )
        assert len(snapshot_recorder) == 1

    @pytest.mark.asyncio
    async def test_generic_exception_snapshot_attached(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """通用异常保存 snapshot 后透传。"""
        client, mock = _make_client_with_mock()
        mock.chat.completions.create = AsyncMock(side_effect=RuntimeError("未知错误"))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(RuntimeError):
            await client._execute_response_request(
                request,
                client._build_default_stream_response_handler(request),
                client._build_default_response_parser(request),
            )
        assert len(snapshot_recorder) == 1


# ---------- _execute_embedding_request 错误处理测试 ----------


class TestOpenaiClientEmbeddingErrors:
    """_execute_embedding_request 错误处理路径测试。"""

    @pytest.mark.asyncio
    async def test_api_connection_error_wrapped_to_network_error(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """embedding APIConnectionError 包装为 NetworkConnectionError。"""
        client, mock = _make_client_with_mock()
        mock.embeddings.create = AsyncMock(side_effect=_make_api_connection_error())
        request = EmbeddingRequest(model_info=_make_model_info(), embedding_input="hello")

        with pytest.raises(NetworkConnectionError):
            await client._execute_embedding_request(request)
        assert len(snapshot_recorder) == 1
        assert snapshot_recorder[0]["operation"] == "embeddings.create"

    @pytest.mark.asyncio
    async def test_api_status_error_wrapped_to_resp_not_ok(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """embedding APIStatusError 包装为 RespNotOkException。"""
        client, mock = _make_client_with_mock()
        mock.embeddings.create = AsyncMock(side_effect=_make_api_status_error(status_code=401))
        request = EmbeddingRequest(model_info=_make_model_info(), embedding_input="hello")

        with pytest.raises(RespNotOkException) as exc_info:
            await client._execute_embedding_request(request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_generic_exception_snapshot_attached(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """embedding 通用异常保存 snapshot 后透传。"""
        client, mock = _make_client_with_mock()
        mock.embeddings.create = AsyncMock(side_effect=ValueError("嵌入失败"))
        request = EmbeddingRequest(model_info=_make_model_info(), embedding_input="hello")

        with pytest.raises(ValueError):
            await client._execute_embedding_request(request)
        assert len(snapshot_recorder) == 1

    @pytest.mark.asyncio
    async def test_empty_embedding_data_raises_resp_parse_exception(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """嵌入响应 data 为空时抛出 RespParseException。"""
        client, mock = _make_client_with_mock()
        empty_response = MagicMock()
        empty_response.data = []
        empty_response.usage = None
        mock.embeddings.create = AsyncMock(return_value=empty_response)
        request = EmbeddingRequest(model_info=_make_model_info(), embedding_input="hello")

        with pytest.raises(RespParseException):
            await client._execute_embedding_request(request)


# ---------- _execute_audio_transcription_request 错误处理测试 ----------


class TestOpenaiClientAudioErrors:
    """_execute_audio_transcription_request 错误处理路径测试。"""

    @pytest.mark.asyncio
    async def test_api_connection_error_wrapped_to_network_error(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """audio APIConnectionError 包装为 NetworkConnectionError。"""
        client, mock = _make_client_with_mock()
        mock.audio.transcriptions.create = AsyncMock(side_effect=_make_api_connection_error())
        request = AudioTranscriptionRequest(model_info=_make_model_info(), audio_base64="dGVzdA==")

        with pytest.raises(NetworkConnectionError):
            await client._execute_audio_transcription_request(request)
        assert len(snapshot_recorder) == 1
        assert snapshot_recorder[0]["operation"] == "audio.transcriptions.create"

    @pytest.mark.asyncio
    async def test_api_status_error_wrapped_to_resp_not_ok(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """audio APIStatusError 包装为 RespNotOkException。"""
        client, mock = _make_client_with_mock()
        mock.audio.transcriptions.create = AsyncMock(side_effect=_make_api_status_error(status_code=413))
        request = AudioTranscriptionRequest(model_info=_make_model_info(), audio_base64="dGVzdA==")

        with pytest.raises(RespNotOkException) as exc_info:
            await client._execute_audio_transcription_request(request)
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_generic_exception_snapshot_attached(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """audio 通用异常保存 snapshot 后透传。"""
        client, mock = _make_client_with_mock()
        mock.audio.transcriptions.create = AsyncMock(side_effect=RuntimeError("音频失败"))
        request = AudioTranscriptionRequest(model_info=_make_model_info(), audio_base64="dGVzdA==")

        with pytest.raises(RuntimeError):
            await client._execute_audio_transcription_request(request)
        assert len(snapshot_recorder) == 1


# ---------- 成功路径测试 ----------


def _simple_parser(raw: Any) -> tuple[APIResponse, Any]:
    """简化的非流式响应解析器，用于成功路径测试。"""
    return APIResponse(content="parsed", raw_data=raw), (1, 2, 3)


class TestOpenaiClientSuccessPaths:
    """_execute_* 成功路径测试，覆盖非错误分支。"""

    @pytest.mark.asyncio
    async def test_response_success_non_stream(self) -> None:
        """非流式响应成功返回解析结果。"""
        client, mock = _make_client_with_mock()
        mock.chat.completions.create = AsyncMock(return_value=MagicMock())
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        response, usage = await client._execute_response_request(
            request,
            client._build_default_stream_response_handler(request),
            _simple_parser,
        )
        assert response.content == "parsed"
        assert usage == (1, 2, 3)

    @pytest.mark.asyncio
    async def test_embedding_success(self) -> None:
        """嵌入成功返回 embedding 向量。"""
        client, mock = _make_client_with_mock()
        embedding_response = MagicMock()
        item = MagicMock()
        item.embedding = [0.1, 0.2, 0.3]
        embedding_response.data = [item]
        embedding_response.usage = None
        mock.embeddings.create = AsyncMock(return_value=embedding_response)
        request = EmbeddingRequest(model_info=_make_model_info(), embedding_input="hello")

        response, usage = await client._execute_embedding_request(request)
        assert response.embedding == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_audio_success_with_text_attribute(self) -> None:
        """音频转写成功返回文本内容。"""
        client, mock = _make_client_with_mock()
        audio_response = MagicMock()
        audio_response.text = "转录结果"
        mock.audio.transcriptions.create = AsyncMock(return_value=audio_response)
        request = AudioTranscriptionRequest(model_info=_make_model_info(), audio_base64="dGVzdA==")

        response, _ = await client._execute_audio_transcription_request(request)
        assert response.content == "转录结果"

    @pytest.mark.asyncio
    async def test_audio_success_with_string_response(self) -> None:
        """音频转写返回纯字符串时直接作为内容。"""
        client, mock = _make_client_with_mock()
        mock.audio.transcriptions.create = AsyncMock(return_value="纯文本转录")
        request = AudioTranscriptionRequest(model_info=_make_model_info(), audio_base64="dGVzdA==")

        response, _ = await client._execute_audio_transcription_request(request)
        assert response.content == "纯文本转录"

