from argparse import ArgumentParser, Namespace
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
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
from src.services.llm_service import generate  # noqa: E402
from src.services.service_task_resolver import get_available_models  # noqa: E402


DEFAULT_SKIP_TASKS = {"embedding", "voice"}


@dataclass(slots=True)
class ProbeTarget:
    """单个待测试模型目标。"""

    task_name: str
    model_name: str
    provider_name: str
    client_type: str
    tool_argument_parse_mode: str


@dataclass(slots=True)
class ToolCallScenario:
    """工具调用 API 场景定义。"""

    name: str
    description: str
    prompt: List[Dict[str, Any]]
    tool_options: List[Dict[str, Any]] | None = None
    expect_tool_calls: bool | None = None


@dataclass(slots=True)
class ProbeResult:
    """单次 API 探测结果。"""

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
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    response_text: str = ""
    reasoning_text: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


def _ensure_utf8_console() -> None:
    """尽量将控制台编码切换为 UTF-8。"""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _build_function_tool(name: str, description: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """构造 OpenAI 风格 function tool。"""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


def _build_probe_tools() -> List[Dict[str, Any]]:
    """构造通用测试工具。"""
    weather_tool = _build_function_tool(
        name="lookup_weather",
        description="查询指定城市天气。",
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名"},
                "unit": {
                    "type": "string",
                    "description": "温度单位",
                    "enum": ["celsius", "fahrenheit"],
                },
                "include_forecast": {"type": "boolean", "description": "是否包含未来天气"},
            },
            "required": ["city", "unit", "include_forecast"],
            "additionalProperties": False,
        },
    )
    search_tool = _build_function_tool(
        name="search_docs",
        description="搜索内部知识库。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "top_k": {"type": "integer", "description": "返回条数"},
                "filters": {
                    "type": "object",
                    "description": "过滤条件",
                    "properties": {
                        "scope": {"type": "string", "description": "搜索范围"},
                        "tag": {"type": "string", "description": "标签"},
                    },
                    "required": ["scope", "tag"],
                    "additionalProperties": False,
                },
            },
            "required": ["query", "top_k", "filters"],
            "additionalProperties": False,
        },
    )
    return [weather_tool, search_tool]


