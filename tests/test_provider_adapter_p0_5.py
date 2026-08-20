"""P0-5 ProviderAdapter 翻译语义测试 — DeepSeek thinking→enable_thinking。

覆盖 spec 5.2.1-1~4（DeepSeek 翻译语义 + 声明一致性）+ 其余 adapter 快照回归
（OpenAI/Anthropic/Passthrough 零变化证明）+ Factory 路由。
"""

from src.llm_models.provider_adapter import (
    AnthropicAdapter,
    DeepSeekAdapter,
    OpenAIAdapter,
    PassthroughAdapter,
    ProviderAdapterFactory,
)


class TestDeepSeekAdapter:
    """P0-5: DeepSeek thinking → enable_thinking 翻译。"""

    def test_thinking_true_translates(self) -> None:
        """thinking=True + max_tokens → enable_thinking=True 且不含 thinking（spec 5.2.1-1）。"""
        result = DeepSeekAdapter().translate_request_params(
            {"thinking": True, "max_tokens": 4096}
        )
        assert result["enable_thinking"] is True
        assert "thinking" not in result
        assert result["max_tokens"] == 4096

    def test_thinking_false_translates(self) -> None:
        """thinking=False → 显式 enable_thinking=False（spec 5.2.1-2）。"""
        result = DeepSeekAdapter().translate_request_params({"thinking": False})
        assert result["enable_thinking"] is False
        assert "thinking" not in result

    def test_thinking_absent_no_key(self) -> None:
        """thinking 缺省 → 不产生 enable_thinking 键。"""
        result = DeepSeekAdapter().translate_request_params({"max_tokens": 1024})
        assert "enable_thinking" not in result
        assert "thinking" not in result

    def test_thinking_true_temperature_removed(self) -> None:
        """thinking=True + temperature → 无 temperature + enable_thinking=True（spec 5.2.1-4）。"""
        result = DeepSeekAdapter().translate_request_params(
            {"thinking": True, "temperature": 0.7}
        )
        assert "temperature" not in result
        assert result["enable_thinking"] is True

    def test_supported_params_consistency(self) -> None:
        """声明一致性：get_supported_params() 含 thinking 且翻译生效（spec 5.2.1-3）。"""
        adapter = DeepSeekAdapter()
        assert "thinking" in adapter.get_supported_params()
        result = adapter.translate_request_params({"thinking": True})
        assert result["enable_thinking"] is True


class TestOtherAdapterSnapshots:
    """P0-5 回归保护：其余 adapter 零变化快照。"""

    def test_openai_thinking_true(self) -> None:
        """OpenAI: thinking=True → reasoning_effort=high 且无 thinking。"""
        result = OpenAIAdapter().translate_request_params(
            {"thinking": True, "max_tokens": 2048}
        )
        assert result["reasoning_effort"] == "high"
        assert "thinking" not in result
        assert result["max_completion_tokens"] == 2048
        assert "max_tokens" not in result

    def test_openai_thinking_false_or_absent(self) -> None:
        """OpenAI: thinking=False/缺省 → 无 reasoning_effort。"""
        assert "reasoning_effort" not in OpenAIAdapter().translate_request_params({"thinking": False})
        assert "reasoning_effort" not in OpenAIAdapter().translate_request_params({})

    def test_anthropic_thinking_true(self) -> None:
        """Anthropic: thinking=True → extended_thinking + 删 temperature。"""
        result = AnthropicAdapter().translate_request_params(
            {"thinking": True, "temperature": 0.8}
        )
        assert result["extended_thinking"] is True
        assert "temperature" not in result
        assert "thinking" not in result

    def test_anthropic_thinking_false_clamp(self) -> None:
        """Anthropic: thinking=False → clamp 语义保持（0-1）。"""
        adapter = AnthropicAdapter()
        assert "extended_thinking" not in adapter.translate_request_params({"thinking": False})
        result = adapter.translate_request_params({"temperature": 2.0})
        assert result["temperature"] == 1.0

    def test_passthrough_copy(self) -> None:
        """Passthrough: 原样拷贝、键不变。"""
        params = {"thinking": True, "temperature": 0.5, "custom": "x"}
        result = PassthroughAdapter().translate_request_params(params)
        assert result == params

    def test_factory_routing(self) -> None:
        """Factory: get_adapter('deepseek') → DeepSeekAdapter；未知 → Passthrough。"""
        assert isinstance(ProviderAdapterFactory.get_adapter("deepseek"), DeepSeekAdapter)
        assert isinstance(ProviderAdapterFactory.get_adapter("unknown-xyz"), PassthroughAdapter)