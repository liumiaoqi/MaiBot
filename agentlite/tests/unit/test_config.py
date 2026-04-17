"""Unit tests for configuration models.

This module tests all Pydantic configuration models including
ProviderConfig, ModelConfig, ToolConfig, and AgentConfig.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentlite import ProviderConfig, ModelConfig, AgentConfig


class TestProviderConfig:
    """Tests for ProviderConfig."""

    def test_provider_config_valid(self):
        """Test valid ProviderConfig creation."""
        config = ProviderConfig(
            type="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test123",
        )
        assert config.type == "openai"
        assert config.base_url == "https://api.openai.com/v1"
        assert config.api_key.get_secret_value() == "sk-test123"

    def test_provider_config_default_type(self):
        """Test ProviderConfig with default type."""
        config = ProviderConfig(
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
        )
        assert config.type == "openai"

    def test_provider_config_default_url(self):
        """Test ProviderConfig with default base_url."""
        config = ProviderConfig(
            api_key="sk-test",
        )
        assert config.base_url == "https://api.openai.com/v1"

    def test_provider_config_invalid_url_http(self):
        """Test ProviderConfig with invalid URL scheme."""
        with pytest.raises(ValidationError) as exc_info:
            ProviderConfig(
                type="openai",
                base_url="ftp://invalid.com",
                api_key="sk-test",
            )
        assert "base_url must start with http:// or https://" in str(exc_info.value)

    def test_provider_config_invalid_url_no_scheme(self):
        """Test ProviderConfig with URL without scheme."""
        with pytest.raises(ValidationError):
            ProviderConfig(
                base_url="api.openai.com/v1",
                api_key="sk-test",
            )

    def test_provider_config_custom_headers(self):
        """Test ProviderConfig with custom headers."""
        config = ProviderConfig(
            api_key="sk-test",
            headers={"X-Custom": "value"},
        )
        assert config.headers == {"X-Custom": "value"}

    def test_provider_config_default_headers(self):
        """Test ProviderConfig default headers."""
        config = ProviderConfig(api_key="sk-test")
        assert config.headers == {}

    def test_provider_config_timeout(self):
        """Test ProviderConfig timeout."""
        config = ProviderConfig(
            api_key="sk-test",
            timeout=30.0,
        )
        assert config.timeout == 30.0

    def test_provider_config_default_timeout(self):
        """Test ProviderConfig default timeout."""
        config = ProviderConfig(api_key="sk-test")
        assert config.timeout == 60.0

    def test_provider_config_api_key_is_secret_str(self):
        """Test that api_key is stored as SecretStr."""
        config = ProviderConfig(api_key="sk-secret")
        # SecretStr should not expose value in repr/str
        assert "sk-secret" not in str(config.api_key)
        # But can get value explicitly
        assert config.api_key.get_secret_value() == "sk-secret"


class TestModelConfig:
    """Tests for ModelConfig."""

    def test_model_config_valid(self):
        """Test valid ModelConfig creation."""
        config = ModelConfig(
            provider="openai",
            model="gpt-4",
        )
        assert config.provider == "openai"
        assert config.model == "gpt-4"

    def test_model_config_with_all_fields(self):
        """Test ModelConfig with all optional fields."""
        config = ModelConfig(
            provider="openai",
            model="gpt-4",
            max_tokens=1000,
            temperature=0.7,
            top_p=0.9,
            capabilities={"streaming", "tool_calling"},
        )
        assert config.max_tokens == 1000
        assert config.temperature == 0.7
        assert config.top_p == 0.9
        assert config.capabilities == {"streaming", "tool_calling"}

    def test_model_config_empty_provider(self):
        """Test ModelConfig with empty provider."""
        with pytest.raises(ValidationError) as exc_info:
            ModelConfig(
                provider="",
                model="gpt-4",
            )
        assert "provider must not be empty" in str(exc_info.value)

    def test_model_config_temperature_bounds(self):
        """Test ModelConfig temperature validation bounds."""
        # Valid: 0.0
        config = ModelConfig(provider="openai", model="gpt-4", temperature=0.0)
        assert config.temperature == 0.0

        # Valid: 2.0
        config = ModelConfig(provider="openai", model="gpt-4", temperature=2.0)
        assert config.temperature == 2.0

        # Invalid: < 0
        with pytest.raises(ValidationError):
            ModelConfig(provider="openai", model="gpt-4", temperature=-0.1)

        # Invalid: > 2
        with pytest.raises(ValidationError):
            ModelConfig(provider="openai", model="gpt-4", temperature=2.1)

    def test_model_config_top_p_bounds(self):
        """Test ModelConfig top_p validation bounds."""
        # Valid: 0.0
        config = ModelConfig(provider="openai", model="gpt-4", top_p=0.0)
        assert config.top_p == 0.0

        # Valid: 1.0
        config = ModelConfig(provider="openai", model="gpt-4", top_p=1.0)
        assert config.top_p == 1.0

        # Invalid: < 0
        with pytest.raises(ValidationError):
            ModelConfig(provider="openai", model="gpt-4", top_p=-0.1)

        # Invalid: > 1
        with pytest.raises(ValidationError):
            ModelConfig(provider="openai", model="gpt-4", top_p=1.1)

    def test_model_config_default_capabilities(self):
        """Test ModelConfig default capabilities."""
        config = ModelConfig(provider="openai", model="gpt-4")
        assert config.capabilities == set()


class TestAgentConfig:
    """Tests for AgentConfig."""

    def test_agent_config_minimal(self):
        """Test AgentConfig with minimal required fields."""
        config = AgentConfig(
            providers={"openai": ProviderConfig(api_key="sk-test")},
            models={"default": ModelConfig(provider="openai", model="gpt-4")},
        )
        assert config.name == "agent"
        assert config.system_prompt == "You are a helpful assistant."
        assert config.default_model == "default"

    def test_agent_config_full(self):
        """Test AgentConfig with all fields."""
        config = AgentConfig(
            name="my_agent",
            system_prompt="Custom system prompt",
            providers={"openai": ProviderConfig(api_key="sk-test")},
            models={"gpt4": ModelConfig(provider="openai", model="gpt-4")},
            default_model="gpt4",
            max_history=50,
        )
        assert config.name == "my_agent"
        assert config.system_prompt == "Custom system prompt"
        assert config.default_model == "gpt4"
        assert config.max_history == 50

    def test_agent_config_missing_default_model(self):
        """Test AgentConfig with non-existent default_model."""
        with pytest.raises(ValidationError) as exc_info:
            AgentConfig(
                providers={"openai": ProviderConfig(api_key="sk-test")},
                models={"gpt4": ModelConfig(provider="openai", model="gpt-4")},
                default_model="nonexistent",
            )
        assert "not found in models" in str(exc_info.value)

    def test_agent_config_unknown_provider(self):
        """Test AgentConfig with model referencing unknown provider."""
        with pytest.raises(ValidationError) as exc_info:
            AgentConfig(
                providers={"openai": ProviderConfig(api_key="sk-test")},
                models={"default": ModelConfig(provider="unknown", model="gpt-4")},
            )
        assert "unknown provider" in str(exc_info.value)

    def test_agent_config_get_provider_config(self):
        """Test get_provider_config method."""
        config = AgentConfig(
            providers={"openai": ProviderConfig(api_key="sk-test")},
            models={"gpt4": ModelConfig(provider="openai", model="gpt-4")},
            default_model="gpt4",
        )

        provider_config = config.get_provider_config("gpt4")
        assert provider_config.api_key.get_secret_value() == "sk-test"

    def test_agent_config_get_provider_config_default(self):
        """Test get_provider_config with default model."""
        config = AgentConfig(
            providers={"openai": ProviderConfig(api_key="sk-test")},
            models={"gpt4": ModelConfig(provider="openai", model="gpt-4")},
            default_model="gpt4",
        )

        provider_config = config.get_provider_config()
        assert provider_config.api_key.get_secret_value() == "sk-test"

    def test_agent_config_get_provider_config_not_found(self):
        """Test get_provider_config with non-existent model."""
        config = AgentConfig(
            providers={"openai": ProviderConfig(api_key="sk-test")},
            models={"default": ModelConfig(provider="openai", model="gpt-4")},
        )

        with pytest.raises(ValueError, match="Model 'nonexistent' not found"):
            config.get_provider_config("nonexistent")

    def test_agent_config_get_model_config(self):
        """Test get_model_config method."""
        config = AgentConfig(
            providers={"openai": ProviderConfig(api_key="sk-test")},
            models={"gpt4": ModelConfig(provider="openai", model="gpt-4")},
            default_model="gpt4",
        )

        model_config = config.get_model_config("gpt4")
        assert model_config.model == "gpt-4"

    def test_agent_config_get_model_config_default(self):
        """Test get_model_config with default."""
        config = AgentConfig(
            providers={"openai": ProviderConfig(api_key="sk-test")},
            models={"gpt4": ModelConfig(provider="openai", model="gpt-4")},
            default_model="gpt4",
        )

        model_config = config.get_model_config()
        assert model_config.model == "gpt-4"

    def test_agent_config_get_model_config_not_found(self):
        """Test get_model_config with non-existent model."""
        config = AgentConfig(
            providers={"openai": ProviderConfig(api_key="sk-test")},
            models={"default": ModelConfig(provider="openai", model="gpt-4")},
        )

        with pytest.raises(ValueError, match="Model 'nonexistent' not found"):
            config.get_model_config("nonexistent")

    def test_agent_config_multiple_providers(self):
        """Test AgentConfig with multiple providers."""
        config = AgentConfig(
            providers={
                "openai": ProviderConfig(api_key="sk-openai"),
                "anthropic": ProviderConfig(
                    type="anthropic",
                    base_url="https://api.anthropic.com/v1",
                    api_key="sk-anthropic",
                ),
            },
            models={
                "default": ModelConfig(provider="openai", model="gpt-4"),
                "claude": ModelConfig(provider="anthropic", model="claude-3"),
            },
        )

        assert len(config.providers) == 2
        assert len(config.models) == 2

    def test_agent_config_max_history_validation(self):
        """Test max_history validation."""
        # Valid: min=1
        config = AgentConfig(
            providers={"openai": ProviderConfig(api_key="sk-test")},
            models={"default": ModelConfig(provider="openai", model="gpt-4")},
            max_history=1,
        )
        assert config.max_history == 1

        # Invalid: 0
        with pytest.raises(ValidationError):
            AgentConfig(
                providers={"openai": ProviderConfig(api_key="sk-test")},
                models={"default": ModelConfig(provider="openai", model="gpt-4")},
                max_history=0,
            )

        # Invalid: negative
        with pytest.raises(ValidationError):
            AgentConfig(
                providers={"openai": ProviderConfig(api_key="sk-test")},
                models={"default": ModelConfig(provider="openai", model="gpt-4")},
                max_history=-1,
            )
