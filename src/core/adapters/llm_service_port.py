"""LLMServiceAdapter — 将 LLMServiceClient 包装为 LLMService Protocol。"""


from collections import OrderedDict
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from src.common.data_models.llm_service_data_models import (
        LLMAudioTranscriptionResult,
        LLMGenerationOptions,
        LLMImageOptions,
        LLMResponseResult,
        MessageFactory,
    )
    from src.core.protocols import LLMService
    from src.services.llm_service import LLMServiceClient

from src.common.logger import get_logger

logger = get_logger("core.adapters.llm_service_port")

_provider: LLMService | None = None

_MAX_CACHE_SIZE = 64


def get_llm_service() -> LLMService:
    if _provider is None:
        raise RuntimeError("LLMService 未注册，请先调用 set_llm_service()")
    return _provider


def set_llm_service(service: LLMService) -> None:
    global _provider
    if _provider is not None:
        logger.warning("LLMService 已注册，将被覆盖")
    _provider = service


def reset_llm_service() -> None:
    global _provider
    _provider = None


class LLMServiceAdapter:
    """纯委托适配器，包裹 LLMServiceClient 实现 LLMService Protocol。

    内部使用 OrderedDict 做 LRU 缓存（maxlen=64），
    按 task_name:request_type:session_id 为键缓存客户端实例。
    """

    def __init__(self) -> None:
        self._client_cache: OrderedDict[str, LLMServiceClient] = OrderedDict()

    def _get_or_create_client(
        self,
        task_name: str,
        request_type: str,
        session_id: str,
        capabilities: Sequence[str] | None = None,
    ) -> LLMServiceClient:
        from src.services.llm_service import LLMServiceClient

        cache_key = f"{task_name}:{request_type}:{session_id}"
        client = self._client_cache.get(cache_key)
        if client is not None:
            self._client_cache.move_to_end(cache_key)
            return client

        client = LLMServiceClient(
            task_name=task_name,
            request_type=request_type,
            session_id=session_id,
            capabilities=capabilities,
        )
        self._client_cache[cache_key] = client
        if len(self._client_cache) > _MAX_CACHE_SIZE:
            self._client_cache.popitem(last=False)
        return client

    async def generate_response(
        self,
        task_name: str,
        prompt: str,
        options: LLMGenerationOptions | None = None,
        *,
        request_type: str = "",
        session_id: str = "",
    ) -> LLMResponseResult:
        client = self._get_or_create_client(task_name, request_type, session_id)
        return await client.generate_response(prompt, options, session_id=session_id)

    async def generate_response_with_messages(
        self,
        task_name: str,
        message_factory: MessageFactory,
        options: LLMGenerationOptions | None = None,
        *,
        request_type: str = "",
        session_id: str = "",
    ) -> LLMResponseResult:
        client = self._get_or_create_client(
            task_name, request_type, session_id,
            capabilities=getattr(options, "capabilities", None) if options else None,
        )
        return await client.generate_response_with_messages(message_factory, options, session_id=session_id)

    async def generate_response_for_image(
        self,
        task_name: str,
        prompt: str,
        image_base64: str,
        image_format: str,
        options: LLMImageOptions | None = None,
        *,
        request_type: str = "",
        session_id: str = "",
    ) -> LLMResponseResult:
        client = self._get_or_create_client(task_name, request_type, session_id)
        return await client.generate_response_for_image(prompt, image_base64, image_format, options, session_id=session_id)

    async def transcribe_audio(
        self,
        task_name: str,
        voice_base64: str,
        *,
        request_type: str = "",
        session_id: str = "",
    ) -> LLMAudioTranscriptionResult:
        client = self._get_or_create_client(task_name, request_type, session_id)
        return await client.transcribe_audio(voice_base64, session_id=session_id)
