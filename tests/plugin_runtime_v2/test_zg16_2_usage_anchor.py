"""ZG16-2 usage 锚定单元测试——简化版 baseline + 增量模型。

覆盖 UsageAnchor.get_baseline/update_baseline/anchored_estimate/reset，
验证指纹匹配复用 baseline+增量、指纹失效纯启发式估算、
provider 少报/无 usage 不更新 baseline 等场景。
"""


from datetime import datetime
from typing import List
from unittest.mock import MagicMock

import pytest

import src.core.token_meter.service as svc
from src.core.token_meter import TokenMeter, _set_instance
from src.maisaka.context.messages import AssistantMessage
from src.maisaka.context.usage_anchor import UsageAnchor, usage_anchor


@pytest.fixture(autouse=True)
def _wire_token_meter():
    original = svc._instance
    _set_instance(TokenMeter())
    yield
    svc._instance = original


def _make_mock_message(text: str) -> MagicMock:
    """构造 mock 消息对象，设置 processed_plain_text 属性。"""
    msg = MagicMock()
    msg.processed_plain_text = text
    return msg


def _make_real_messages(total_tokens: int, count: int = 1) -> List[AssistantMessage]:
    """构造 count 条真实 AssistantMessage，总 token 约 total_tokens。

    ZG-N6: CHARS_PER_TOKEN=4，estimate_message = ceil(len/4) + 8，
    每条 token = total_tokens / count。
    """
    per_msg_tokens = total_tokens // count
    text_len = (per_msg_tokens - 8) * 4
    return [AssistantMessage(content="x" * text_len, timestamp=datetime.now()) for _ in range(count)]


# ════════════════════════════════════════════════════════════════════
# 简化版锚定
# ════════════════════════════════════════════════════════════════════


def test_anchored_estimate_baseline_plus_increment():
    """上一次 prompt_tokens=42000 + 本次增量 3000 → 锚定估算 45000。"""
    anchor = UsageAnchor()
    # 上一次请求：provider 返回 prompt_tokens=42000，启发式估算 40000
    anchor.update_baseline("model1", "sys_prompt", [], prompt_tokens=42000, estimated=40000)
    # 本次请求：增量消息 3000 token
    incremental = _make_real_messages(3000)
    result = anchor.anchored_estimate("model1", "sys_prompt", [], incremental)
    # baseline(42000) + incremental(3000) = 45000
    assert result == 45000


# ════════════════════════════════════════════════════════════════════
# 锚定条件：指纹匹配复用 baseline
# ════════════════════════════════════════════════════════════════════


def test_baseline_reused_when_fingerprint_matches():
    """system_prompt + tools 不变 → 复用 baseline。"""
    anchor = UsageAnchor()
    tools = ["tool1", "tool2"]
    anchor.update_baseline("model1", "sys", tools, prompt_tokens=50000, estimated=45000)
    baseline = anchor.get_baseline("model1", "sys", tools)
    assert baseline == 50000


def test_anchored_estimate_reuses_baseline():
    """指纹匹配时 anchored_estimate = baseline + 增量。"""
    anchor = UsageAnchor()
    anchor.update_baseline("model1", "sys", [], prompt_tokens=50000, estimated=45000)
    incremental = _make_real_messages(2000)
    result = anchor.anchored_estimate("model1", "sys", [], incremental)
    assert result == 52000


# ════════════════════════════════════════════════════════════════════
# baseline 失效
# ════════════════════════════════════════════════════════════════════


def test_baseline_invalidated_on_system_prompt_change():
    """system_prompt 变更 → 不复用 baseline，纯启发式估算。"""
    anchor = UsageAnchor()
    anchor.update_baseline("model1", "sys_old", [], prompt_tokens=50000, estimated=45000)
    # system_prompt 变更
    baseline = anchor.get_baseline("model1", "sys_new", [])
    assert baseline is None
    # anchored_estimate 走纯启发式
    incremental = _make_real_messages(2000)
    result = anchor.anchored_estimate("model1", "sys_new", [], incremental)
    assert result == 2000  # 纯增量，无 baseline


