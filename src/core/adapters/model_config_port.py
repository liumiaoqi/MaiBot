"""ModelConfigPort 适配器 — 委托 ConfigManager，实现智能体级配置合并。

适配器层是唯一允许导入 ConfigManager 具体类的地方。
"""

from __future__ import annotations

import copy
import logging
from typing import Callable, Optional, Sequence

from src.config.config import ConfigManager, ModelConfig
from src.config.model_configs import APIProvider, ModelInfo, ModelTaskConfig, TaskConfig

logger = logging.getLogger("core.adapters.model_config_port")


class ConfigManagerModelConfigPort:
    """ModelConfigPort 适配器。

    职责：
    1. 委托 ConfigManager 提供模型配置查询
    2. 实现智能体级 model_config_override 浅合并
    3. 热重载回调中继
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        agent_config_resolver: Callable[[str], Optional[object]],
    ) -> None:
        """初始化适配器。

        Args:
            config_manager: ConfigManager 实例
            agent_config_resolver: 根据 agent_id 解析 AgentConfig 的回调，
                                   返回 None 表示智能体不存在或无需覆盖
        """
        self._config_manager = config_manager
        self._agent_config_resolver = agent_config_resolver
        self._reload_callbacks: list[Callable] = []
        config_manager.register_reload_callback(self._on_config_reloaded)

    # ── 查询接口 ──────────────────────────────────────

    def get_task_config(self, task_name: str, *, agent_id: str = "") -> TaskConfig:
        """按任务名查询任务配置，支持智能体级覆盖。"""
        model_config = self._config_manager.get_model_config()
        task_cfg = self._resolve_task_config(model_config.model_task_config, task_name)

        if not agent_id:
            return copy.deepcopy(task_cfg)

        return self._apply_agent_override(task_cfg, task_name, agent_id)

    def get_model_info(self, model_name: str) -> ModelInfo:
        """按模型名查询模型信息。"""
        model_config = self._config_manager.get_model_config()
        for m in model_config.models:
            if m.name == model_name or m.model_identifier == model_name:
                return m
        raise ValueError(f"未找到名为 '{model_name}' 的模型")

    def get_provider(self, provider_name: str) -> APIProvider:
        """按提供商名查询提供商配置。"""
        model_config = self._config_manager.get_model_config()
        for p in model_config.api_providers:
            if p.name == provider_name:
                return p
        raise ValueError(f"未找到名为 '{provider_name}' 的提供商")

    def get_model_config(self) -> ModelConfig:
        """获取完整模型配置。"""
        return self._config_manager.get_model_config()

    # ── 热重载回调 ────────────────────────────────────

    def register_reload_callback(self, callback: object) -> None:
        """注册配置热重载回调。"""
        self._reload_callbacks.append(callback)

    def unregister_reload_callback(self, callback: object) -> None:
        """注销配置热重载回调。"""
        try:
            self._reload_callbacks.remove(callback)
        except ValueError:
            pass

    def _on_config_reloaded(self, changed_scopes: Sequence[str] = ()) -> None:
        """ConfigManager 热重载完成后调用，传播给消费者。"""
        for cb in list(self._reload_callbacks):
            try:
                try:
                    cb(changed_scopes)
                except TypeError:
                    cb()
            except Exception:
                logger.warning(
                    "配置热重载回调异常: callback=%s",
                    getattr(cb, "__name__", str(cb)),
                    exc_info=True,
                )

    # ── 智能体覆盖合并 ────────────────────────────────

    @staticmethod
    def _resolve_task_config(task_configs: ModelTaskConfig, task_name: str) -> TaskConfig:
        """从 ModelTaskConfig 容器中提取指定任务的配置。"""
        if not hasattr(task_configs, task_name):
            available = [
                attr for attr in dir(task_configs)
                if not attr.startswith("_") and isinstance(getattr(task_configs, attr, None), TaskConfig)
            ]
            raise ValueError(
                f"未找到名为 '{task_name}' 的任务配置，可用任务: {', '.join(available)}"
            )
        return getattr(task_configs, task_name)

    def _apply_agent_override(
        self,
        global_task_cfg: TaskConfig,
        task_name: str,
        agent_id: str,
    ) -> TaskConfig:
        """应用智能体级 model_config_override 到全局 TaskConfig。"""
        agent_cfg = self._agent_config_resolver(agent_id)
        if agent_cfg is None:
            return copy.deepcopy(global_task_cfg)

        override_raw = getattr(agent_cfg, "model_config_override", None)
        if override_raw is None or not isinstance(override_raw, dict):
            return copy.deepcopy(global_task_cfg)

        override = override_raw.get(task_name)
        if override is None or not isinstance(override, dict):
            return copy.deepcopy(global_task_cfg)

        merged = copy.deepcopy(global_task_cfg)

        for field_name, override_value in override.items():
            if not hasattr(merged, field_name):
                logger.warning(
                    "智能体 %s 的 model_config_override 中任务 %s 的字段 '%s' 不存在，已跳过",
                    agent_id, task_name, field_name,
                )
                continue

            existing_value = getattr(merged, field_name)
            expected_type = type(existing_value)
            if not isinstance(override_value, expected_type):
                logger.warning(
                    "智能体 %s 覆盖任务 %s 的 %s 类型不匹配(期望=%s, 实际=%s)，已跳过",
                    agent_id, task_name, field_name,
                    expected_type.__name__, type(override_value).__name__,
                )
                continue

            setattr(merged, field_name, override_value)

        # model_list 空保护
        if field_name == "model_list" and not isinstance(getattr(merged, "model_list", None), list):
            pass  # model_list 不在覆盖项中被跳过的情况由类型校验处理
        merged_model_list = getattr(merged, "model_list", None)
        if isinstance(merged_model_list, list) and not merged_model_list:
            global_model_list = getattr(global_task_cfg, "model_list", [])
            logging.warning(
                "智能体 %s 覆盖后任务 %s 的 model_list 为空，回退到全局配置",
                agent_id, task_name,
            )
            setattr(merged, "model_list", copy.deepcopy(global_model_list))

        return merged

    @classmethod
    def _available_task_names(cls, task_configs: ModelTaskConfig) -> list[str]:
        """获取 ModelTaskConfig 中可用的任务名列表。"""
        return [
            attr for attr in dir(task_configs)
            if not attr.startswith("_")
            and isinstance(getattr(task_configs, attr, None), TaskConfig)
        ]
