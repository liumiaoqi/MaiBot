"""ZG16-2 select_llm_context_messages 集成测试——双路径 + 灰度开关。

覆盖开关关闭行为不变（回归核心）、开关关闭仍输出统计日志、
开关打开按预算选择、开关切换中途异常 fallback、
token 预算路径异常降级、灰度日志格式、回归测试（条数模式 + 引用消息保留）。
"""


from datetime import datetime
from unittest.mock import MagicMock, patch

from src.llm_models.payload_content.tool_option import ToolCall
from src.maisaka.chat_loop_service import MaisakaChatLoopService
from src.maisaka.context.grayscale_log import format_grayscale_log
from src.maisaka.context.messages import (
    AssistantMessage,
    ReferenceMessage,
    ReferenceMessageType,
    ToolResultMessage,
)


def _make_assistant_message(text: str, *, tool_calls: list[ToolCall] | None = None) -> AssistantMessage:
    """构造 AssistantMessage。"""
    return AssistantMessage(
        content=text,
        timestamp=datetime.now(),
        tool_calls=tool_calls or [],
    )


def _make_reference_message(
    text: str,
    *,
    reference_type: ReferenceMessageType = ReferenceMessageType.CONTEXT_RESTORE,
) -> ReferenceMessage:
    """构造 ReferenceMessage（默认 CONTEXT_RESTORE 类型，始终保留）。"""
    return ReferenceMessage(content=text, timestamp=datetime.now(), reference_type=reference_type)


def _make_tool_result_message(text: str, *, tool_call_id: str = "tc1", tool_name: str = "tool1") -> ToolResultMessage:
    """构造 ToolResultMessage。"""
    return ToolResultMessage(
        content=text,
        timestamp=datetime.now(),
        tool_call_id=tool_call_id,
        tool_name=tool_name,
    )


def _make_chat_config_port(
    *,
    enable_token_budget: bool = False,
    max_context_size: int = 40,
    threshold_ratio: float = 0.8,
    retain_ratio: float = 0.16,
) -> MagicMock:
    """构造 mock ChatConfigPort。"""
    port = MagicMock()
    port.get_enable_token_budget.return_value = enable_token_budget
    port.get_max_context_size.return_value = max_context_size
    port.get_token_threshold_ratio.return_value = threshold_ratio
    port.get_token_retain_ratio.return_value = retain_ratio
    return port


# ════════════════════════════════════════════════════════════════════
# 开关关闭行为不变（回归核心）
# ════════════════════════════════════════════════════════════════════


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_switch_off_count_mode_behavior(mock_get_port, _mock_cw):
    """enable_token_budget=false → 选择结果按条数模式（effective = max(base, base×2)）。"""
    mock_get_port.return_value = _make_chat_config_port(enable_token_budget=False, max_context_size=3)
    msgs = [_make_assistant_message(f"msg{i}") for i in range(10)]
    selected, _ = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    # effective = max(3, int(3*2.0)) = 6 → 选中最近 6 条
    assert len(selected) == 6
    assert selected == msgs[4:10]


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_switch_off_2x_sawtooth_retained(mock_get_port, _mock_cw):
    """2× 锯齿保留：max_context_size=2 → effective=max(2, 4)=4。"""
    mock_get_port.return_value = _make_chat_config_port(enable_token_budget=False, max_context_size=2)
    msgs = [_make_assistant_message(f"msg{i}") for i in range(10)]
    selected, _ = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    assert len(selected) == 4
    assert selected == msgs[6:10]


# ════════════════════════════════════════════════════════════════════
# 开关关闭仍输出统计日志
# ════════════════════════════════════════════════════════════════════


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_switch_off_emits_grayscale_log(mock_get_port, _mock_cw):
    """enable_token_budget=false → selection_reason 含 token_est/overflow_ratio 字段。"""
    mock_get_port.return_value = _make_chat_config_port(enable_token_budget=False, max_context_size=5)
    msgs = [_make_assistant_message(f"msg{i}") for i in range(5)]
    _, reason = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    assert "token_est=" in reason
    assert "overflow_ratio=" in reason


