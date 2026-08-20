"""Provider 适配器族 — 厂商参数语义翻译（ZG-12/16）。

对标 Linux driver：内核只有统一的请求结构（struct request），
每个驱动把它翻译成具体硬件的寄存器操作。

组件只声明统一语义（temperature/max_tokens/thinking），
适配器按厂商能力翻译：
- DeepSeek：think 模式 temperature 无效 → 忽略 temperature
- OpenAI：temperature 0-2、max_tokens → max_completion_tokens、thinking → reasoning_effort
- Anthropic：temperature 0-1、thinking → extended_thinking（adaptive/budget）
- Passthrough：未知 client_type 原样透传
"""

from typing import Any, Protocol, runtime_checkable

DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 4096


@runtime_checkable
class ProviderAdapter(Protocol):
    """Provider 参数翻译适配器协议。"""

    def translate_request_params(
        self,
        params: dict[str, Any],
        *,
        capabilities: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        """将统一语义参数翻译为厂商 API 参数。

        Args:
            params: 统一语义参数（temperature/max_tokens/thinking 等）
            capabilities: 模型能力标签（供能力驱动参数过滤）

        Returns:
            厂商 API 参数（已按该厂商语义调整）
        """
        ...

    def get_supported_params(self) -> frozenset[str]:
        """该厂商支持的统一参数名集合。"""
        ...


class DeepSeekAdapter:
    """DeepSeek：think 模式 temperature 无效 → 忽略 temperature。

    依据 OpenClaw 能力表（deepseek-v4-flash/pro：thinking 模式温度无效、
    supportsReasoningEffort、maxTokensField=max_tokens）。
    """

    _SUPPORTED = frozenset({"max_tokens", "thinking"})

    def translate_request_params(
        self,
        params: dict[str, Any],
        *,
        capabilities: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        translated = dict(params)
        # think 模式 temperature 无效：移除，避免"配置了温度但没生效"的隐性陷阱
        if "temperature" in translated:
            del translated["temperature"]
        # 统一语义 thinking 翻译为 DeepSeek API 参数 enable_thinking
        # （声明支持 thinking 即必须翻译——P0-5：声明与实现一致性）
        if "thinking" in translated:
            translated["enable_thinking"] = bool(translated.pop("thinking"))
        # max_tokens 原样（deepseek 声明 maxTokensField=max_tokens）
        return translated

    def get_supported_params(self) -> frozenset[str]:
        return self._SUPPORTED


class OpenAIAdapter:
    """OpenAI：temperature 0-2、max_tokens → max_completion_tokens、thinking → reasoning_effort。"""

    _SUPPORTED = frozenset({"temperature", "max_tokens", "thinking", "top_p"})
    _TEMPERATURE_RANGE = (0.0, 2.0)

    def translate_request_params(
        self,
        params: dict[str, Any],
        *,
        capabilities: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        translated = dict(params)
        temperature = translated.get("temperature")
        if temperature is not None:
            low, high = self._TEMPERATURE_RANGE
            translated["temperature"] = max(low, min(high, float(temperature)))
        if "max_tokens" in translated:
            translated["max_completion_tokens"] = translated.pop("max_tokens")
        if "thinking" in translated:
            thinking = translated.pop("thinking")
            if thinking:
                translated["reasoning_effort"] = "high"
        return translated

    def get_supported_params(self) -> frozenset[str]:
        return self._SUPPORTED


class AnthropicAdapter:
    """Anthropic：temperature 0-1、thinking → extended_thinking（思考开启时不发送 temperature）。"""

    _SUPPORTED = frozenset({"temperature", "max_tokens", "thinking"})
    _TEMPERATURE_RANGE = (0.0, 1.0)

    def translate_request_params(
        self,
        params: dict[str, Any],
        *,
        capabilities: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        translated = dict(params)
        thinking = translated.get("thinking")
        if thinking:
            # 思考开启时 Anthropic 拒绝自定义 temperature（OpenClaw anthropic.ts 语义）
            translated.pop("temperature", None)
            translated["extended_thinking"] = True
            translated.pop("thinking")
        else:
            translated.pop("thinking", None)
            temperature = translated.get("temperature")
            if temperature is not None:
                low, high = self._TEMPERATURE_RANGE
                translated["temperature"] = max(low, min(high, float(temperature)))
        return translated

    def get_supported_params(self) -> frozenset[str]:
        return self._SUPPORTED


class PassthroughAdapter:
    """未知 client_type：原样透传（不翻译，不丢弃）。"""

    _SUPPORTED = frozenset({"temperature", "max_tokens", "thinking", "top_p", "top_k"})

    def translate_request_params(
        self,
        params: dict[str, Any],
        *,
        capabilities: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        return dict(params)

    def get_supported_params(self) -> frozenset[str]:
        return self._SUPPORTED


class ProviderAdapterFactory:
    """按 client_type 选择适配器。"""

    _ADAPTERS: dict[str, ProviderAdapter] = {
        "deepseek": DeepSeekAdapter(),
        "openai": OpenAIAdapter(),
        "anthropic": AnthropicAdapter(),
    }
    _passthrough = PassthroughAdapter()

    @classmethod
    def get_adapter(cls, client_type: str) -> ProviderAdapter:
        """获取适配器；未知 client_type 回退 PassthroughAdapter。"""
        return cls._ADAPTERS.get((client_type or "").lower(), cls._passthrough)

    @classmethod
    def register_adapter(cls, client_type: str, adapter: ProviderAdapter) -> None:
        """注册自定义适配器（插件可扩展）。"""
        cls._ADAPTERS[client_type.lower()] = adapter
