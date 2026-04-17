from argparse import ArgumentParser, Namespace
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Sequence

import asyncio
import json
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.data_models.llm_service_data_models import LLMServiceRequest, LLMServiceResult  # noqa: E402
from src.config.config import config_manager  # noqa: E402
from src.config.model_configs import APIProvider, ModelInfo, TaskConfig  # noqa: E402
from src.llm_models.payload_content.tool_option import ToolCall  # noqa: E402
from src.services.llm_service import generate  # noqa: E402
from src.services.service_task_resolver import get_available_models  # noqa: E402


DEFAULT_SKIP_TASKS = {"embedding", "voice"}


@dataclass(slots=True)
class ToolCallCase:
    """Tool call 参数测试用例。"""

    name: str
    description: str
    tool_definition: Dict[str, Any]
    expected_arguments: Dict[str, Any]

    @property
    def tool_name(self) -> str:
        """返回工具名称。"""
        if self.tool_definition.get("type") == "function":
            function_definition = self.tool_definition.get("function", {})
            return str(function_definition.get("name", "") or "")
        return str(self.tool_definition.get("name", "") or "")

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """返回参数 Schema。"""
        if self.tool_definition.get("type") == "function":
            function_definition = self.tool_definition.get("function", {})
            parameters = function_definition.get("parameters", {})
            return parameters if isinstance(parameters, dict) else {}
        parameters = self.tool_definition.get("parameters", {})
        return parameters if isinstance(parameters, dict) else {}

    def build_messages(self) -> List[Dict[str, Any]]:
        """构造测试消息。"""
        expected_json = json.dumps(self.expected_arguments, ensure_ascii=False, indent=2)
        system_prompt = (
            "你正在执行严格的工具调用参数兼容性测试。"
            "你必须通过工具调用响应，不能输出自然语言，不能解释，不能补充额外字段。"
        )
        user_prompt = (
            f"请立刻调用工具 `{self.tool_name}`。\n"
            "参数必须与下面 JSON 完全一致，键名、值、布尔类型、整数类型、浮点数、数组顺序和对象结构都不能改变。\n"
            "不要输出任何解释文本，只返回工具调用。\n"
            f"{expected_json}"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]


@dataclass(slots=True)
class ProbeTarget:
    """单个待测试模型目标。"""

    task_name: str
    model_name: str
    provider_name: str
    client_type: str
    tool_argument_parse_mode: str


@dataclass(slots=True)
class ProbeResult:
    """单次测试结果。"""

    task_name: str
    target_model_name: str
    actual_model_name: str
    provider_name: str
    client_type: str
    tool_argument_parse_mode: str
    case_name: str
    attempt: int
    success: bool
    elapsed_seconds: float
    errors: List[str]
    warnings: List[str]
    response_text: str
    reasoning_text: str
    tool_calls: List[Dict[str, Any]]