def _build_default_scenarios() -> List[ToolCallScenario]:
    """构造默认测试场景。"""
    tools = _build_probe_tools()
    weather_tool = tools[0]
    search_tool = tools[1]

    history_tool_call = {
        "id": "call_hist_weather_001",
        "type": "function",
        "function": {
            "name": "lookup_weather",
            "arguments": {
                "city": "上海",
                "unit": "celsius",
                "include_forecast": True,
            },
        },
    }
    nested_history_tool_call = {
        "id": "call_hist_search_001",
        "type": "function",
        "function": {
            "name": "search_docs",
            "arguments": {
                "query": "工具调用兼容性",
                "top_k": 3,
                "filters": {
                    "scope": "internal",
                    "tag": "tool-call",
                },
            },
        },
    }

    return [
        ToolCallScenario(
            name="fresh_tool_call",
            description="首轮普通工具调用请求。",
            prompt=[
                {
                    "role": "system",
                    "content": (
                        "你正在执行工具调用连通性测试。"
                        "如果能调用工具，就优先调用最合适的工具。"
                    ),
                },
                {
                    "role": "user",
                    "content": "请查询上海天气，并使用工具给出参数。",
                },
            ],
            tool_options=[weather_tool],
            expect_tool_calls=True,
        ),
        ToolCallScenario(
            name="history_assistant_tool_calls_with_content",
            description="历史 assistant 同时包含文本和 tool_calls，当前轮不再提供 tools。",
            prompt=[
                {"role": "system", "content": "你正在执行多轮上下文兼容性测试。"},
                {"role": "user", "content": "先帮我查一下上海天气。"},
                {
                    "role": "assistant",
                    "content": "我先查询天气，再继续回答。",
                    "tool_calls": [history_tool_call],
                },
                {"role": "user", "content": "继续说，别丢掉上下文。"},
            ],
            tool_options=None,
            expect_tool_calls=None,
        ),
        ToolCallScenario(
            name="history_assistant_tool_calls_without_content",
            description="历史 assistant 只有 tool_calls，没有文本内容。",
            prompt=[
                {"role": "system", "content": "你正在执行多轮上下文兼容性测试。"},
                {"role": "user", "content": "先帮我查一下上海天气。"},
                {
                    "role": "assistant",
                    "tool_calls": [history_tool_call],
                },
                {"role": "user", "content": "继续。"},
            ],
            tool_options=None,
            expect_tool_calls=None,
        ),
        ToolCallScenario(
            name="history_tool_result_followup",
            description="历史中包含 assistant.tool_calls 与对应 tool 结果消息。",
            prompt=[
                {"role": "system", "content": "你正在执行工具调用闭环兼容性测试。"},
                {"role": "user", "content": "先查上海天气。"},
                {
                    "role": "assistant",
                    "content": "我先查询天气。",
                    "tool_calls": [history_tool_call],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_hist_weather_001",
                    "content": json.dumps(
                        {
                            "city": "上海",
                            "condition": "多云",
                            "temperature_c": 24,
                            "forecast": ["晴", "小雨"],
                        },
                        ensure_ascii=False,
                    ),
                },
                {"role": "user", "content": "结合上面的查询结果继续总结。"},
            ],
            tool_options=None,
            expect_tool_calls=None,
        ),
        ToolCallScenario(
            name="history_multiple_tool_calls_and_results",
            description="历史中包含多个 tool_calls 与多条 tool 结果。",
            prompt=[
                {"role": "system", "content": "你正在执行多工具上下文兼容性测试。"},
                {"role": "user", "content": "先查天气，再搜一下工具调用兼容性文档。"},
                {
                    "role": "assistant",
                    "content": "我分两步查询。",
                    "tool_calls": [history_tool_call, nested_history_tool_call],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_hist_weather_001",
                    "content": json.dumps(
                        {
                            "city": "上海",
                            "condition": "阴",
                            "temperature_c": 22,
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_hist_search_001",
                    "content": json.dumps(
                        {
                            "items": [
                                "OpenAI 兼容接口的 arguments 常见为 JSON 字符串",
                                "部分 provider 在历史消息回放时兼容性较弱",
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
                {"role": "user", "content": "继续整合上面的两个结果。"},
            ],
            tool_options=None,
            expect_tool_calls=None,
        ),
        ToolCallScenario(
            name="history_tool_calls_with_current_tools",
            description="保留历史 tool_calls，同时当前轮仍然提供 tools。",
            prompt=[
                {"role": "system", "content": "你正在执行历史 tool_calls 与当前 tools 共存测试。"},
                {"role": "user", "content": "先查上海天气。"},
                {
                    "role": "assistant",
                    "content": "我先查天气。",
                    "tool_calls": [history_tool_call],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_hist_weather_001",
                    "content": json.dumps(
                        {
                            "city": "上海",
                            "condition": "晴",
                            "temperature_c": 26,
                        },
                        ensure_ascii=False,
                    ),
                },
                {"role": "user", "content": "现在再搜一下工具调用兼容性文档。"},
            ],
            tool_options=[search_tool],
            expect_tool_calls=True,
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
    """构造模型名到模型配置的映射。"""
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
        raise ValueError("没有可用于工具调用 API 测试的任务，请显式通过 --task 指定")

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


def _serialize_tool_calls(tool_calls: Any) -> List[Dict[str, Any]]:
    """序列化返回中的工具调用。"""
    if not tool_calls:
        return []

    serialized_items: List[Dict[str, Any]] = []
    for tool_call in tool_calls:
        serialized_items.append(
            {
                "id": getattr(tool_call, "call_id", ""),
                "function": {
                    "name": getattr(tool_call, "func_name", ""),
                    "arguments": dict(getattr(tool_call, "args", {}) or {}),
                },
                **(
                    {"extra_content": dict(getattr(tool_call, "extra_content", {}) or {})}
                    if getattr(tool_call, "extra_content", None)
                    else {}
                ),
            }
        )
    return serialized_items


def _validate_service_result(service_result: LLMServiceResult, scenario: ToolCallScenario) -> tuple[List[str], List[str], List[Dict[str, Any]]]:
    """校验服务结果。"""
    errors: List[str] = []
    warnings: List[str] = []
    completion = service_result.completion
    serialized_tool_calls = _serialize_tool_calls(completion.tool_calls)

    if not service_result.success:
        errors.append(service_result.error or completion.response or "请求失败，但没有返回明确错误")
        return errors, warnings, serialized_tool_calls

    if scenario.expect_tool_calls is True and not serialized_tool_calls:
        warnings.append("本场景期望模型倾向于调用工具，但未返回 tool_calls")
    if scenario.expect_tool_calls is False and serialized_tool_calls:
        warnings.append("本场景未期望继续调用工具，但模型返回了 tool_calls")
    if completion.response.strip():
        warnings.append("模型返回了可见文本")
    return errors, warnings, serialized_tool_calls


async def _run_single_probe(
    target: ProbeTarget,
    scenario: ToolCallScenario,
    attempt: int,
    max_tokens: int,
    temperature: float,
) -> ProbeResult:
    """执行单次 API 探测。"""
    request = LLMServiceRequest(
        task_name=target.task_name,
        request_type=f"tool_call_api_matrix.{scenario.name}.attempt_{attempt}",
        prompt=scenario.prompt,
        tool_options=scenario.tool_options,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    started_at = time.perf_counter()
    with _pin_task_to_model(target.task_name, target.model_name):
        service_result = await generate(request)
    elapsed_seconds = time.perf_counter() - started_at

    errors, warnings, serialized_tool_calls = _validate_service_result(service_result, scenario)
    completion = service_result.completion
    return ProbeResult(
        task_name=target.task_name,
        target_model_name=target.model_name,
        actual_model_name=completion.model_name,
        provider_name=target.provider_name,
        client_type=target.client_type,
        tool_argument_parse_mode=target.tool_argument_parse_mode,
        case_name=scenario.name,
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


def _select_scenarios(case_filters: Sequence[str]) -> List[ToolCallScenario]:
    """按名称筛选测试场景。"""
    all_scenarios = {scenario.name: scenario for scenario in _build_default_scenarios()}
    if not case_filters:
        return list(all_scenarios.values())

    selected_scenarios: List[ToolCallScenario] = []
    for case_name in case_filters:
        if case_name not in all_scenarios:
            raise ValueError(
                f"未知测试场景 `{case_name}`，可选值: {', '.join(sorted(all_scenarios))}"
            )
        selected_scenarios.append(all_scenarios[case_name])
    return selected_scenarios


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

    selected_scenarios = _select_scenarios(case_filters)
    targets = _resolve_targets(task_filters, model_filters, args.fallback_task)

    _print_targets(targets)
    print("")

    results: List[ProbeResult] = []
    for target in targets:
        for attempt in range(1, args.repeat + 1):
            for scenario in selected_scenarios:
                print(
                    f"开始测试: model={target.model_name}, task={target.task_name}, "
                    f"case={scenario.name}, attempt={attempt}"
                )
                result = await _run_single_probe(
                    target=target,
                    scenario=scenario,
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
            "测试不同模型在多种工具调用消息形态下的 API 兼容性。\n"
            "重点覆盖历史 assistant.tool_calls、tool 结果消息、多工具调用等场景。"
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
        help="指定模型名，可重复传入，或使用逗号分隔多个值，例如 --model qwen3.5-35b-a3b",
    )
    parser.add_argument(
        "--case",
        action="append",
        help=(
            "指定测试场景名，可选值包括 "
            "fresh_tool_call、history_assistant_tool_calls_with_content、"
            "history_assistant_tool_calls_without_content、history_tool_result_followup、"
            "history_multiple_tool_calls_and_results、history_tool_calls_with_current_tools"
        ),
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="每个模型每个场景重复测试次数，默认 1",
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
        help="单次测试温度，默认 0.0，以尽量提高稳定性",
    )
    parser.add_argument(
        "--fallback-task",
        default="utils",
        help="当指定模型未被已选任务引用时，用于挂载该模型的任务名，默认 utils",
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
        help="打印模型返回的可见文本内容",
    )
    return parser


def main() -> int:
    """脚本入口。"""
    _ensure_utf8_console()
    config_manager.initialize()
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