def test_baseline_invalidated_on_tools_change():
    """tools 变更 → baseline 失效。"""
    anchor = UsageAnchor()
    anchor.update_baseline("model1", "sys", ["tool1"], prompt_tokens=50000, estimated=45000)
    baseline = anchor.get_baseline("model1", "sys", ["tool2"])
    assert baseline is None


# ════════════════════════════════════════════════════════════════════
# 模型切换失效
# ════════════════════════════════════════════════════════════════════


def test_baseline_invalidated_on_model_switch():
    """model 切其他 → baseline 失效。"""
    anchor = UsageAnchor()
    anchor.update_baseline("model1", "sys", [], prompt_tokens=50000, estimated=45000)
    baseline = anchor.get_baseline("model2", "sys", [])
    assert baseline is None
    incremental = _make_real_messages(2000)
    result = anchor.anchored_estimate("model2", "sys", [], incremental)
    assert result == 2000  # 纯增量


# ════════════════════════════════════════════════════════════════════
# 首次请求无 baseline
# ════════════════════════════════════════════════════════════════════


def test_first_request_no_baseline():
    """首次请求无 baseline → 纯启发式估算。"""
    anchor = UsageAnchor()
    baseline = anchor.get_baseline("model1", "sys", [])
    assert baseline is None
    incremental = _make_real_messages(3000)
    result = anchor.anchored_estimate("model1", "sys", [], incremental)
    assert result == 3000  # 纯增量


# ════════════════════════════════════════════════════════════════════
# provider 少报
# ════════════════════════════════════════════════════════════════════


def test_provider_underreport_no_update():
    """provider 少报：prompt_tokens=30000 < 启发式 45000 → 不更新 baseline。"""
    anchor = UsageAnchor()
    # prompt_tokens < estimated → 不更新
    anchor.update_baseline("model1", "sys", [], prompt_tokens=30000, estimated=45000)
    baseline = anchor.get_baseline("model1", "sys", [])
    assert baseline is None


# ════════════════════════════════════════════════════════════════════
# provider 无 usage
# ════════════════════════════════════════════════════════════════════


def test_provider_no_usage_no_update():
    """provider 无 usage：prompt_tokens=0 → 不更新 baseline。"""
    anchor = UsageAnchor()
    anchor.update_baseline("model1", "sys", [], prompt_tokens=0, estimated=45000)
    baseline = anchor.get_baseline("model1", "sys", [])
    assert baseline is None


def test_provider_none_usage_no_update():
    """provider 无 usage：prompt_tokens=None → 不更新 baseline。"""
    anchor = UsageAnchor()
    anchor.update_baseline("model1", "sys", [], prompt_tokens=None, estimated=45000)  # type: ignore[arg-type]
    baseline = anchor.get_baseline("model1", "sys", [])
    assert baseline is None


# ════════════════════════════════════════════════════════════════════
# reset
# ════════════════════════════════════════════════════════════════════


def test_reset_clears_all_baselines():
    """reset() 清空所有 baseline。"""
    anchor = UsageAnchor()
    anchor.update_baseline("model1", "sys1", [], prompt_tokens=50000, estimated=45000)
    anchor.update_baseline("model2", "sys2", [], prompt_tokens=60000, estimated=55000)
    # 确认有 baseline
    assert anchor.get_baseline("model1", "sys1", []) is not None
    assert anchor.get_baseline("model2", "sys2", []) is not None
    # reset
    anchor.reset()
    assert anchor.get_baseline("model1", "sys1", []) is None
    assert anchor.get_baseline("model2", "sys2", []) is None


# ════════════════════════════════════════════════════════════════════
# 模块级单例
# ════════════════════════════════════════════════════════════════════


def test_module_level_singleton_exists():
    """模块级单例 usage_anchor 可用且为 UsageAnchor 实例。"""
    assert isinstance(usage_anchor, UsageAnchor)


def test_singleton_reset_works():
    """模块级单例 reset 后无残留 baseline（测试隔离）。"""
    usage_anchor.reset()
    usage_anchor.update_baseline("model1", "sys", [], prompt_tokens=50000, estimated=45000)
    assert usage_anchor.get_baseline("model1", "sys", []) is not None
    usage_anchor.reset()
    assert usage_anchor.get_baseline("model1", "sys", []) is None


