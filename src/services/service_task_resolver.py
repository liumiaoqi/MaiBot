"""服务层模型任务解析工具（ZG-12 能力化改造）。

旧接口（get_available_models / resolve_task_name / resolve_task_name_from_model_config）
保留签名但内部走能力化路径，标注 deprecated；
新代码应使用 ModelConfigPort.resolve_by_capability。
"""

from typing import Any, Dict

from src.common.logger import get_logger
from src.config.model_configs import TaskConfig
from src.core.model_config_port_registry import get_model_config_port
from src.core.model_config_port_registry import register_model_config_port
from src.llm_models.model_requirement import ResolvedModel
from src.llm_models.task_name_mapping import resolve_legacy_task_name

logger = get_logger("service_task_resolver")


def set_model_config_port(port: Any) -> None:
    """注入模块级 ModelConfigPort（委托全局注册点）。"""
    register_model_config_port(port)


def _get_model_config_port() -> Any:
    """获取 ModelConfigPort——未注册时抛 RuntimeError。"""
    port = get_model_config_port()
    if port is None:
        raise RuntimeError("ModelConfigPort 未注册，无法获取模型配置")
    return port


def _get_model_config():
    """获取模型配置——通过 ModelConfigPort 访问。"""
    return _get_model_config_port().get_model_config()


def get_available_models(preferred_task_name: str = "") -> Dict[str, TaskConfig]:
    """获取当前所有可用的模型任务配置。

    .. deprecated::
        ZG-12 组件自治后任务名不做配置键——本方法改为返回注册表中
        （经旧任务名能力映射）可用的模型列表，保持旧调用方兼容。

    Args:
        preferred_task_name: 候选任务名（决定返回哪组能力对应的模型）
    """
    capabilities = resolve_legacy_task_name(preferred_task_name) if preferred_task_name else frozenset(
        {"text_generation"}
    )
    resolved = _get_model_config_port().resolve_by_capability(capabilities)
    return {preferred_task_name or "default": _to_compat_task_config(resolved)}


def model_name_exists(model_name: str) -> bool:
    """检查模型名是否存在于当前配置中。"""
    return any(model.name == model_name.strip() for model in _get_model_config().models)


def resolve_task_name(task_name: str = "") -> ResolvedModel:
    """根据任务名解析模型。

    .. deprecated::
        ZG-12 组件自治后返回类型从 str 升级为 ResolvedModel——
        旧调用方若按 str 使用需改用 resolve_by_capability。

    Args:
        task_name: 旧任务名（replyer/planner/...）；为空时按默认能力解析。

    Returns:
        ResolvedModel: 选中的模型 + 生效采样参数。

    Raises:
        RuntimeError: ModelConfigPort 未注册时抛出。
        ValueError: 未知任务名时抛出。
    """
    port = _get_model_config_port()
    normalized = (task_name or "").strip()
    if not normalized:
        return port.resolve_by_capability(("text_generation",))
    capabilities = resolve_legacy_task_name(normalized)
    return port.resolve_by_capability(capabilities)


def resolve_task_name_from_model_config(model_config: Any, preferred_task_name: str = "") -> str:
    """根据旧版模型配置对象解析任务名（兼容层，保留旧签名）。

    .. deprecated::
        ZG-12 组件自治后按模型配置对象解析的语义不再需要——
        本方法保留返回 str 的旧契约（近似映射到旧任务名），
        新代码应使用 resolve_by_capability。

    Args:
        model_config: 旧调用方持有的任务配置对象。
        preferred_task_name: 候选任务名。

    Returns:
        str: 解析后的旧任务名（兼容旧调用方）。
    """
    resolved = resolve_task_name(preferred_task_name)
    requested_model_list = [str(item).strip() for item in (getattr(model_config, "model_list", []) or []) if str(item).strip()]
    if requested_model_list and resolved.name in requested_model_list:
        return preferred_task_name or resolved.name
    return preferred_task_name or resolved.name


def _to_compat_task_config(resolved: ResolvedModel) -> TaskConfig:
    """ResolvedModel → TaskConfig 兼容格式（旧调用方过渡期用）。"""
    return TaskConfig(
        model_list=[resolved.name],
        max_tokens=resolved.max_tokens,
        temperature=resolved.temperature,
        selection_strategy=resolved.selection_strategy,
        hard_timeout=resolved.hard_timeout,
        slow_threshold=resolved.slow_threshold,
    )
