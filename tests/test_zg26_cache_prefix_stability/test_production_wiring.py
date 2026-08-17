"""ZG-26 测试：生产路径接线验证（grep + import 确认改动点在生产代码中）。

chat_loop_service 已 revert（P1-1 修复），不再检查其 wiring。
orchestrator 是 favor_injection_text 的唯一生产构造点。
"""

import importlib
from pathlib import Path


def test_prompt_builder_has_cache_stability():
    """prompt_builder.py 包含 _is_cache_stability_enabled 调用。"""
    path = Path("src/maisaka/agent_autonomy/prompt_builder.py")
    content = path.read_text(encoding="utf-8")
    assert "_is_cache_stability_enabled" in content, "prompt_builder 缺少 _is_cache_stability_enabled"
    assert "cache_stability_enabled" in content, "prompt_builder 缺少 cache_stability_enabled 变量"


def test_thinking_organ_has_favor_injection():
    """thinking_organ.py 包含 favor_injection_text 引用和 '好感度：' 字符串。"""
    path = Path("src/maisaka/agent_autonomy/thinking_organ.py")
    content = path.read_text(encoding="utf-8")
    assert "favor_injection_text" in content, "thinking_organ 缺少 favor_injection_text"
    assert "好感度：" in content, "thinking_organ 缺少 '好感度：' 字符串"


def test_orchestrator_passes_favor():
    """orchestrator.py 在 ThinkContext 构造处传入 favor_injection_text。"""
    path = Path("src/maisaka/agent_autonomy/orchestrator.py")
    content = path.read_text(encoding="utf-8")
    assert "favor_injection_text=favor_injection_text" in content, "orchestrator 未传入 favor_injection_text"


def test_orchestrator_uses_top_level_import():
    """P0 回归：orchestrator.py 顶部用 app_config_port_registry 导入 get_app_config_port。"""
    path = Path("src/maisaka/agent_autonomy/orchestrator.py")
    content = path.read_text(encoding="utf-8")
    assert "from src.core.app_config_port_registry import get_app_config_port" in content, (
        "orchestrator.py 顶部应从 app_config_port_registry 导入 get_app_config_port"
    )
    assert "from src.core.adapters.app_config_port import get_app_config_port" not in content, (
        "orchestrator.py 不应含错误 import 路径 src.core.adapters.app_config_port"
    )


def test_orchestrator_uses_bot_config_port():
    """P1-2 回归：orchestrator.py 顶部导入 get_bot_config_port 用于真实用户参数。"""
    path = Path("src/maisaka/agent_autonomy/orchestrator.py")
    content = path.read_text(encoding="utf-8")
    assert "from src.core.bot_config_port_registry import get_bot_config_port" in content, (
        "orchestrator.py 顶部应导入 get_bot_config_port"
    )


def test_orchestrator_no_wrong_function_level_import():
    """P0 回归：orchestrator.py 不在函数内重复 import get_app_config_port。"""
    path = Path("src/maisaka/agent_autonomy/orchestrator.py")
    lines = path.read_text(encoding="utf-8").splitlines()
    wrong_imports = [
        i for i, line in enumerate(lines, 1)
        if "from src.core.adapters.app_config_port import" in line
    ]
    assert not wrong_imports, f"orchestrator.py 不应含错误 import，行号: {wrong_imports}"


def test_config_class_exists():
    """official_configs.py 包含 CachePrefixStabilityConfig 定义。"""
    path = Path("src/config/official_configs.py")
    content = path.read_text(encoding="utf-8")
    assert "class CachePrefixStabilityConfig" in content, "缺少 CachePrefixStabilityConfig 定义"


def test_config_field_in_global_config():
    """config.py 包含 cache_prefix_stability 字段。"""
    path = Path("src/config/config.py")
    content = path.read_text(encoding="utf-8")
    assert "cache_prefix_stability" in content, "GlobalConfig 缺少 cache_prefix_stability 字段"
    assert "CachePrefixStabilityConfig" in content, "config.py 缺少 CachePrefixStabilityConfig import"


def test_app_config_port_has_getter():
    """app_config_port.py 包含 is_cache_prefix_stability_enabled 实现。"""
    path = Path("src/core/adapters/app_config_port.py")
    content = path.read_text(encoding="utf-8")
    assert "is_cache_prefix_stability_enabled" in content, "app_config_port 缺少 getter"


def test_protocol_has_method_stub():
    """protocols.py 包含 is_cache_prefix_stability_enabled 方法桩。"""
    path = Path("src/core/protocols.py")
    content = path.read_text(encoding="utf-8")
    assert "is_cache_prefix_stability_enabled" in content, "Protocol 缺少方法桩"


def test_think_context_has_favor_field():
    """types.py ThinkContext 包含 favor_injection_text 字段。"""
    path = Path("src/core/types.py")
    content = path.read_text(encoding="utf-8")
    assert "favor_injection_text" in content, "ThinkContext 缺少 favor_injection_text 字段"


def test_imports_work():
    """所有改动模块可正常 import（无语法错误）。"""
    importlib.import_module("src.config.official_configs")
    importlib.import_module("src.core.types")
    importlib.import_module("src.core.protocols")
