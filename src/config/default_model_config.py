from typing import Any, TypeVar

from .config_base import ConfigBase
from .model_configs import APIProvider, ModelInfo, ModelTaskConfig, OpenAICompatibleAuthType, TaskConfig

T = TypeVar("T", bound=ConfigBase)

DEFAULT_PROVIDER_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "BaiLian",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "auth_type": OpenAICompatibleAuthType.NONE.value,
    }
]

DEFAULT_TASK_CONFIG_TEMPLATES: dict[str, dict[str, Any]] = {
    "utils": {
        "model_list": ["qwen3.5-35b-a3b-nonthink"],
        "max_tokens": 4096,
        "temperature": 0.5,
        "slow_threshold": 15.0,
        "selection_strategy": "random",
    },
    "replyer": {
        "model_list": ["ali-glm-5"],
        "max_tokens": 4096,
        "temperature": 1,
        "slow_threshold": 120.0,
        "selection_strategy": "random",
    },
    "planner": {
        "model_list": ["qwen3.5-35b-a3b", "qwen3.5-122b-a10b", "qwen3.5-flash"],
        "max_tokens": 8000,
        "temperature": 0.7,
        "slow_threshold": 12.0,
        "selection_strategy": "random",
    },
    "vlm": {
        "model_list": ["qwen3.5-flash"],
        "max_tokens": 512,
        "temperature": 0.3,
        "slow_threshold": 15.0,
        "selection_strategy": "random",
    },
    "voice": {
        "model_list": [""],
        "max_tokens": 1024,
        "temperature": 0.3,
        "slow_threshold": 12.0,
        "selection_strategy": "random",
    },
    "embedding": {
        "model_list": ["qwen3-embedding"],
        "max_tokens": 1024,
        "temperature": 0.3,
        "slow_threshold": 5.0,
        "selection_strategy": "random",
    },
}

DEFAULT_MODEL_TEMPLATES: list[dict[str, Any]] = [
    {
        "model_identifier": "glm-5",
        "name": "ali-glm-5",
        "api_provider": "BaiLian",
        "price_in": 3.0,
        "price_out": 14.0,
        "temperature": 1.0,
        "visual": False,
        "extra_params": {"enable_thinking": False},
    },
    {
        "model_identifier": "qwen3.5-122b-a10b",
        "name": "qwen3.5-122b-a10b",
        "api_provider": "BaiLian",
        "price_in": 0.8,
        "price_out": 6.4,
        "visual": True,
        "extra_params": {"enable_thinking": "false"},
    },
    {
        "model_identifier": "qwen3.5-35b-a3b",
        "name": "qwen3.5-35b-a3b",
        "api_provider": "BaiLian",
        "price_in": 0.4,
        "price_out": 3.2,
        "visual": True,
        "extra_params": {},
    },
    {
        "model_identifier": "qwen3.5-35b-a3b",
        "name": "qwen3.5-35b-a3b-nonthink",
        "api_provider": "BaiLian",
        "price_in": 0.4,
        "price_out": 3.2,
        "visual": True,
        "extra_params": {"enable_thinking": "false"},
    },
    {
        "model_identifier": "qwen3.5-flash",
        "name": "qwen3.5-flash",
        "api_provider": "BaiLian",
        "price_in": 0.2,
        "price_out": 2.0,
        "visual": True,
        "extra_params": {"enable_thinking": "false"},
    },
    {
        "model_identifier": "text-embedding-v4",
        "name": "qwen3-embedding",
        "api_provider": "BaiLian",
        "price_in": 0.5,
        "price_out": 0.5,
        "visual": False,
        "extra_params": {},
    }
]


def build_default_model_templates() -> list[dict[str, Any]]:
    """筛选任务分配中实际用到的模型模板。"""

    used_model_names = {
        model_name
        for task_template in DEFAULT_TASK_CONFIG_TEMPLATES.values()
        for model_name in task_template["model_list"]
    }
    return [model_template for model_template in DEFAULT_MODEL_TEMPLATES if model_template["name"] in used_model_names]


def create_default_model_config(config_class: type[T]) -> T:
    """根据预置模板创建可通过校验的默认模型配置。"""

    task_config_fields = {}
    for field_name, field_info in ModelTaskConfig.model_fields.items():
        if field_info.annotation is not TaskConfig:
            continue

        task_template = DEFAULT_TASK_CONFIG_TEMPLATES.get(field_name, {})
        task_config_fields[field_name] = TaskConfig(**task_template)

    return config_class(
        models=[ModelInfo(**model_template) for model_template in build_default_model_templates()],
        model_task_config=ModelTaskConfig(**task_config_fields),
        api_providers=[APIProvider(**provider_template) for provider_template in DEFAULT_PROVIDER_TEMPLATES],
    )
