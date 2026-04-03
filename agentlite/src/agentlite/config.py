"""Configuration models for AgentLite.

This module provides Pydantic-based configuration models for providers,
models, and agent settings.
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, SecretStr, model_validator


ProviderType = Literal["openai", "anthropic", "google", "custom"]


ModelCapability = Literal[
    "streaming",
    "tool_calling",
    "vision",
    "json_mode",
    "function_calling",
]


class ProviderConfig(BaseModel):
    """Configuration for an LLM provider.

    Attributes:
        type: The provider type (openai, anthropic, etc.)
        base_url: The API base URL
        api_key: The API key (stored securely)
        headers: Additional headers to include in requests
        timeout: Request timeout in seconds

    Example:
        >>> config = ProviderConfig(
        ...     type="openai",
        ...     base_url="https://api.openai.com/v1",
        ...     api_key="sk-...",
        ... )
    """

    type: ProviderType = "openai"
    base_url: str = "https://api.openai.com/v1"
    api_key: SecretStr
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: float = 60.0

    @model_validator(mode="after")
    def validate_base_url(self) -> "ProviderConfig":
        """Validate that base_url is a valid URL."""
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return self


class ModelConfig(BaseModel):
    """Configuration for an LLM model.

    Attributes:
        provider: Name of the provider to use
        model: The model name/ID
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature
        top_p: Nucleus sampling parameter
        capabilities: Set of model capabilities

    Example:
        >>> config = ModelConfig(
        ...     provider="openai",
        ...     model="gpt-4",
        ...     temperature=0.7,
        ... )
    """

    provider: str
    model: str
    max_tokens: Optional[int] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    capabilities: set[ModelCapability] = Field(default_factory=set)

    @model_validator(mode="after")
    def validate_provider(self) -> "ModelConfig":
        """Validate provider is not empty."""
        if not self.provider:
            raise ValueError("provider must not be empty")
        return self


class ToolConfig(BaseModel):
    """Configuration for tool usage.

    Attributes:
        max_iterations: Maximum number of tool call iterations
        timeout: Timeout for tool execution in seconds
    """

    max_iterations: int = Field(default=80, ge=1, le=100)
    timeout: float = 60.0


class AgentConfig(BaseModel):
    """Complete configuration for an Agent.

    This combines provider, model, and behavior settings into a single
    configuration object.

    Attributes:
        name: Optional name for the agent
        system_prompt: The system prompt to use
        providers: Dictionary of provider configurations
        models: Dictionary of model configurations
        default_model: Name of the default model to use
        tools: Tool configuration
        max_history: Maximum number of messages to keep in history

    Example:
        >>> config = AgentConfig(
        ...     name="my_agent",
        ...     system_prompt="You are a helpful assistant.",
        ...     providers={
        ...         "openai": ProviderConfig(
        ...             type="openai",
        ...             api_key="sk-...",
        ...         )
        ...     },
        ...     models={
        ...         "gpt4": ModelConfig(
        ...             provider="openai",
        ...             model="gpt-4",
        ...         )
        ...     },
        ...     default_model="gpt4",
        ... )
    """

    name: str = "agent"
    system_prompt: str = "You are a helpful assistant."
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    models: dict[str, ModelConfig] = Field(default_factory=dict)
    default_model: str = "default"
    tools: ToolConfig = Field(default_factory=ToolConfig)
    max_history: int = Field(default=100, ge=1)

    @model_validator(mode="after")
    def validate_default_model(self) -> "AgentConfig":
        """Validate that default_model exists in models."""
        if self.default_model and self.default_model not in self.models:
            raise ValueError(f"default_model '{self.default_model}' not found in models")
        return self

    @model_validator(mode="after")
    def validate_model_providers(self) -> "AgentConfig":
        """Validate that all model providers exist."""
        for model_name, model_config in self.models.items():
            if model_config.provider not in self.providers:
                raise ValueError(
                    f"Model '{model_name}' references unknown provider '{model_config.provider}'"
                )
        return self

    def get_provider_config(self, model_name: Optional[str] = None) -> ProviderConfig:
        """Get the provider config for a model.

        Args:
            model_name: Name of the model. If None, uses default_model.

        Returns:
            The provider configuration for the model.

        Raises:
            ValueError: If the model or provider is not found.
        """
        model_name = model_name or self.default_model
        if model_name not in self.models:
            raise ValueError(f"Model '{model_name}' not found")

        model_config = self.models[model_name]
        if model_config.provider not in self.providers:
            raise ValueError(f"Provider '{model_config.provider}' not found")

        return self.providers[model_config.provider]

    def get_model_config(self, model_name: Optional[str] = None) -> ModelConfig:
        """Get the configuration for a model.

        Args:
            model_name: Name of the model. If None, uses default_model.

        Returns:
            The model configuration.

        Raises:
            ValueError: If the model is not found.
        """
        model_name = model_name or self.default_model
        if model_name not in self.models:
            raise ValueError(f"Model '{model_name}' not found")
        return self.models[model_name]
