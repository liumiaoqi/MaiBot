"""GeminiClient 单元测试（ZG 批 6 T6.2）。

覆盖：构造函数配置透传、clamp_thinking_budget 预算裁剪、_resolve_model_identifier
模型标识解析、_execute_response_request/_execute_embedding_request 错误处理路径
（ClientError/ServerError/ReqAbortException/EmptyResponseException/
FunctionInvocationError/通用异常 → 对应统一异常 + snapshot 挂载）。
所有外部 API 调用通过替换 client.client 为 AsyncMock 实现，不实际请求外部服务。
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from google.genai.errors import (
    ClientError,
    FunctionInvocationError,
    ServerError,
    UnknownFunctionCallArgumentError,
    UnsupportedFunctionError,
)

from src.config.model_configs import APIProvider, ModelInfo
from src.llm_models.exceptions import (
    EmptyResponseException,
    NetworkConnectionError,
    ReqAbortException,
    RespNotOkException,
    RespParseException,
)
from src.llm_models.model_client.base_client import (
    APIResponse,
    EmbeddingRequest,
    ResponseRequest,
)
from src.llm_models.model_client.gemini_client import (
    THINKING_BUDGET_AUTO,
    THINKING_BUDGET_DISABLED,
    GeminiClient,
)
from src.llm_models.payload_content.message import Message, RoleType, TextMessagePart


# ---------- 测试辅助 ----------


def _make_provider(**overrides: Any) -> APIProvider:
    """构造测试用 Gemini APIProvider。"""
    params: dict[str, Any] = {
        "name": "gemini_test",
        "base_url": "",
        "api_key": "AIza-test",
        "client_type": "gemini",
    }
    params.update(overrides)
    return APIProvider(**params)


def _make_model_info() -> ModelInfo:
    """构造测试用 ModelInfo。"""
    return ModelInfo(name="gem_model", model_identifier="gemini-2.5-flash", api_provider="gemini_test")


def _make_message_list() -> list[Message]:
    """构造测试用消息列表。"""
    return [Message(role=RoleType.User, parts=[TextMessagePart(text="hello")])]


def _make_client_error(code: int = 404) -> ClientError:
    """构造 Gemini ClientError。"""
    return ClientError(code, {"error": {"message": "client error"}})


def _make_server_error(code: int = 500) -> ServerError:
    """构造 Gemini ServerError。"""
    return ServerError(code, {"error": {"message": "server error"}})


def _make_client_with_mock() -> tuple[GeminiClient, AsyncMock]:
    """构造 GeminiClient 并替换底层 client 为 AsyncMock。"""
    client = GeminiClient(_make_provider())
    mock = AsyncMock()
    client.client = mock
    return client, mock


def _noop_parser(raw: Any) -> tuple[APIResponse, Any]:
    """空响应解析器，错误路径不会走到。"""
    return APIResponse(content="parsed"), None


@pytest.fixture
def snapshot_recorder(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """记录 save_failed_request_snapshot 调用，避免写文件。"""
    calls: list[dict[str, Any]] = []

    def _save(**kwargs: Any) -> None:
        calls.append(kwargs)
        return None

    monkeypatch.setattr("src.llm_models.model_client.gemini_client.save_failed_request_snapshot", _save)
    monkeypatch.setattr("src.llm_models.model_client.gemini_client.attach_request_snapshot", lambda exc, path: None)
    monkeypatch.setattr("src.llm_models.model_client.gemini_client.has_request_snapshot", lambda exc: False)
    return calls


# ---------- 构造函数测试 ----------


class TestGeminiClientInit:
    """GeminiClient 构造函数配置透传测试。"""

    def test_init_creates_genai_client(self) -> None:
        """构造函数创建 genai.Client 实例。"""
        from google import genai

        client = GeminiClient(_make_provider())
        assert isinstance(client.client, genai.Client)

    def test_init_propagates_api_provider(self) -> None:
        """构造函数透传 api_provider。"""
        provider = _make_provider()
        client = GeminiClient(provider)
        assert client.api_provider is provider


# ---------- clamp_thinking_budget 静态方法测试 ----------


class TestGeminiClampThinkingBudget:
    """GeminiClient.clamp_thinking_budget 预算裁剪测试。"""

    def test_none_extra_params_returns_auto(self) -> None:
        """无额外参数时返回 AUTO。"""
        assert GeminiClient.clamp_thinking_budget(None, "gemini-2.5-flash") == THINKING_BUDGET_AUTO

    def test_explicit_auto_returns_auto(self) -> None:
        """显式 AUTO 值返回 AUTO。"""
        result = GeminiClient.clamp_thinking_budget({"thinking_budget": THINKING_BUDGET_AUTO}, "gemini-2.5-flash")
        assert result == THINKING_BUDGET_AUTO

    def test_in_range_value_preserved(self) -> None:
        """范围内的预算值被保留。"""
        assert GeminiClient.clamp_thinking_budget({"thinking_budget": 100}, "gemini-2.5-flash") == 100

    def test_disabled_on_supported_model(self) -> None:
        """支持禁用的模型接受 DISABLED。"""
        result = GeminiClient.clamp_thinking_budget({"thinking_budget": THINKING_BUDGET_DISABLED}, "gemini-2.5-flash")
        assert result == THINKING_BUDGET_DISABLED

    def test_disabled_on_unsupported_model_falls_back_to_min(self) -> None:
        """不支持禁用的模型将 DISABLED 回退为最小值。"""
        result = GeminiClient.clamp_thinking_budget({"thinking_budget": THINKING_BUDGET_DISABLED}, "gemini-2.5-pro")
        assert result == 128

    def test_too_large_clamped_to_max(self) -> None:
        """过大预算裁剪到最大值。"""
        result = GeminiClient.clamp_thinking_budget({"thinking_budget": 999999}, "gemini-2.5-flash")
        assert result == 24576

    def test_too_small_clamped_to_min(self) -> None:
        """过小预算裁剪到最小值。"""
        result = GeminiClient.clamp_thinking_budget({"thinking_budget": -5}, "gemini-2.5-flash")
        assert result == 1

    def test_invalid_value_falls_back_to_auto(self) -> None:
        """无效预算值回退为 AUTO。"""
        result = GeminiClient.clamp_thinking_budget({"thinking_budget": "not-a-number"}, "gemini-2.5-flash")
        assert result == THINKING_BUDGET_AUTO

    def test_unknown_model_falls_back_to_auto(self) -> None:
        """未配置范围的模型回退为 AUTO。"""
        result = GeminiClient.clamp_thinking_budget({"thinking_budget": 100}, "totally-unknown-model")
        assert result == THINKING_BUDGET_AUTO


# ---------- _resolve_model_identifier 静态方法测试 ----------


class TestGeminiResolveModelIdentifier:
    """GeminiClient._resolve_model_identifier 模型标识解析测试。"""

    def test_plain_identifier_no_search(self) -> None:
        """普通标识符不启用搜索。"""
        identifier, search = GeminiClient._resolve_model_identifier("gemini-2.5-flash", {})
        assert identifier == "gemini-2.5-flash"
        assert search is False

    def test_search_suffix_enables_search(self) -> None:
        """-search 后缀启用 Google Search 并剥离后缀。"""
        identifier, search = GeminiClient._resolve_model_identifier("gemini-2.5-flash-search", {})
        assert identifier == "gemini-2.5-flash"
        assert search is True

    def test_explicit_enable_search_flag(self) -> None:
        """extra_params 显式启用搜索。"""
        identifier, search = GeminiClient._resolve_model_identifier(
            "gemini-2.5-flash", {"enable_google_search": True}
        )
        assert identifier == "gemini-2.5-flash"
        assert search is True


# ---------- _execute_response_request 错误处理测试 ----------


class TestGeminiClientResponseErrors:
    """_execute_response_request 错误处理路径测试。"""

    @pytest.mark.asyncio
    async def test_client_error_wrapped_to_resp_not_ok(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """ClientError 包装为 RespNotOkException 并保存 snapshot。"""
        client, mock = _make_client_with_mock()
        mock.aio.models.generate_content = AsyncMock(side_effect=_make_client_error(code=404))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(RespNotOkException) as exc_info:
            await client._execute_response_request(
                request,
                client._build_default_stream_response_handler(request),
                client._build_default_response_parser(request),
            )
        assert exc_info.value.status_code == 404
        assert len(snapshot_recorder) == 1
        assert snapshot_recorder[0]["client_type"] == "gemini"
        assert snapshot_recorder[0]["operation"] == "models.generate_content"

    @pytest.mark.asyncio
    async def test_server_error_wrapped_to_resp_not_ok(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """ServerError 包装为 RespNotOkException 并保存 snapshot。"""
        client, mock = _make_client_with_mock()
        mock.aio.models.generate_content = AsyncMock(side_effect=_make_server_error(code=503))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(RespNotOkException) as exc_info:
            await client._execute_response_request(
                request,
                client._build_default_stream_response_handler(request),
                client._build_default_response_parser(request),
            )
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_req_abort_exception_propagates(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """ReqAbortException 直接透传，不保存 snapshot。"""
        client, mock = _make_client_with_mock()
        mock.aio.models.generate_content = AsyncMock(side_effect=ReqAbortException("中断"))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(ReqAbortException):
            await client._execute_response_request(
                request,
                client._build_default_stream_response_handler(request),
                client._build_default_response_parser(request),
            )
        assert len(snapshot_recorder) == 0

    @pytest.mark.asyncio
    async def test_function_invocation_error_wrapped_to_resp_parse_exception(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """FunctionInvocationError 包装为 RespParseException 并保存 snapshot。"""
        client, mock = _make_client_with_mock()
        mock.aio.models.generate_content = AsyncMock(side_effect=FunctionInvocationError("坏参数"))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(RespParseException):
            await client._execute_response_request(
                request,
                client._build_default_stream_response_handler(request),
                client._build_default_response_parser(request),
            )
        assert len(snapshot_recorder) == 1

    @pytest.mark.asyncio
    async def test_unknown_function_call_argument_error_wrapped(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """UnknownFunctionCallArgumentError 包装为 RespParseException。"""
        client, mock = _make_client_with_mock()
        mock.aio.models.generate_content = AsyncMock(side_effect=UnknownFunctionCallArgumentError("未知参数"))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(RespParseException):
            await client._execute_response_request(
                request,
                client._build_default_stream_response_handler(request),
                client._build_default_response_parser(request),
            )

    @pytest.mark.asyncio
    async def test_unsupported_function_error_wrapped(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """UnsupportedFunctionError 包装为 RespParseException。"""
        client, mock = _make_client_with_mock()
        mock.aio.models.generate_content = AsyncMock(side_effect=UnsupportedFunctionError("不支持"))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(RespParseException):
            await client._execute_response_request(
                request,
                client._build_default_stream_response_handler(request),
                client._build_default_response_parser(request),
            )

    @pytest.mark.asyncio
    async def test_empty_response_exception_snapshot_attached(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """EmptyResponseException 保存 snapshot 后透传。"""
        client, mock = _make_client_with_mock()
        mock.aio.models.generate_content = AsyncMock(side_effect=EmptyResponseException(None, "空"))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(EmptyResponseException):
            await client._execute_response_request(
                request,
                client._build_default_stream_response_handler(request),
                client._build_default_response_parser(request),
            )
        assert len(snapshot_recorder) == 1

    @pytest.mark.asyncio
    async def test_generic_exception_wrapped_to_network_error(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """response 通用异常包装为 NetworkConnectionError 并保存 snapshot。"""
        client, mock = _make_client_with_mock()
        mock.aio.models.generate_content = AsyncMock(side_effect=RuntimeError("未知"))
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        with pytest.raises(NetworkConnectionError):
            await client._execute_response_request(
                request,
                client._build_default_stream_response_handler(request),
                client._build_default_response_parser(request),
            )
        assert len(snapshot_recorder) == 1


# ---------- _execute_embedding_request 错误处理测试 ----------


class TestGeminiClientEmbeddingErrors:
    """_execute_embedding_request 错误处理路径测试。"""

    @pytest.mark.asyncio
    async def test_client_error_wrapped_to_resp_not_ok(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """embedding ClientError 包装为 RespNotOkException。"""
        client, mock = _make_client_with_mock()
        mock.aio.models.embed_content = AsyncMock(side_effect=_make_client_error(code=400))
        request = EmbeddingRequest(model_info=_make_model_info(), embedding_input="hello")

        with pytest.raises(RespNotOkException) as exc_info:
            await client._execute_embedding_request(request)
        assert exc_info.value.status_code == 400
        assert len(snapshot_recorder) == 1
        assert snapshot_recorder[0]["operation"] == "models.embed_content"

    @pytest.mark.asyncio
    async def test_server_error_wrapped_to_resp_not_ok(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """embedding ServerError 包装为 RespNotOkException。"""
        client, mock = _make_client_with_mock()
        mock.aio.models.embed_content = AsyncMock(side_effect=_make_server_error(code=500))
        request = EmbeddingRequest(model_info=_make_model_info(), embedding_input="hello")

        with pytest.raises(RespNotOkException):
            await client._execute_embedding_request(request)

    @pytest.mark.asyncio
    async def test_generic_exception_wrapped_to_network_error(
        self, snapshot_recorder: list[dict[str, Any]]
    ) -> None:
        """embedding 通用异常包装为 NetworkConnectionError 并保存 snapshot。"""
        client, mock = _make_client_with_mock()
        mock.aio.models.embed_content = AsyncMock(side_effect=ValueError("嵌入失败"))
        request = EmbeddingRequest(model_info=_make_model_info(), embedding_input="hello")

        with pytest.raises(NetworkConnectionError):
            await client._execute_embedding_request(request)
        assert len(snapshot_recorder) == 1


# ---------- 成功路径测试 ----------


def _simple_parser(raw: Any) -> tuple[APIResponse, Any]:
    """简化的非流式响应解析器，用于成功路径测试。"""
    return APIResponse(content="parsed", raw_data=raw), (1, 2, 3)


class TestGeminiClientSuccessPaths:
    """_execute_* 成功路径测试，覆盖非错误分支。"""

    @pytest.mark.asyncio
    async def test_response_success_non_stream(self) -> None:
        """非流式响应成功返回解析结果。"""
        client, mock = _make_client_with_mock()
        mock.aio.models.generate_content = AsyncMock(return_value=MagicMock())
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
        embed_response = MagicMock()
        embedding_item = MagicMock()
        embedding_item.values = [0.1, 0.2, 0.3]
        embed_response.embeddings = [embedding_item]
        embed_response.metadata = None
        mock.aio.models.embed_content = AsyncMock(return_value=embed_response)
        request = EmbeddingRequest(model_info=_make_model_info(), embedding_input="hello")

        response, usage = await client._execute_embedding_request(request)
        assert response.embedding == [0.1, 0.2, 0.3]
        assert usage is not None
