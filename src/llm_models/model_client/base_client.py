from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Tuple, Type

import asyncio

from src.common.logger import get_logger
from src.config.config import config_manager
from src.config.model_configs import APIProvider, ModelInfo
from src.llm_models.payload_content.message import Message
from src.llm_models.payload_content.resp_format import RespFormat
from src.llm_models.payload_content.tool_option import ToolCall, ToolOption

logger = get_logger("model_client_registry")


@dataclass
class UsageRecord:
    """
    使用记录类
    """

    model_name: str
    """模型名称"""

    provider_name: str
    """提供商名称"""

    prompt_tokens: int
    """提示token数"""

    completion_tokens: int
    """完成token数"""

    total_tokens: int
    """总token数"""

    prompt_cache_hit_tokens: int = 0
    """输入中缓存命中的 token 数"""

    prompt_cache_miss_tokens: int = 0
    """输入中缓存未命中的 token 数"""


@dataclass
class APIResponse:
    """
    API响应类
    """

    content: str | None = None
    """响应内容"""

    reasoning_content: str | None = None
    """推理内容"""

    tool_calls: List[ToolCall] | None = None
    """工具调用 [(工具名称, 工具参数), ...]"""

    embedding: List[float] | None = None
    """嵌入向量"""

    usage: UsageRecord | None = None
    """使用情况 (prompt_tokens, completion_tokens, total_tokens)"""

    raw_data: Any = None
    """响应原始数据"""


UsageTuple = Tuple[int, ...]
"""统一的使用量元组，顺序为 `(prompt_tokens, completion_tokens, total_tokens, prompt_cache_hit_tokens, prompt_cache_miss_tokens)`。"""

StreamResponseHandler = Callable[
    [Any, asyncio.Event | None],
    Coroutine[Any, Any, Tuple["APIResponse", UsageTuple | None]],
]
"""统一的流式响应处理函数类型。"""

ResponseParser = Callable[[Any], Tuple["APIResponse", UsageTuple | None]]
"""统一的非流式响应解析函数类型。"""


@dataclass(slots=True)
class ResponseRequest:
    """统一的文本/多模态响应请求。"""

    model_info: ModelInfo
    message_list: List[Message]
    tool_options: List[ToolOption] | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    response_format: RespFormat | None = None
    stream_response_handler: StreamResponseHandler | None = None
    async_response_parser: ResponseParser | None = None
    interrupt_flag: asyncio.Event | None = None
    extra_params: Dict[str, Any] = field(default_factory=dict)

    def copy_with(self, **changes: Any) -> "ResponseRequest":
        """基于当前请求创建一个带局部变更的新请求。

        Args:
            **changes: 需要覆盖的字段值。

        Returns:
            ResponseRequest: 复制后的请求对象。
        """
        payload = {
            "model_info": self.model_info,
            "message_list": list(self.message_list),
            "tool_options": None if self.tool_options is None else list(self.tool_options),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "response_format": self.response_format,
            "stream_response_handler": self.stream_response_handler,
            "async_response_parser": self.async_response_parser,
            "interrupt_flag": self.interrupt_flag,
            "extra_params": dict(self.extra_params),
        }
        payload.update(changes)
        return ResponseRequest(**payload)


@dataclass(slots=True)
class EmbeddingRequest:
    """统一的嵌入请求。"""

    model_info: ModelInfo
    embedding_input: str
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AudioTranscriptionRequest:
    """统一的音频转录请求。"""

    model_info: ModelInfo
    audio_base64: str
    max_tokens: int | None = None
    extra_params: Dict[str, Any] = field(default_factory=dict)


ClientRequest = ResponseRequest | EmbeddingRequest | AudioTranscriptionRequest
"""统一客户端请求类型。"""


class BaseClient(ABC):
    """
    基础客户端
    """

    api_provider: APIProvider

    def __init__(self, api_provider: APIProvider) -> None:
        """初始化基础客户端。

        Args:
            api_provider: API 提供商配置。
        """
        self.api_provider = api_provider

    @abstractmethod
    async def get_response(self, request: ResponseRequest) -> APIResponse:
        """获取对话响应。

        Args:
            request: 统一响应请求对象。

        Returns:
            APIResponse: 统一响应对象。
        """
        raise NotImplementedError("'get_response' method should be overridden in subclasses")

    @abstractmethod
    async def get_embedding(self, request: EmbeddingRequest) -> APIResponse:
        """获取文本嵌入。

        Args:
            request: 统一嵌入请求对象。

        Returns:
            APIResponse: 嵌入响应。
        """
        raise NotImplementedError("'get_embedding' method should be overridden in subclasses")

    @abstractmethod
    async def get_audio_transcriptions(self, request: AudioTranscriptionRequest) -> APIResponse:
        """获取音频转录。

        Args:
            request: 统一音频转录请求对象。

        Returns:
            APIResponse: 音频转录响应。
        """
        raise NotImplementedError("'get_audio_transcriptions' method should be overridden in subclasses")

    @abstractmethod
    def get_support_image_formats(self) -> List[str]:
        """获取支持的图片格式。

        Returns:
            List[str]: 支持的图片格式列表。
        """
        raise NotImplementedError("'get_support_image_formats' method should be overridden in subclasses")


class ClientRegistry:
    """客户端注册表。"""

    def __init__(self) -> None:
        """初始化注册表并绑定配置重载回调。"""
        self.client_registry: Dict[str, Type[BaseClient]] = {}
        """APIProvider.type -> BaseClient的映射表"""
        self.client_instance_cache: Dict[str, BaseClient] = {}
        """APIProvider.name -> BaseClient的映射表"""
        config_manager.register_reload_callback(self.clear_client_instance_cache)

    def register_client_class(self, client_type: str) -> Callable[[Type[BaseClient]], Type[BaseClient]]:
        """注册 API 客户端类。

        Args:
            client_type: 客户端类型标识。

        Returns:
            Callable[[Type[BaseClient]], Type[BaseClient]]: 装饰器函数。
        """

        def decorator(cls: Type[BaseClient]) -> Type[BaseClient]:
            if not issubclass(cls, BaseClient):
                raise TypeError(f"{cls.__name__} is not a subclass of BaseClient")
            self.client_registry[client_type] = cls
            return cls

        return decorator

    def get_client_class_instance(self, api_provider: APIProvider, force_new: bool = False) -> BaseClient:
        """获取注册的 API 客户端实例。

        Args:
            api_provider: APIProvider 实例。
            force_new: 是否强制创建新实例。

        Returns:
            BaseClient: 注册的 API 客户端实例。
        """
        from . import ensure_client_type_loaded

        ensure_client_type_loaded(api_provider.client_type)

        # 如果强制创建新实例，直接创建不使用缓存
        if force_new:
            if client_class := self.client_registry.get(api_provider.client_type):
                return client_class(api_provider)
            else:
                raise KeyError(f"'{api_provider.client_type}' 类型的 Client 未注册")

        # 正常的缓存逻辑
        if api_provider.name not in self.client_instance_cache:
            if client_class := self.client_registry.get(api_provider.client_type):
                self.client_instance_cache[api_provider.name] = client_class(api_provider)
            else:
                raise KeyError(f"'{api_provider.client_type}' 类型的 Client 未注册")
        return self.client_instance_cache[api_provider.name]

    def clear_client_instance_cache(self) -> None:
        """清空客户端实例缓存。"""
        self.client_instance_cache.clear()
        logger.info("检测到配置重载，已清空LLM客户端实例缓存")


client_registry = ClientRegistry()
