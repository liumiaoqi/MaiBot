"""ModelConfigPort 适配器 — 委托 ConfigManager，实现智能体级配置合并。

适配器层是唯一允许导入 ConfigManager 具体类的地方。
"""


import copy
from src.common.logger import get_logger
from typing import Any, Callable, Optional, Sequence

from src.config.config import ConfigManager, ModelConfig
from src.config.model_configs import APIProvider, ModelInfo, ModelTaskConfig, TaskConfig
from src.llm_models.model_registry import ModelRegistry
from src.llm_models.model_requirement import (
    DEFAULT_SOURCE,
    OPTIONS_SOURCE,
    EffectiveResolution,
    ModelEntry,
    ResolutionOptions,
    ResolvedModel,
    get_all_declarations,
)
from src.llm_models.task_name_mapping import resolve_legacy_task_name

logger = get_logger("core.adapters.model_config_port")


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
        self._registry: ModelRegistry | None = None
        config_manager.register_reload_callback(self._on_config_reloaded)

    # ── 查询接口 ──────────────────────────────────────

    def get_task_config(self, task_name: str, *, agent_id: str = "") -> TaskConfig:
        """按任务名查询任务配置，支持智能体级覆盖。

        .. deprecated::
            ZG-12 组件自治后任务名不做配置键——本方法经
            resolve_legacy_task_name → resolve_by_capability 兼容。
        """
        logger.warning(
            "get_task_config 已弃用（ZG-12 组件自治），调用方应改用 "
            "resolve_by_capability；task_name=%s", task_name,
        )
        capabilities = resolve_legacy_task_name(task_name)
        resolved = self.resolve_by_capability(capabilities, agent_id=agent_id)
        return TaskConfig(
            model_list=[resolved.name],
            max_tokens=resolved.max_tokens,
            temperature=resolved.temperature,
            selection_strategy=resolved.selection_strategy,
            hard_timeout=resolved.hard_timeout,
            slow_threshold=resolved.slow_threshold,
        )

    # ── 能力化查询（ZG-12 主路径）───────────────────────────

    def resolve_by_capability(
        self,
        capabilities: list[str] | tuple[str, ...],
        *,
        agent_id: str = "",
        options: Any | None = None,
    ) -> ResolvedModel:
        """按能力需求解析模型 — 委托 ModelRegistry + 智能体覆盖 + 调用点 options。"""
        registry = self._build_registry()
        prefer = self._resolve_agent_prefer(capabilities, agent_id)
        merged_options = self._merge_options(prefer, options)
        return registry.query_by_capability(capabilities, prefer=merged_options.prefer, options=merged_options)

    def get_effective_config(self, component_name: str) -> EffectiveResolution:
        """查询组件的生效解析结果（含参数来源追踪）。"""
        registry = self._build_registry()
        declarations = get_all_declarations()
        declaration = declarations.get(component_name)
        if declaration is None:
            return EffectiveResolution(
                component_name=component_name,
                status="unknown",
            )
        try:
            resolved = registry.query_by_capability(
                declaration.capabilities,
                prefer=declaration.defaults.prefer if declaration.defaults else (),
            )
            status = "satisfied"
        except Exception as exc:
            from src.llm_models.model_requirement import DeclarationError
            if not isinstance(exc, DeclarationError):
                raise
            status = "fast_fail" if declaration.critical else "degraded"
            return EffectiveResolution(
                component_name=component_name,
                capabilities=declaration.capabilities,
                resolved_model=None,
                status=status,
                fallback_candidates=(),
            )
        param_sources = {
            "temperature": OPTIONS_SOURCE if (declaration.defaults and declaration.defaults.temperature is not None) else DEFAULT_SOURCE,
            "max_tokens": OPTIONS_SOURCE if (declaration.defaults and declaration.defaults.max_tokens is not None) else DEFAULT_SOURCE,
        }
        return EffectiveResolution(
            component_name=component_name,
            capabilities=declaration.capabilities,
            resolved_model=resolved,
            param_sources=param_sources,
            fallback_candidates=resolved.fallback_candidates,
            status=status,
        )

    def get_all_providers(self) -> list[APIProvider]:
        """列出全部已注册的 API provider。"""
        return list(self._config_manager.get_model_config().api_providers)

    def get_models_by_capability(self, capability: str) -> list[ModelInfo]:
        """按能力列出模型（供 WebUI 渲染/插件枚举）。"""
        registry = self._build_registry()
        entries = registry._capability_index.get(capability, [])  # noqa: SLF001 — 适配器层访问注册表内部
        names = {entry.name for entry in entries}
        return [m for m in self._config_manager.get_model_config().models if m.name in names]

    # ── 注册表构建 ──────────────────────────────────────────

    def _build_registry(self) -> ModelRegistry:
        """从 ModelConfig 构建 ModelRegistry（缓存，热重载时失效）。"""
        if self._registry is None:
            model_config = self._config_manager.get_model_config()
            registry = ModelRegistry()
            entries = [self._to_entry(m) for m in model_config.models]
            registry.build_index(list(model_config.api_providers), entries)
            self._registry = registry
        return self._registry

    @staticmethod
    def _to_entry(model_info: ModelInfo) -> ModelEntry:
        """ModelInfo → ModelEntry（能力 + 采样参数默认值）。"""
        extra_params = dict(model_info.extra_params or {})
        temperature = float(extra_params.pop("temperature", 0.3) or 0.3)
        max_tokens = int(extra_params.pop("max_tokens", 4096) or 4096)
        return ModelEntry(
            category=model_info.category or "llm",
            name=model_info.name,
            model_identifier=model_info.model_identifier,
            api_provider=model_info.api_provider,
            capabilities=frozenset(model_info.capabilities or set()),
            price_in=model_info.price_in,
            price_out=model_info.price_out,
            cache=model_info.cache,
            temperature=temperature,
            max_tokens=max_tokens,
            force_stream_mode=getattr(model_info, "force_stream_mode", False),
            extra_params=extra_params,
        )

    def _resolve_agent_prefer(
        self,
        capabilities: list[str] | tuple[str, ...],
        agent_id: str,
    ) -> tuple[tuple[str, str], ...]:
        """智能体 model_config_override 中匹配能力的模型列表 → prefer 元组。"""
        if not agent_id:
            return ()
        agent_cfg = self._agent_config_resolver(agent_id)
        if agent_cfg is None:
            return ()
        override_raw = getattr(agent_cfg, "model_config_override", None)
        if not isinstance(override_raw, dict):
            return ()
        preferred: list[tuple[str, str]] = []
        required = frozenset(capabilities)
        registry = self._build_registry()
        for task_override in override_raw.values():
            if not isinstance(task_override, dict):
                continue
            model_list = task_override.get("model_list")
            if not isinstance(model_list, list):
                continue
            for model_name in model_list:
                if not isinstance(model_name, str):
                    continue
                for entry in registry._model_index.values():  # noqa: SLF001
                    if entry.name == model_name and required.issubset(entry.capabilities):
                        preferred.append(entry.key)
                        break
        return tuple(dict.fromkeys(preferred))

    @staticmethod
    def _merge_options(
        prefer: tuple[tuple[str, str], ...],
        options: Any | None,
    ) -> ResolutionOptions:
        """合并智能体 prefer 与调用点 options。"""
        if options is None:
            return ResolutionOptions(prefer=prefer)
        merged_prefer = tuple(prefer) + tuple(getattr(options, "prefer", ()))
        return ResolutionOptions(
            prefer=merged_prefer,
            temperature=getattr(options, "temperature", None),
            max_tokens=getattr(options, "max_tokens", None),
            selection_strategy=getattr(options, "selection_strategy", "balance"),
            hard_timeout=getattr(options, "hard_timeout", 240.0),
            slow_threshold=getattr(options, "slow_threshold", 15.0),
        )

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
        """ConfigManager 热重载完成后调用，传播给消费者。

        ZG-12 热重载链（T26）：
        1. 重建注册表索引并 diff 出受影响组件（refresh_index）
        2. 通过 ServiceManager 精确重启受影响组件（不动其他组件）
        3. 传播给消费回调
        """
        scopes = tuple(changed_scopes or ("bot", "model"))
        affected: set[str] = set()
        if "model" in scopes:
            model_config = self._config_manager.get_model_config()
            providers = list(model_config.api_providers)
            entries = [self._to_entry(m) for m in model_config.models]
            if self._registry is not None:
                affected = self._registry.refresh_index(providers, entries)
            else:
                registry = ModelRegistry()
                registry.build_index(providers, entries)
                self._registry = registry
        else:
            self._registry = None  # 非模型 scope：整体失效（下次查询重建）
        self._schedule_affected_restart(affected)
        for cb in list(self._reload_callbacks):
            try:
                try:
                    cb(changed_scopes)
                except TypeError:
                    cb()
            except Exception:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning(
                    "配置热重载回调异常: callback=%s",
                    getattr(cb, "__name__", str(cb)),
                    exc_info=True,
                )

    # ── 热重载精确重启 ─────────────────────────────────

    @staticmethod
    def _resolve_component_id(component_name: str, known_ids: set[str]) -> str | None:
        """组件名（类名）→ ServiceManager 组件 ID（启动项名）映射。

        尝试驼峰 → snake 命名（ThinkingOrgan → thinking_organ）；
        匹配已知启动项名则返回，否则返回 None（跳过重启）。
        """
        import re

        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", component_name).lower()
        if snake in known_ids:
            return snake
        return None

    def _schedule_affected_restart(self, affected: set[str]) -> None:
        """通过 ServiceManager 精确重启受影响组件（异步调度，失败仅告警）。"""
        if not affected:
            return
        from src.core.service_manager_port_registry import get_service_manager_port

        sm_port = get_service_manager_port()
        if sm_port is None:
            logger.warning(
                "模型配置热重载影响组件 %s，但 ServiceManager 未注入，跳过精确重启",
                sorted(affected),
            )
            return
        try:
            states = sm_port.list_states()
            known_ids = {state.component_id for state in states} if states else set()
        except Exception:
            known_ids = set()
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "模型配置热重载影响组件 %s，但当前无运行中的事件循环，跳过精确重启",
                sorted(affected),
            )
            return
        for component_name in sorted(affected):
            component_id = self._resolve_component_id(component_name, known_ids)
            if component_id is None:
                logger.info(
                    "模型配置热重载影响声明 %s，无匹配启动项（声明与启动名未对齐，T28 迁移后生效）",
                    component_name,
                )
                continue
            try:
                loop.create_task(sm_port.restart(component_id))
                logger.info("模型配置热重载 → 精确重启组件: %s", component_id)
            except Exception as exc:
                logger.warning("模型配置热重载重启组件 %s 失败: %s", component_id, exc)

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
            from src.core.tainted_mask.mark import mark_taint
            from src.core.tainted_mask.taint_flag import TaintFlag

            mark_taint(TaintFlag.TAINT_CONFIG_OVERRIDE)

        # model_list 空保护
        if field_name == "model_list" and not isinstance(getattr(merged, "model_list", None), list):
            pass  # model_list 不在覆盖项中被跳过的情况由类型校验处理
        merged_model_list = getattr(merged, "model_list", None)
        if isinstance(merged_model_list, list) and not merged_model_list:
            global_model_list = getattr(global_task_cfg, "model_list", [])
            get_logger("model_config_port").warning(
                "智能体 %s 覆盖后任务 %s 的 model_list 为空，回退到全局配置",
                agent_id, task_name,
            )
            merged.model_list = copy.deepcopy(global_model_list)

        return merged

    @classmethod
    def _available_task_names(cls, task_configs: ModelTaskConfig) -> list[str]:
        """获取 ModelTaskConfig 中可用的任务名列表。"""
        return [
            attr for attr in dir(task_configs)
            if not attr.startswith("_")
            and isinstance(getattr(task_configs, attr, None), TaskConfig)
        ]

    def list_model_names(self) -> list[str]:
        from src.config.config import config_manager  # noqa: TID251 — 适配器层允许导入
        model_cfg = config_manager.get_model_config()
        return [model.name for model in model_cfg.models]
