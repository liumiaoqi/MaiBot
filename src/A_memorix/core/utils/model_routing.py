"""A_Memorix 内部模型任务选择工具（ZG-12 能力化改造）。

旧任务名路由（NON_TEXT_GENERATION_TASK_NAMES / A_MEMORIX_TEXT_TASK_PRIORITY /
pick_text_generation_task）已废弃——统一走 ModelConfigPort.resolve_by_capability。

隔离说明：ResolutionOptions / TaskConfig 的字段通过 getattr 访问（见
model_config_port.py:_merge_options），故本地定义等价 dataclass 即可，
无需导入 src.llm_models / src.config。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Tuple

from src.common.logger import get_logger
from src.common.data_models.llm_service_data_models import LLMServiceResult
from src.core.model_config_port_registry import get_model_config_port


logger = get_logger("A_Memorix.ModelRouting")


@dataclass(frozen=True, slots=True)
class _ResolutionOptions:
    """本地等价 ResolutionOptions——字段通过 getattr 访问，无需导入 src.llm_models。"""

    prefer: tuple[tuple[str, str], ...] = ()
    temperature: float | None = None
    max_tokens: int | None = None
    selection_strategy: str = "balance"
    hard_timeout: float = 240.0
    slow_threshold: float = 15.0


@dataclass
class _CompatTaskConfig:
    """本地等价 TaskConfig——A_memorix 内部通过 getattr 访问字段。"""

    model_list: list[str] = field(default_factory=list)
    max_tokens: int = 0
    temperature: float = 0.0
    slow_threshold: float = 15.0
    selection_strategy: str = "balance"
    hard_timeout: float = 240.0


@dataclass(frozen=True)
class ResolvedLLMModel:
    """A_Memorix 内部使用的 LLM 选择结果。"""

    task_name: str
    task_config: Any
    selected_model_name: str = ""

    @property
    def is_single_model(self) -> bool:
        return bool(self.selected_model_name)


def resolve_text_generation_task(
    llm_api: Any,
    *,
    prefer: tuple[tuple[str, str], ...] = (),
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ResolvedLLMModel:
    """按 text_generation 能力解析 A_Memorix 的文本生成模型（ZG-12 主路径）。

    Args:
        llm_api: LLM 服务 API 模块（提供 resolve_by_capability / LLMServiceClient）。
        prefer: 偏好模型 (category, name) 元组序列。
        temperature / max_tokens: 调用点采样参数覆盖。

    Returns:
        ResolvedLLMModel：解析结果（task_name=模型名，兼容旧调用契约）。

    Raises:
        RuntimeError: ModelConfigPort 未注册或无可满足能力的模型时。
    """
    port = get_model_config_port()
    if port is None:
        raise RuntimeError("ModelConfigPort 未注册，无法解析文本生成模型")
    options = _ResolutionOptions(
        prefer=prefer,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    resolved = port.resolve_by_capability(("text_generation",), options=options)
    compat_task_config = _to_compat_task_config(resolved)
    return ResolvedLLMModel(
        task_name=resolved.name,
        task_config=compat_task_config,
        selected_model_name=resolved.name,
    )


def _to_compat_task_config(resolved: Any) -> Any:
    """ResolvedModel → TaskConfig 兼容格式（旧调用契约过渡期用）。"""
    return _CompatTaskConfig(
        model_list=[resolved.name],
        max_tokens=resolved.max_tokens,
        temperature=resolved.temperature,
        slow_threshold=resolved.slow_threshold,
        selection_strategy=resolved.selection_strategy,
        hard_timeout=resolved.hard_timeout,
    )


def task_has_model_list(task_config: Any) -> bool:
    """判断任务配置是否有可用模型候选。"""

    model_list = getattr(task_config, "model_list", [])
    return any(str(model_name).strip() for model_name in (model_list or []))


def get_text_generation_model_tasks(llm_api: Any, *, include_empty: bool = False) -> Dict[str, Any]:
    """获取 A_Memorix 可用的文本生成任务配置（deprecated，ZG-12 后统一走能力解析）。

    返回 {模型名: 兼容 TaskConfig}——保留旧调用方遍历契约。
    """
    del include_empty
    try:
        resolved = resolve_text_generation_task(llm_api)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "能力解析失败，返回空任务表", exception=exc)
        logger.warning(f"[A_Memorix.ModelRouting] 能力解析失败，返回空任务表: {exc}")
        return {}
    return {resolved.task_name: resolved.task_config}


def pick_text_generation_task(
    available_tasks: Dict[str, Any],
    preferred: Iterable[str] = (),
) -> Tuple[Optional[str], Optional[Any]]:
    """按优先级选择文本生成任务（deprecated——preferred 任务名语义已废弃）。

    保留旧签名：从 available_tasks（能力解析结果）中取首个可用项。
    """
    del preferred
    for task_name, task_config in available_tasks.items():
        if task_has_model_list(task_config):
            return task_name, task_config
    return None, None


def find_text_generation_task_for_model(
    available_tasks: Dict[str, Any],
    model_name: str,
) -> Tuple[Optional[str], Optional[Any]]:
    """按模型名查找其所属的文本生成任务。"""

    normalized_model_name = str(model_name or "").strip()
    if not normalized_model_name:
        return None, None
    for task_name, task_config in available_tasks.items():
        model_list = getattr(task_config, "model_list", []) or []
        task_models = [str(item).strip() for item in model_list if str(item).strip()]
        if normalized_model_name in task_models:
            return task_name, task_config
    return None, None


def build_single_model_task(model_name: str, template: Any) -> Any:
    """基于现有任务模板构造只包含单个文本生成模型的任务配置。"""

    return type(template)(
        model_list=[model_name],
        max_tokens=template.max_tokens,
        temperature=template.temperature,
        slow_threshold=template.slow_threshold,
        selection_strategy=template.selection_strategy,
        hard_timeout=template.hard_timeout,
    )


def resolve_text_generation_model_selector(
    available_tasks: Dict[str, Any],
    selector: str,
) -> Tuple[Optional[str], Optional[Any], str]:
    """解析任务名或具体模型名选择器。"""

    normalized_selector = str(selector or "").strip()
    if not normalized_selector or normalized_selector.lower() == "auto":
        return None, None, ""

    task_config = available_tasks.get(normalized_selector)
    if task_has_model_list(task_config):
        return normalized_selector, task_config, ""

    task_name, task_config = find_text_generation_task_for_model(available_tasks, normalized_selector)
    if task_name and task_config:
        return task_name, build_single_model_task(normalized_selector, task_config), normalized_selector
    return None, None, ""


async def generate_with_resolved_model(
    model: ResolvedLLMModel,
    request_type: str,
    prompt: str,
    llm_api: Any,
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> LLMServiceResult:
    """按 A_Memorix 解析出的模型执行文本生成。"""

    if not model.is_single_model:
        return await llm_api.generate(
            llm_api.LLMServiceRequest(
                task_name=model.task_name,
                request_type=request_type,
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )

    # P0-1 修复：task_name 在能力化后是模型名（非旧任务名）——
    # 构造 client 走 capabilities（task_name 仅作统计元数据）。
    client = llm_api.LLMServiceClient(
        task_name=model.task_name,
        request_type=request_type,
        capabilities=("text_generation",),
    )
    client._orchestrator.model_for_task = model.task_config
    client._orchestrator.model_usage = {model.selected_model_name: (0, 0, 0)}

    def _refresh_single_model_task() -> Any:
        client._orchestrator.model_for_task = model.task_config
        client._orchestrator.model_usage = {
            model.selected_model_name: client._orchestrator.model_usage.get(
                model.selected_model_name,
                (0, 0, 0),
            )
        }
        return model.task_config

    client._orchestrator._refresh_task_config = _refresh_single_model_task
    try:
        completion = await client.generate_response(
            prompt=prompt,
            options=llm_api.LLMGenerationOptions(
                temperature=temperature,
                max_tokens=max_tokens,
            ),
        )
        return llm_api.LLMServiceResult.from_response_result(completion)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "生成内容时出错", exception=exc)
        error_message = f"生成内容时出错: {exc}"
        logger.error(f"[A_Memorix.ModelRouting] {error_message}")
        return llm_api.LLMServiceResult.from_error(error_message, str(exc))


def resolve_default_text_generation_task(llm_api: Any) -> str:
    """解析默认文本生成任务，避免宿主默认值落到 embedding。"""

    available_tasks = get_text_generation_model_tasks(llm_api)
    task_name, _ = pick_text_generation_task(available_tasks)
    if not task_name:
        raise RuntimeError("没有可用的文本生成模型配置")
    return task_name


def resolve_text_generation_task_name_from_model_config(
    llm_api: Any,
    model_config: Any,
    *,
    preferred_task_name: str = "",
) -> str:
    """根据旧版 TaskConfig 对象解析文本生成任务名。"""

    available_tasks = get_text_generation_model_tasks(llm_api)
    if not available_tasks:
        raise RuntimeError("没有可用的文本生成模型配置")

    normalized_preferred = str(preferred_task_name or "").strip()
    if normalized_preferred and normalized_preferred in available_tasks:
        return normalized_preferred

    for task_name, task_config in available_tasks.items():
        if task_config is model_config:
            return task_name

    requested_model_list = [
        str(item).strip() for item in (getattr(model_config, "model_list", []) or []) if str(item).strip()
    ]
    if requested_model_list:
        for task_name, task_config in available_tasks.items():
            candidate_model_list = [
                str(item).strip() for item in (getattr(task_config, "model_list", []) or []) if str(item).strip()
            ]
            if requested_model_list == candidate_model_list:
                return task_name

        for requested_model in requested_model_list:
            task_name, _ = find_text_generation_task_for_model(available_tasks, requested_model)
            if task_name:
                logger.info(f"旧版文本生成 model_config 按模型 `{requested_model}` 近似映射到任务 `{task_name}`")
                return task_name

    fallback_task_name, _ = pick_text_generation_task(available_tasks)
    if fallback_task_name:
        if normalized_preferred:
            logger.warning(f"无法映射文本生成 model_config，回退默认任务: preferred={normalized_preferred}")
        return fallback_task_name
    raise RuntimeError("没有可用的文本生成模型配置")
