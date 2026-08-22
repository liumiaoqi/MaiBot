"""AdapterClient 适配器基类单元测试（ZG 批 6 T6.2）。

覆盖：await_task_with_interrupt 中断语义、_build_usage_record 使用量构建、
_attach_usage_record 挂载逻辑、_resolve_* 处理器解析、
get_response/get_embedding/get_audio_transcriptions 骨架流程。
"""

from typing import Any, Tuple

import asyncio

import pytest

from src.config.model_configs import APIProvider, ModelInfo
from src.llm_models.exceptions import ReqAbortException
from src.llm_models.model_client.adapter_base import (
    AdapterClient,
    ProviderResponseParser,
    ProviderStreamResponseHandler,
    await_task_with_interrupt,
)
from src.llm_models.model_client.base_client import (
    APIResponse,
    AudioTranscriptionRequest,
    EmbeddingRequest,
    ResponseRequest,

    UsageTuple,
)
from src.llm_models.payload_content.message import Message, RoleType, TextMessagePart


def _make_provider() -> APIProvider:
    """构造测试用 APIProvider。"""
    return APIProvider(name="test_provider", base_url="http://localhost:11434", api_key="sk-test", client_type="openai")


def _make_model_info() -> ModelInfo:
    """构造测试用 ModelInfo。"""
    return ModelInfo(name="test_model", model_identifier="gpt-4", api_provider="test_provider")


def _make_message_list() -> list[Message]:
    """构造测试用消息列表。"""
    return [Message(role=RoleType.User, parts=[TextMessagePart(text="hello")])]


class _ConcreteAdapter(AdapterClient[Any, Any]):
    """用于测试的具体 AdapterClient 子类，记录抽象方法调用。"""

    def __init__(self, api_provider: APIProvider) -> None:
        super().__init__(api_provider)
        self.execute_response_calls: list[Any] = []
        self.execute_embedding_calls: list[Any] = []
        self.execute_audio_calls: list[Any] = []
        self.default_stream_handler_built = 0
        self.default_response_parser_built = 0

    async def _execute_response_request(
        self,
        request: ResponseRequest,
        stream_response_handler: ProviderStreamResponseHandler[Any],
        response_parser: ProviderResponseParser[Any],
    ) -> Tuple[APIResponse, UsageTuple | None]:
        self.execute_response_calls.append((request, stream_response_handler, response_parser))
        return APIResponse(content="ok"), (10, 20, 30)

    async def _execute_embedding_request(
        self,
        request: EmbeddingRequest,
    ) -> Tuple[APIResponse, UsageTuple | None]:
        self.execute_embedding_calls.append(request)
        return APIResponse(embedding=[0.1, 0.2]), (5, 0, 5)

    async def _execute_audio_transcription_request(
        self,
        request: AudioTranscriptionRequest,
    ) -> Tuple[APIResponse, UsageTuple | None]:
        self.execute_audio_calls.append(request)
        return APIResponse(content="transcript"), None

    def _build_default_stream_response_handler(
        self,
        request: ResponseRequest,
    ) -> ProviderStreamResponseHandler[Any]:
        self.default_stream_handler_built += 1

        async def handler(raw: Any, flag: asyncio.Event | None) -> Tuple[APIResponse, UsageTuple | None]:
            return APIResponse(content="stream"), None

        return handler

    def _build_default_response_parser(
        self,
        request: ResponseRequest,
    ) -> ProviderResponseParser[Any]:
        self.default_response_parser_built += 1

        def parser(raw: Any) -> Tuple[APIResponse, UsageTuple | None]:
            return APIResponse(content="parsed"), None

        return parser

    async def get_support_image_formats(self) -> list[str]:
        return ["png"]


class TestAwaitTaskWithInterrupt:
    """await_task_with_interrupt 中断语义测试。"""

    @pytest.mark.asyncio
    async def test_normal_completion_returns_result(self) -> None:
        """任务正常完成时返回结果。"""
        async def _work() -> str:
            await asyncio.sleep(0)
            return "done"

        task = asyncio.create_task(_work())
        result = await await_task_with_interrupt(task, None)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_interrupt_flag_raises_req_abort(self) -> None:
        """中断信号已设置时抛出 ReqAbortException 并取消任务。"""
        flag = asyncio.Event()
        flag.set()

        async def _long_work() -> str:
            await asyncio.sleep(10)
            return "never"

        task = asyncio.create_task(_long_work())
        with pytest.raises(ReqAbortException):
            await await_task_with_interrupt(task, flag)
        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_none_interrupt_flag_waits_to_completion(self) -> None:
        """interrupt_flag 为 None 时等同于直接 await。"""
        async def _work() -> int:
            await asyncio.sleep(0.01)
            return 42

        task = asyncio.create_task(_work())
        result = await await_task_with_interrupt(task, None)
        assert result == 42

    @pytest.mark.asyncio
    async def test_child_cancelled_during_cleanup(self) -> None:
        """调用方被取消时子任务也被取消。"""
        async def _child() -> str:
            await asyncio.sleep(10)
            return "x"

        task = asyncio.create_task(_child())
        # 模拟调用方取消：直接取消等待协程
        waiter = asyncio.create_task(await_task_with_interrupt(task, None))
        await asyncio.sleep(0.01)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        # 子任务应已被取消
        assert task.cancelled() or task.done()