def _ensure_utf8_console() -> None:
    """尽量将控制台编码切到 UTF-8。"""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _build_function_tool(name: str, description: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """构造 OpenAI 风格 function tool 定义。"""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


def _build_default_cases() -> List[ToolCallCase]:
    """构造默认测试用例。"""
    simple_expected_arguments = {
        "request_id": "probe-simple-001",
        "count": 7,
        "enabled": True,
        "mode": "strict",
        "ratio": 2.5,
    }
    simple_parameters = {
        "type": "object",
        "properties": {
            "request_id": {"type": "string", "description": "请求 ID"},
            "count": {"type": "integer", "description": "数量"},
            "enabled": {"type": "boolean", "description": "是否启用"},
            "mode": {
                "type": "string",
                "description": "模式",
                "enum": ["strict", "loose"],
            },
            "ratio": {"type": "number", "description": "比例"},
        },
        "required": ["request_id", "count", "enabled", "mode", "ratio"],
        "additionalProperties": False,
    }

    nested_expected_arguments = {
        "request_id": "probe-nested-001",
        "notify": False,
        "profile": {
            "channel": "stable",
            "priority": 2,
        },
        "tags": ["alpha", "beta", "gamma"],
        "items": [
            {"count": 2, "name": "apple"},
            {"count": 5, "name": "banana"},
        ],
    }
    nested_parameters = {
        "type": "object",
        "properties": {
            "request_id": {"type": "string", "description": "请求 ID"},
            "notify": {"type": "boolean", "description": "是否通知"},
            "profile": {
                "type": "object",
                "description": "配置对象",
                "properties": {
                    "channel": {"type": "string", "description": "渠道"},
                    "priority": {"type": "integer", "description": "优先级"},
                },
                "required": ["channel", "priority"],
                "additionalProperties": False,
            },
            "tags": {
                "type": "array",
                "description": "标签列表",
                "items": {"type": "string"},
            },
            "items": {
                "type": "array",
                "description": "条目列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer", "description": "数量"},
                        "name": {"type": "string", "description": "名称"},
                    },
                    "required": ["count", "name"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["request_id", "notify", "profile", "tags", "items"],
        "additionalProperties": False,
    }

    return [
        ToolCallCase(
            name="simple",
            description="标量参数类型校验",
            tool_definition=_build_function_tool(
                name="record_simple_probe",
                description="记录简单参数探测结果",
                parameters=simple_parameters,
            ),
            expected_arguments=simple_expected_arguments,
        ),
        ToolCallCase(
            name="nested",
            description="嵌套对象与数组参数校验",
            tool_definition=_build_function_tool(
                name="record_nested_probe",
                description="记录嵌套参数探测结果",
                parameters=nested_parameters,
            ),
            expected_arguments=nested_expected_arguments,
        ),
    ]


def _parse_multi_value_args(raw_values: Sequence[str] | None) -> List[str]:
    """解析命令行中的多值参数。"""
    parsed_values: List[str] = []
    for raw_value in raw_values or []:
        for item in str(raw_value).split(","):
            normalized_item = item.strip()
            if normalized_item:
                parsed_values.append(normalized_item)
    return parsed_values


def _build_model_map() -> Dict[str, ModelInfo]:
    """构造模型名称到模型配置的映射。"""
    return {model.name: model for model in config_manager.get_model_config().models}


def _build_provider_map() -> Dict[str, APIProvider]:
    """构造 Provider 名称到配置的映射。"""
    return {provider.name: provider for provider in config_manager.get_model_config().api_providers}


def _pick_default_task_name(task_names: Sequence[str]) -> str:
    """选择默认任务名。"""
    if "utils" in task_names:
        return "utils"
    if not task_names:
        raise ValueError("当前没有可用的任务配置")
    return str(task_names[0])


def _resolve_targets(task_filters: Sequence[str], model_filters: Sequence[str], fallback_task: str) -> List[ProbeTarget]:
    """根据命令行参数解析待测试目标。"""
    available_tasks = get_available_models()
    model_map = _build_model_map()
    provider_map = _build_provider_map()

    if not available_tasks:
        raise ValueError("未找到任何可用的模型任务配置")

    if task_filters:
        selected_task_names = []
        for task_name in task_filters:
            if task_name not in available_tasks:
                raise ValueError(f"未找到任务 `{task_name}`")
            selected_task_names.append(task_name)
    else:
        selected_task_names = [
            task_name
            for task_name in available_tasks
            if task_name not in DEFAULT_SKIP_TASKS
        ]

    if not selected_task_names:
        raise ValueError("没有可用于 tool call 测试的任务，请显式通过 --task 指定")

    default_task_name = fallback_task if fallback_task in available_tasks else _pick_default_task_name(selected_task_names)
    resolved_targets: List[ProbeTarget] = []
    seen_models: set[str] = set()

    if model_filters:
        model_names = list(model_filters)
    else:
        model_names = []
        for task_name in selected_task_names:
            task_config = available_tasks[task_name]
            for model_name in task_config.model_list:
                if model_name not in model_names:
                    model_names.append(model_name)

    for model_name in model_names:
        if model_name in seen_models:
            continue
        if model_name not in model_map:
            raise ValueError(f"未找到模型 `{model_name}`")

        target_task_name = ""
        for task_name in selected_task_names:
            if model_name in available_tasks[task_name].model_list:
                target_task_name = task_name
                break
        if not target_task_name:
            target_task_name = default_task_name

        model_info = model_map[model_name]
        provider_info = provider_map[model_info.api_provider]
        resolved_targets.append(
            ProbeTarget(
                task_name=target_task_name,
                model_name=model_name,
                provider_name=provider_info.name,
                client_type=provider_info.client_type,
                tool_argument_parse_mode=provider_info.tool_argument_parse_mode,
            )
        )
        seen_models.add(model_name)

    return resolved_targets


@contextmanager
def _pin_task_to_model(task_name: str, model_name: str) -> Iterator[None]:
    """临时将某个任务锁定到单模型。"""
    model_task_config = config_manager.get_model_config().model_task_config
    task_config = getattr(model_task_config, task_name, None)
    if not isinstance(task_config, TaskConfig):
        raise ValueError(f"未找到任务 `{task_name}` 对应的配置")

    original_model_list = list(task_config.model_list)
    original_selection_strategy = task_config.selection_strategy
    task_config.model_list = [model_name]
    task_config.selection_strategy = "balance"
    try:
        yield
    finally:
        task_config.model_list = original_model_list
        task_config.selection_strategy = original_selection_strategy


def _serialize_tool_calls(tool_calls: List[ToolCall] | None) -> List[Dict[str, Any]]:
    """序列化工具调用结果。"""
    if not tool_calls:
        return []
    return [
        {
            "id": tool_call.call_id,
            "function": {
                "name": tool_call.func_name,
                "arguments": dict(tool_call.args or {}),
            },
        }
        for tool_call in tool_calls
    ]


def _is_integer_value(value: Any) -> bool:
    """判断是否为整数类型且排除布尔值。"""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number_value(value: Any) -> bool:
    """判断是否为数值类型且排除布尔值。"""
    return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)


def _schema_type(schema: Dict[str, Any]) -> str:
    """解析 Schema 的类型。"""
    schema_type = str(schema.get("type", "") or "").strip()
    if schema_type:
        return schema_type
    if "properties" in schema or "required" in schema:
        return "object"
    return ""


def _validate_schema(schema: Dict[str, Any], actual_value: Any, path: str = "args") -> List[str]:
    """按简化 JSON Schema 校验工具参数。"""
    errors: List[str] = []
    schema_type = _schema_type(schema)

    if "enum" in schema and actual_value not in schema["enum"]:
        errors.append(f"{path} 枚举值不合法，期望属于 {schema['enum']}，实际为 {actual_value!r}")

    if schema_type == "string":
        if not isinstance(actual_value, str):
            errors.append(f"{path} 类型错误，期望 string，实际为 {type(actual_value).__name__}")
        return errors

    if schema_type == "integer":
        if not _is_integer_value(actual_value):
            errors.append(f"{path} 类型错误，期望 integer，实际为 {type(actual_value).__name__}")
        return errors

    if schema_type == "number":
        if not _is_number_value(actual_value):
            errors.append(f"{path} 类型错误，期望 number，实际为 {type(actual_value).__name__}")
        return errors

    if schema_type == "boolean":
        if not isinstance(actual_value, bool):
            errors.append(f"{path} 类型错误，期望 boolean，实际为 {type(actual_value).__name__}")
        return errors

    if schema_type == "array":
        if not isinstance(actual_value, list):
            errors.append(f"{path} 类型错误，期望 array，实际为 {type(actual_value).__name__}")
            return errors
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(actual_value):
                errors.extend(_validate_schema(item_schema, item, f"{path}[{index}]"))
        return errors

    if schema_type == "object":
        if not isinstance(actual_value, dict):
            errors.append(f"{path} 类型错误，期望 object，实际为 {type(actual_value).__name__}")
            return errors

        properties = schema.get("properties", {})
        required_fields = [str(item) for item in schema.get("required", [])]
        for required_field in required_fields:
            if required_field not in actual_value:
                errors.append(f"{path}.{required_field} 缺少必填字段")

        for field_name, field_value in actual_value.items():
            field_path = f"{path}.{field_name}"
            field_schema = properties.get(field_name)
            if isinstance(field_schema, dict):
                errors.extend(_validate_schema(field_schema, field_value, field_path))
                continue

            additional_properties = schema.get("additionalProperties", True)
            if additional_properties is False:
                errors.append(f"{field_path} 是未定义字段")
            elif isinstance(additional_properties, dict):
                errors.extend(_validate_schema(additional_properties, field_value, field_path))
        return errors

    return errors


def _compare_expected_values(expected_value: Any, actual_value: Any, path: str = "args") -> List[str]:
    """递归比较实际值与期望值是否完全一致。"""
    errors: List[str] = []

    if isinstance(expected_value, dict):
        if not isinstance(actual_value, dict):
            return [f"{path} 值不一致，期望 object，实际为 {type(actual_value).__name__}"]

        expected_keys = set(expected_value.keys())
        actual_keys = set(actual_value.keys())
        for missing_key in sorted(expected_keys - actual_keys):
            errors.append(f"{path}.{missing_key} 缺少期望字段")
        for extra_key in sorted(actual_keys - expected_keys):
            errors.append(f"{path}.{extra_key} 出现了额外字段")
        for shared_key in sorted(expected_keys & actual_keys):
            errors.extend(
                _compare_expected_values(
                    expected_value[shared_key],
                    actual_value[shared_key],
                    f"{path}.{shared_key}",
                )
            )
        return errors

    if isinstance(expected_value, list):
        if not isinstance(actual_value, list):
            return [f"{path} 值不一致，期望 array，实际为 {type(actual_value).__name__}"]

        if len(expected_value) != len(actual_value):
            errors.append(f"{path} 列表长度不一致，期望 {len(expected_value)}，实际 {len(actual_value)}")
        for index, (expected_item, actual_item) in enumerate(
            zip(expected_value, actual_value, strict=False)
        ):
            errors.extend(_compare_expected_values(expected_item, actual_item, f"{path}[{index}]"))
        return errors

    if isinstance(expected_value, bool):
        if not isinstance(actual_value, bool) or actual_value is not expected_value:
            errors.append(f"{path} 值不一致，期望 {expected_value!r}，实际 {actual_value!r}")
        return errors

    if _is_integer_value(expected_value):
        if not _is_integer_value(actual_value) or actual_value != expected_value:
            errors.append(f"{path} 值不一致，期望 {expected_value!r}，实际 {actual_value!r}")
        return errors

    if isinstance(expected_value, float):
        if not _is_number_value(actual_value) or float(actual_value) != expected_value:
            errors.append(f"{path} 值不一致，期望 {expected_value!r}，实际 {actual_value!r}")
        return errors

    if expected_value != actual_value:
        errors.append(f"{path} 值不一致，期望 {expected_value!r}，实际 {actual_value!r}")
    return errors


def _pick_tool_call(tool_calls: List[ToolCall], expected_tool_name: str) -> ToolCall:
    """优先选择同名工具调用，否则回退到第一条。"""
    for tool_call in tool_calls:
        if tool_call.func_name == expected_tool_name:
            return tool_call
    return tool_calls[0]


def _validate_service_result(
    service_result: LLMServiceResult,
    target: ProbeTarget,
    case: ToolCallCase,
) -> tuple[List[str], List[str], List[Dict[str, Any]]]:
    """校验服务层返回结果。"""
    errors: List[str] = []
    warnings: List[str] = []
    completion = service_result.completion
    serialized_tool_calls = _serialize_tool_calls(completion.tool_calls)

    if not service_result.success:
        errors.append(service_result.error or completion.response or "请求失败但未返回错误信息")
        return errors, warnings, serialized_tool_calls

    if completion.model_name and completion.model_name != target.model_name:
        errors.append(
            f"实际命中的模型为 `{completion.model_name}`，与目标模型 `{target.model_name}` 不一致"
        )

    tool_calls = completion.tool_calls or []
    if not tool_calls:
        errors.append("模型未返回 tool_calls")
        if completion.response.strip():
            warnings.append("模型返回了自然语言文本而不是工具调用")
        return errors, warnings, serialized_tool_calls

    if len(tool_calls) != 1:
        errors.append(f"返回了 {len(tool_calls)} 个 tool_calls，预期为 1 个")

    selected_tool_call = _pick_tool_call(tool_calls, case.tool_name)
    if selected_tool_call.func_name != case.tool_name:
        errors.append(
            f"工具名不一致，期望 `{case.tool_name}`，实际 `{selected_tool_call.func_name}`"
        )

    actual_arguments = selected_tool_call.args
    if not isinstance(actual_arguments, dict):
        errors.append("工具参数未被解析为对象")
        return errors, warnings, serialized_tool_calls

    errors.extend(_validate_schema(case.parameters_schema, actual_arguments))
    errors.extend(_compare_expected_values(case.expected_arguments, actual_arguments))

    if completion.response.strip():
        warnings.append("模型同时返回了自然语言文本")
    return errors, warnings, serialized_tool_calls


async def _run_single_probe(
    target: ProbeTarget,
    case: ToolCallCase,
    attempt: int,
    max_tokens: int,
    temperature: float,
) -> ProbeResult:
    """执行单次工具调用参数探测。"""
    request = LLMServiceRequest(
        task_name=target.task_name,
        request_type=f"tool_call_param_probe.{case.name}.attempt_{attempt}",
        prompt=case.build_messages(),
        tool_options=[case.tool_definition],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    started_at = time.perf_counter()
    with _pin_task_to_model(target.task_name, target.model_name):
        service_result = await generate(request)
    elapsed_seconds = time.perf_counter() - started_at

    errors, warnings, serialized_tool_calls = _validate_service_result(service_result, target, case)
    completion = service_result.completion
    return ProbeResult(
        task_name=target.task_name,
        target_model_name=target.model_name,
        actual_model_name=completion.model_name,
        provider_name=target.provider_name,
        client_type=target.client_type,
        tool_argument_parse_mode=target.tool_argument_parse_mode,
        case_name=case.name,
        attempt=attempt,
        success=not errors,
        elapsed_seconds=elapsed_seconds,
        errors=errors,
        warnings=warnings,
        response_text=completion.response,
        reasoning_text=completion.reasoning,
        tool_calls=serialized_tool_calls,
    )


def _print_targets(targets: Sequence[ProbeTarget]) -> None:
    """打印待测试目标。"""
    print("待测试目标：")
    for index, target in enumerate(targets, start=1):
        print(
            f"{index}. model={target.model_name} | task={target.task_name} | "
            f"provider={target.provider_name} | client={target.client_type} | "
            f"tool_argument_parse_mode={target.tool_argument_parse_mode}"
        )


def _print_available_targets() -> None:
    """打印当前可用任务与模型。"""
    available_tasks = get_available_models()
    model_map = _build_model_map()
    task_names = list(available_tasks.keys())

    print("当前可用任务：")
    for task_name in task_names:
        task_config = available_tasks[task_name]
        print(f"- {task_name}: {list(task_config.model_list)}")

    referenced_models = {
        model_name
        for task_config in available_tasks.values()
        for model_name in task_config.model_list
    }

    print("\n当前配置中的模型：")
    for model_name, model_info in model_map.items():
        referenced_mark = "已被任务引用" if model_name in referenced_models else "未被任务引用"
        print(
            f"- {model_name}: provider={model_info.api_provider}, "
            f"identifier={model_info.model_identifier}, {referenced_mark}"
        )


def _select_cases(case_filters: Sequence[str]) -> List[ToolCallCase]:
    """根据参数筛选测试用例。"""
    all_cases = {case.name: case for case in _build_default_cases()}
    if not case_filters:
        return list(all_cases.values())

    selected_cases: List[ToolCallCase] = []
    for case_name in case_filters:
        if case_name not in all_cases:
            raise ValueError(f"未知测试用例 `{case_name}`，可选值: {', '.join(sorted(all_cases))}")
        selected_cases.append(all_cases[case_name])
    return selected_cases


def _print_single_result(result: ProbeResult, show_response: bool) -> None:
    """打印单次结果。"""
    status_text = "PASS" if result.success else "FAIL"
    print(
        f"[{status_text}] model={result.target_model_name} | task={result.task_name} | "
        f"case={result.case_name} | attempt={result.attempt} | elapsed={result.elapsed_seconds:.2f}s"
    )
    if result.errors:
        for error in result.errors:
            print(f"  ERROR: {error}")
    if result.warnings:
        for warning in result.warnings:
            print(f"  WARN: {warning}")
    if result.tool_calls:
        print(f"  tool_calls: {json.dumps(result.tool_calls, ensure_ascii=False)}")
    if show_response and result.response_text.strip():
        print(f"  response: {result.response_text}")


def _build_summary(results: Sequence[ProbeResult]) -> Dict[str, Any]:
    """构造结果摘要。"""
    total_count = len(results)
    passed_count = sum(1 for result in results if result.success)
    failed_count = total_count - passed_count
    failed_items = [
        {
            "model_name": result.target_model_name,
            "case_name": result.case_name,
            "attempt": result.attempt,
            "errors": list(result.errors),
        }
        for result in results
        if not result.success
    ]
    return {
        "total": total_count,
        "passed": passed_count,
        "failed": failed_count,
        "failed_items": failed_items,
    }


def _write_json_report(json_out: str, results: Sequence[ProbeResult]) -> None:
    """将测试结果写入 JSON 文件。"""
    output_path = Path(json_out).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": _build_summary(results),
        "results": [asdict(result) for result in results],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入: {output_path}")


async def _run_probes(args: Namespace) -> List[ProbeResult]:
    """执行所有探测请求。"""
    task_filters = _parse_multi_value_args(args.task)
    model_filters = _parse_multi_value_args(args.model)
    case_filters = _parse_multi_value_args(args.case)

    selected_cases = _select_cases(case_filters)
    targets = _resolve_targets(task_filters, model_filters, args.fallback_task)

    _print_targets(targets)
    print("")

    results: List[ProbeResult] = []
    for target in targets:
        for attempt in range(1, args.repeat + 1):
            for case in selected_cases:
                print(
                    f"开始测试: model={target.model_name}, task={target.task_name}, "
                    f"case={case.name}, attempt={attempt}"
                )
                result = await _run_single_probe(
                    target=target,
                    case=case,
                    attempt=attempt,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                )
                _print_single_result(result, args.show_response)
                print("")
                results.append(result)
    return results


def _build_parser() -> ArgumentParser:
    """构造命令行参数解析器。"""
    parser = ArgumentParser(
        description=(
            "测试 config/model_config.toml 中不同模型的 tool call 参数兼容性。\n"
            "默认会测试所有非 voice / embedding 任务中引用到的模型。"
        )
    )
    parser.add_argument(
        "--task",
        action="append",
        help="指定任务名，可重复传入，或使用逗号分隔多个值，例如 --task utils --task planner",
    )
    parser.add_argument(
        "--model",
        action="append",
        help="指定模型名，可重复传入，或使用逗号分隔多个值，例如 --model qwen3.6-plus",
    )
    parser.add_argument(
        "--case",
        action="append",
        help="指定测试用例名，可选 simple、nested；不传则运行全部默认用例",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="每个模型每个用例重复测试次数，默认 1",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=512,
        help="单次测试的最大输出 token 数，默认 512",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="单次测试温度，默认 0.0 以尽量提高稳定性",
    )
    parser.add_argument(
        "--fallback-task",
        default="utils",
        help="当指定模型未被任何已选任务引用时，用于挂载该模型的任务名，默认 utils",
    )
    parser.add_argument(
        "--json-out",
        help="可选，将结果写入指定 JSON 文件",
    )
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help="仅打印当前任务与模型映射，不发起网络请求",
    )
    parser.add_argument(
        "--show-response",
        action="store_true",
        help="打印模型返回的自然语言文本内容",
    )
    return parser


def main() -> int:
    """脚本入口。"""
    _ensure_utf8_console()
    parser = _build_parser()
    args = parser.parse_args()

    if args.repeat < 1:
        parser.error("--repeat 必须大于等于 1")
    if args.max_tokens < 1:
        parser.error("--max-tokens 必须大于等于 1")

    if args.list_targets:
        _print_available_targets()
        return 0

    results = asyncio.run(_run_probes(args))
    summary = _build_summary(results)

    print("测试摘要：")
    print(
        f"total={summary['total']} | passed={summary['passed']} | failed={summary['failed']}"
    )
    if summary["failed_items"]:
        print("失败明细：")
        for failed_item in summary["failed_items"]:
            print(
                f"- model={failed_item['model_name']} | case={failed_item['case_name']} | "
                f"attempt={failed_item['attempt']} | errors={failed_item['errors']}"
            )

    if args.json_out:
        _write_json_report(args.json_out, results)

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