# ════════════════════════════════════════════════════════════════════
# 开关打开按预算选择
# ════════════════════════════════════════════════════════════════════


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_switch_on_token_budget_mode(mock_get_port, _mock_cw):
    """enable_token_budget=true → 选择结果按 token 预算不再按条数。

    10 条消息每条 10000 token，budget_limit=52428，retain_budget=10485。
    token 预算选中 7 条（索引 3-9），条数模式（max_context_size=2, effective=4）选 4 条。
    """
    mock_get_port.return_value = _make_chat_config_port(
        enable_token_budget=True,
        max_context_size=2,
        threshold_ratio=0.8,
        retain_ratio=0.16,
    )
    # 每条 token = 10000 → text_len = (10000-8)*2 = 19984
    msgs = [_make_assistant_message("x" * 19984) for _ in range(10)]
    selected, reason = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    # token 预算选中 7 条（索引 3-9），而非条数模式的 4 条
    assert len(selected) == 7
    assert selected == msgs[3:10]
    assert "token预算" in reason


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_switch_on_and_off_produce_different_results(mock_get_port, _mock_cw):
    """开关打开与关闭产生不同选择结果（验证双路径确实分流）。"""
    mock_get_port.return_value = _make_chat_config_port(
        enable_token_budget=True,
        max_context_size=2,
        threshold_ratio=0.8,
        retain_ratio=0.16,
    )
    msgs = [_make_assistant_message("x" * 19984) for _ in range(10)]
    selected_on, _ = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )

    mock_get_port.return_value = _make_chat_config_port(
        enable_token_budget=False,
        max_context_size=2,
    )
    selected_off, _ = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    assert len(selected_on) != len(selected_off)
    assert selected_on != selected_off


# ════════════════════════════════════════════════════════════════════
# 开关切换中途异常 → fallback false
# ════════════════════════════════════════════════════════════════════


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_switch_read_exception_fallback_false(mock_get_port, _mock_cw):
    """读 enable_token_budget 异常 → fallback false（条数模式）。"""
    port = MagicMock()
    port.get_enable_token_budget.side_effect = RuntimeError("config port broken")
    port.get_max_context_size.return_value = 3
    mock_get_port.return_value = port
    msgs = [_make_assistant_message(f"msg{i}") for i in range(10)]
    selected, reason = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    # fallback 条数模式：effective=6，选中最近 6 条
    assert len(selected) == 6
    assert "token预算" not in reason


# ════════════════════════════════════════════════════════════════════
# token 预算路径异常 → 降级回条数模式
# ════════════════════════════════════════════════════════════════════


@patch("src.maisaka.chat_loop_service.select_by_token_budget", side_effect=RuntimeError("estimator crash"))
@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_token_budget_path_exception_degrades_to_count_mode(mock_get_port, _mock_cw, _mock_select):
    """估算器崩溃 mock → 降级回条数模式。"""
    mock_get_port.return_value = _make_chat_config_port(
        enable_token_budget=True,
        max_context_size=3,
    )
    msgs = [_make_assistant_message(f"msg{i}") for i in range(10)]
    selected, reason = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    # 降级条数模式：effective=6，选中最近 6 条
    assert len(selected) == 6
    # 降级后走条数模式，reason 不含 "token预算"
    assert "token预算" not in reason


# ════════════════════════════════════════════════════════════════════
# 灰度日志格式测试
# ════════════════════════════════════════════════════════════════════


def test_grayscale_log_fixed_fields():
    """format_grayscale_log 固定字段 + grep 可提取。"""
    log = format_grayscale_log(
        count_result=10,
        token_est=50000,
        usage_prompt=42000,
        overflow_ratio=0.763,
    )
    assert "条数=10" in log
    assert "token_est=50000" in log
    assert "usage_prompt=42000" in log
    assert "overflow_ratio=0.763" in log


def test_grayscale_log_usage_null_when_missing():
    """usage 缺失为 null。"""
    log = format_grayscale_log(
        count_result=5,
        token_est=30000,
        usage_prompt=None,
        overflow_ratio=0.458,
    )
    assert "usage_prompt=null" in log


def test_grayscale_log_overflow_ratio_formatted():
    """overflow_ratio 保留 3 位小数。"""
    log = format_grayscale_log(
        count_result=1,
        token_est=1,
        usage_prompt=None,
        overflow_ratio=0.123456,
    )
    assert "overflow_ratio=0.123" in log