class TestBuildUsageRecord:
    """AdapterClient._build_usage_record 使用量构建测试。"""

    def test_three_tuple_defaults_cache_tokens_to_zero(self) -> None:
        """三元组使用量，缓存命中/未命中 token 默认为 0。"""
        model_info = _make_model_info()
        record = AdapterClient._build_usage_record(model_info, (100, 200, 300))
        assert record.model_name == "test_model"
        assert record.provider_name == "test_provider"
        assert record.prompt_tokens == 100
        assert record.completion_tokens == 200
        assert record.total_tokens == 300
        assert record.prompt_cache_hit_tokens == 0
        assert record.prompt_cache_miss_tokens == 0

    def test_five_tuple_preserves_cache_tokens(self) -> None:
        """五元组使用量保留缓存命中/未命中 token。"""
        model_info = _make_model_info()
        record = AdapterClient._build_usage_record(model_info, (100, 200, 300, 40, 60))
        assert record.prompt_cache_hit_tokens == 40
        assert record.prompt_cache_miss_tokens == 60


class TestAttachUsageRecord:
    """AdapterClient._attach_usage_record 挂载逻辑测试。"""

    def test_none_usage_record_leaves_response_unchanged(self) -> None:
        """usage_record 为 None 时不修改响应。"""
        adapter = _ConcreteAdapter(_make_provider())
        response = APIResponse(content="hello")
        result = adapter._attach_usage_record(response, _make_model_info(), None)
        assert result is response
        assert result.usage is None

    def test_usage_record_attached_to_response(self) -> None:
        """有效 usage_record 被挂载到响应。"""
        adapter = _ConcreteAdapter(_make_provider())
        response = APIResponse(content="hello")
        result = adapter._attach_usage_record(response, _make_model_info(), (10, 20, 30))
        assert result.usage is not None
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 20
        assert result.usage.total_tokens == 30


class TestResolveHandlers:
    """_resolve_stream_response_handler / _resolve_response_parser 解析测试。"""

    def test_custom_stream_handler_takes_precedence(self) -> None:
        """request 自带 stream_response_handler 时优先使用。"""
        adapter = _ConcreteAdapter(_make_provider())
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        async def custom_handler(raw: Any, flag: Any) -> Tuple[APIResponse, UsageTuple | None]:
            return APIResponse(content="custom"), None

        request.stream_response_handler = custom_handler
        resolved = adapter._resolve_stream_response_handler(request)
        assert resolved is custom_handler
        assert adapter.default_stream_handler_built == 0

    def test_fallback_to_default_stream_handler(self) -> None:
        """无自定义 handler 时构建默认 handler。"""
        adapter = _ConcreteAdapter(_make_provider())
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())
        adapter._resolve_stream_response_handler(request)
        assert adapter.default_stream_handler_built == 1

    def test_custom_response_parser_takes_precedence(self) -> None:
        """request 自带 async_response_parser 时优先使用。"""
        adapter = _ConcreteAdapter(_make_provider())
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())

        def custom_parser(raw: Any) -> Tuple[APIResponse, UsageTuple | None]:
            return APIResponse(content="custom"), None

        request.async_response_parser = custom_parser
        resolved = adapter._resolve_response_parser(request)
        assert resolved is custom_parser
        assert adapter.default_response_parser_built == 0

    def test_fallback_to_default_response_parser(self) -> None:
        """无自定义 parser 时构建默认 parser。"""
        adapter = _ConcreteAdapter(_make_provider())
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())
        adapter._resolve_response_parser(request)
        assert adapter.default_response_parser_built == 1


class TestAdapterClientSkeleton:
    """get_response/get_embedding/get_audio_transcriptions 骨架流程测试。"""

    @pytest.mark.asyncio
    async def test_get_response_invokes_execute_and_attaches_usage(self) -> None:
        """get_response 调用 _execute_response_request 并挂载使用量。"""
        adapter = _ConcreteAdapter(_make_provider())
        request = ResponseRequest(model_info=_make_model_info(), message_list=_make_message_list())
        response = await adapter.get_response(request)
        assert len(adapter.execute_response_calls) == 1
        assert response.content == "ok"
        assert response.usage is not None
        assert response.usage.prompt_tokens == 10
        assert response.usage.completion_tokens == 20

    @pytest.mark.asyncio
    async def test_get_embedding_invokes_execute_and_attaches_usage(self) -> None:
        """get_embedding 调用 _execute_embedding_request 并挂载使用量。"""
        adapter = _ConcreteAdapter(_make_provider())
        request = EmbeddingRequest(model_info=_make_model_info(), embedding_input="hello")
        response = await adapter.get_embedding(request)
        assert len(adapter.execute_embedding_calls) == 1
        assert response.embedding == [0.1, 0.2]
        assert response.usage is not None
        assert response.usage.total_tokens == 5

    @pytest.mark.asyncio
    async def test_get_audio_transcriptions_invokes_execute(self) -> None:
        """get_audio_transcriptions 调用 _execute_audio_transcription_request。"""
        adapter = _ConcreteAdapter(_make_provider())
        request = AudioTranscriptionRequest(model_info=_make_model_info(), audio_base64="dGVzdA==")
        response = await adapter.get_audio_transcriptions(request)
        assert len(adapter.execute_audio_calls) == 1
        assert response.content == "transcript"
        # usage_record 为 None，不应挂载
        assert response.usage is None


class TestAdapterClientAbstractContract:
    """AdapterClient 抽象方法契约测试。"""

    def test_cannot_instantiate_abstract_base_directly(self) -> None:
        """AdapterClient 含抽象方法，不能直接实例化。"""
        with pytest.raises(TypeError):
            AdapterClient(_make_provider())  # type: ignore[abstract]

    def test_subclass_missing_abstract_method_rejected(self) -> None:
        """子类未实现全部抽象方法时无法实例化。"""

        class _Incomplete(AdapterClient[Any, Any]):
            pass

        with pytest.raises(TypeError):
            _Incomplete(_make_provider())  # type: ignore[abstract]