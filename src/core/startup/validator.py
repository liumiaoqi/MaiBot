"""启动配置校验器。

在启动流程早期对关键配置进行前置完整性检查，
确保核心依赖就绪后再启动子系统。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.config import Config, ModelConfig

_AGENTS_DIR = Path("agents")


class StartupValidator:
    """启动配置前置校验。"""

    @staticmethod
    def validate(global_config: "Config", model_config: "ModelConfig") -> list[str]:
        """执行全部配置前置校验，返回失败项列表，空列表表示通过。"""
        failures: list[str] = []
        failures.extend(StartupValidator._validate_model_config(model_config))
        failures.extend(StartupValidator._validate_agent_config())
        return failures

    @staticmethod
    def _validate_model_config(model_config: "ModelConfig") -> list[str]:
        """校验模型配置完整性。"""
        failures: list[str] = []
        api_providers = model_config.api_providers
        models = model_config.models

        if not api_providers:
            failures.append("模型配置中未定义任何 API Provider")
            return failures

        if not models:
            failures.append("模型配置中未定义任何模型")

        if models:
            provider_names = {p.name for p in api_providers}
            for model in models:
                if not model.api_provider:
                    failures.append(
                        f"模型「{model.name}」未指定 api_provider"
                    )
                elif model.api_provider not in provider_names:
                    failures.append(
                        f"模型「{model.name}」引用的 API Provider「{model.api_provider}」未定义"
                    )

        return failures

    @staticmethod
    def _validate_agent_config() -> list[str]:
        """校验智能体配置完整性。"""
        failures: list[str] = []

        if not _AGENTS_DIR.exists():
            failures.append(f"智能体配置目录「{_AGENTS_DIR}」不存在")
            return failures

        if not _AGENTS_DIR.is_dir():
            failures.append(f"「{_AGENTS_DIR}」不是一个目录")
            return failures

        try:
            agent_dirs = [
                entry
                for entry in _AGENTS_DIR.iterdir()
                if entry.is_dir() and not entry.name.startswith("_")
            ]
        except OSError as e:
            failures.append(f"无法读取智能体配置目录「{_AGENTS_DIR}」: {e}")
            return failures

        if not agent_dirs:
            failures.append(
                f"智能体配置目录「{_AGENTS_DIR}」为空，没有找到智能体配置"
            )

        return failures