# ════════════════════════════════════════════════════════════════════
# 回归测试：引用消息保留
# ════════════════════════════════════════════════════════════════════


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_reference_message_retained_in_count_mode(mock_get_port, _mock_cw):
    """条数模式：引用消息（CONTEXT_RESTORE）始终保留。"""
    mock_get_port.return_value = _make_chat_config_port(enable_token_budget=False, max_context_size=2)
    ref_msg = _make_reference_message("important context")
    msgs = [ref_msg] + [_make_assistant_message(f"msg{i}") for i in range(10)]
    selected, _ = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    # 引用消息始终保留
    assert ref_msg in selected


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_reference_message_retained_in_token_budget_mode(mock_get_port, _mock_cw):
    """token 预算模式：引用消息（CONTEXT_RESTORE）始终保留。"""
    mock_get_port.return_value = _make_chat_config_port(
        enable_token_budget=True,
        max_context_size=2,
        threshold_ratio=0.8,
        retain_ratio=0.16,
    )
    ref_msg = _make_reference_message("important context")
    # 构造大量消息使预算裁切
    msgs = [ref_msg] + [_make_assistant_message("x" * 19984) for _ in range(10)]
    selected, _ = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    assert ref_msg in selected


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_non_context_restore_reference_not_force_retained(mock_get_port, _mock_cw):
    """非 CONTEXT_RESTORE 类型引用消息不强制保留（不在 always_selected_indices 中）。

    CUSTOM 引用消息在头部，条数模式从后往前选达到 effective 后 break，
    头部 CUSTOM 消息不被处理 → 不选中（与 CONTEXT_RESTORE 的强制保留形成对比）。
    """
    mock_get_port.return_value = _make_chat_config_port(enable_token_budget=False, max_context_size=2)
    # CUSTOM 类型不被 _collect_always_selected_reference_indices 收集
    ref_msg = _make_reference_message("custom hint", reference_type=ReferenceMessageType.CUSTOM)
    msgs = [ref_msg] + [_make_assistant_message(f"msg{i}") for i in range(10)]
    selected, _ = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    # effective=4，从后往前选 4 条 count_in_context=True 后 break
    # 头部 CUSTOM 引用消息未被循环处理 → 不在 selected 中
    assert ref_msg not in selected
    assert len(selected) == 4


# ════════════════════════════════════════════════════════════════════
# 回归测试：工具配对修正
# ════════════════════════════════════════════════════════════════════


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_orphan_tool_result_dropped(mock_get_port, _mock_cw):
    """孤立 ToolResultMessage（无配对 tool_call）被 normalize_tool_call_result_pairs 移除。"""
    mock_get_port.return_value = _make_chat_config_port(enable_token_budget=False, max_context_size=5)
    tool_msg = _make_tool_result_message("tool result content")
    msgs = [_make_assistant_message(f"msg{i}") for i in range(5)] + [tool_msg]
    selected, _ = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    # 孤立 ToolResultMessage 无配对 tool_call → 被 drop_orphan_tool_results 移除
    assert tool_msg not in selected


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_tool_call_result_pair_preserved(mock_get_port, _mock_cw):
    """assistant tool_call + tool_result 配对保留。"""
    mock_get_port.return_value = _make_chat_config_port(enable_token_budget=False, max_context_size=5)
    tool_call = ToolCall(call_id="tc1", func_name="search", args={"q": "test"})
    assistant_with_tool = _make_assistant_message("calling tool", tool_calls=[tool_call])
    tool_result = _make_tool_result_message("search result", tool_call_id="tc1", tool_name="search")
    msgs = [_make_assistant_message(f"msg{i}") for i in range(3)] + [assistant_with_tool, tool_result]
    selected, _ = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    # 配对完整时两者都保留
    assert assistant_with_tool in selected
    assert tool_result in selected