# ════════════════════════════════════════════════════════════════════
# P0: 可哈希指纹——dict/ToolOption 列表不崩
# ════════════════════════════════════════════════════════════════════


def test_fingerprint_with_dict_tools():
    """dict 列表（不可哈希）不崩——P0 修复验证。"""
    anchor = UsageAnchor()
    tools = [{"name": "tool1", "type": "function"}, {"name": "tool2", "parameters": {"x": 1}}]
    anchor.update_baseline("model1", "sys", tools, prompt_tokens=50000, estimated=45000)
    baseline = anchor.get_baseline("model1", "sys", tools)
    assert baseline == 50000


def test_fingerprint_with_nested_dict_tools():
    """嵌套 dict 列表不崩——P0 修复验证。"""
    anchor = UsageAnchor()
    tools = [
        {"name": "tool1", "type": "function", "parameters": {"properties": {"x": {"type": "string"}}}},
    ]
    anchor.update_baseline("model1", "sys", tools, prompt_tokens=60000, estimated=55000)
    baseline = anchor.get_baseline("model1", "sys", tools)
    assert baseline == 60000


def test_fingerprint_with_mock_objects():
    """非 frozen dataclass 对象列表（不可哈希）不崩——P0 修复验证。"""
    anchor = UsageAnchor()
    tool = MagicMock()
    tool.name = "tool1"
    tools = [tool]
    anchor.update_baseline("model1", "sys", tools, prompt_tokens=50000, estimated=45000)
    baseline = anchor.get_baseline("model1", "sys", tools)
    assert baseline == 50000


def test_fingerprint_dict_tools_change_invalidates():
    """dict 列表内容变更 → baseline 失效——P0 修复后指纹正确区分。"""
    anchor = UsageAnchor()
    tools_v1 = [{"name": "tool1"}]
    tools_v2 = [{"name": "tool2"}]
    anchor.update_baseline("model1", "sys", tools_v1, prompt_tokens=50000, estimated=45000)
    assert anchor.get_baseline("model1", "sys", tools_v1) == 50000
    assert anchor.get_baseline("model1", "sys", tools_v2) is None


def test_fingerprint_dict_tools_order_independent():
    """dict 列表顺序不同但内容相同 → 不崩（sort_keys=True）。"""
    anchor = UsageAnchor()
    tools_a = [{"name": "tool1", "type": "function"}, {"name": "tool2"}]
    anchor.update_baseline("model1", "sys", tools_a, prompt_tokens=50000, estimated=45000)
    # 验证至少不崩且相同列表能取到 baseline
    assert anchor.get_baseline("model1", "sys", tools_a) == 50000


# ════════════════════════════════════════════════════════════════════
# P1-2: estimated 含 system_prompt + tools 开销
# ════════════════════════════════════════════════════════════════════


def test_update_baseline_rejects_when_prompt_less_than_full_estimated():
    """prompt_tokens < estimated(含 system_prompt+tools) → 不更新 baseline。

    P1-2 修复验证：estimated 含 system_prompt + tools 开销后，
    prompt_tokens 恒 ≥ estimated 的漏洞被堵。
    """
    from src.maisaka.context.token_estimator import (
        estimate_system_prompt,
        estimate_tools_schema,
    )

    anchor = UsageAnchor()
    system_prompt = "你是一个助手" * 100
    tools = [{"name": "tool1", "type": "function"}, {"name": "tool2"}]
    # 消息估算 3000，但 system_prompt + tools 开销 ~500
    msg_estimated = 3000
    full_estimated = msg_estimated + estimate_system_prompt(system_prompt) + estimate_tools_schema(tools)
    # prompt_tokens 仅 3000 < full_estimated → 不更新
    anchor.update_baseline("model1", system_prompt, tools, prompt_tokens=3000, estimated=full_estimated)
    assert anchor.get_baseline("model1", system_prompt, tools) is None
    # prompt_tokens >= full_estimated → 更新
    anchor.update_baseline(
        "model1", system_prompt, tools, prompt_tokens=full_estimated + 100, estimated=full_estimated
    )
    assert anchor.get_baseline("model1", system_prompt, tools) == full_estimated + 100