# ════════════════════════════════════════════════════════════════════
# 回归测试：条数模式完全保留
# ════════════════════════════════════════════════════════════════════


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_count_mode_full_retention_within_budget(mock_get_port, _mock_cw):
    """条数模式：消息数 ≤ effective → 全部选中。"""
    mock_get_port.return_value = _make_chat_config_port(enable_token_budget=False, max_context_size=5)
    msgs = [_make_assistant_message(f"msg{i}") for i in range(3)]
    selected, _ = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    # effective=10 > 3 → 全部选中
    assert len(selected) == 3
    assert selected == msgs


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_count_mode_trims_from_head(mock_get_port, _mock_cw):
    """条数模式：超 effective → 从头部丢弃。"""
    mock_get_port.return_value = _make_chat_config_port(enable_token_budget=False, max_context_size=2)
    msgs = [_make_assistant_message(f"msg{i}") for i in range(10)]
    selected, _ = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    # effective=4 → 选中最近 4 条（索引 6-9）
    assert len(selected) == 4
    assert selected == msgs[6:10]


# ════════════════════════════════════════════════════════════════════
# P1-1: usage_prompt 参数接入灰度日志
# ════════════════════════════════════════════════════════════════════


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_usage_prompt_passed_to_grayscale_log_count_mode(mock_get_port, _mock_cw):
    """条数模式：usage_prompt=42000 → selection_reason 含 usage_prompt=42000。"""
    mock_get_port.return_value = _make_chat_config_port(enable_token_budget=False, max_context_size=5)
    msgs = [_make_assistant_message(f"msg{i}") for i in range(3)]
    _, reason = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
        usage_prompt=42000,
    )
    assert "usage_prompt=42000" in reason


# ════════════════════════════════════════════════════════════════════
# P1-1 拼余：普通场景（tool_definitions=None）usage_prompt 非 null
# ════════════════════════════════════════════════════════════════════


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_usage_prompt_non_null_with_dict_tools_baseline(mock_get_port, _mock_cw):
    """普通场景：baseline 用 dict 工具列表写入 → select 传入 usage_prompt 非 null → 日志含实际值。

    验证 P1-1 拼余修复：读/写端 tools 指纹一致（all_tools 提前计算）。
    """
    from src.maisaka.context.usage_anchor import usage_anchor

    usage_anchor.reset()
    model_name = "test_model"
    system_prompt = "你是一个助手"
    tools = [{"name": "tool1", "type": "function"}, {"name": "tool2", "type": "function"}]
    # 模拟写入端：上一次请求存入 baseline
    usage_anchor.update_baseline(model_name, system_prompt, tools, prompt_tokens=42000, estimated=40000)
    # 模拟读取端：同模型/同 system_prompt/同 tools → 取到 baseline
    baseline = usage_anchor.get_baseline(model_name, system_prompt, tools)
    assert baseline == 42000

    mock_get_port.return_value = _make_chat_config_port(enable_token_budget=False, max_context_size=5)
    msgs = [_make_assistant_message(f"msg{i}") for i in range(3)]
    _, reason = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
        usage_prompt=baseline,
    )
    assert "usage_prompt=42000" in reason
    usage_anchor.reset()


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_usage_prompt_none_default_count_mode(mock_get_port, _mock_cw):
    """条数模式：不传 usage_prompt → selection_reason 含 usage_prompt=null。"""
    mock_get_port.return_value = _make_chat_config_port(enable_token_budget=False, max_context_size=5)
    msgs = [_make_assistant_message(f"msg{i}") for i in range(3)]
    _, reason = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
    )
    assert "usage_prompt=null" in reason


@patch.object(MaisakaChatLoopService, "_resolve_context_window", return_value=65536)
@patch("src.maisaka.chat_loop_service.get_chat_config_port")
def test_usage_prompt_passed_to_grayscale_log_token_mode(mock_get_port, _mock_cw):
    """token 预算模式：usage_prompt=42000 → selection_reason 含 usage_prompt=42000。"""
    mock_get_port.return_value = _make_chat_config_port(enable_token_budget=True, max_context_size=5)
    msgs = [_make_assistant_message(f"msg{i}") for i in range(3)]
    _, reason = MaisakaChatLoopService.select_llm_context_messages(
        msgs,
        enable_visual_message=True,
        request_kind="planner",
        usage_prompt=42000,
    )
    assert "usage_prompt=42000" in reason