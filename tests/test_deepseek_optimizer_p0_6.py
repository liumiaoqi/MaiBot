"""P0-6 lean fallback 优先级补齐测试。

覆盖 spec 5.3.1-2~4 + adaptive 保底：
- fallback 交集覆盖全部 5 个核心段（identity/anti_mechanization/emotion_state/relationship/history）
- fallback 顺序语义（预算不足时高优先级先保留）
- 已配置 injection_priority 行为不变（快照）
- adaptive 非核心段保留
- 无配置 agent 走 fallback 不崩溃
"""

from types import SimpleNamespace
from unittest.mock import patch

from src.maisaka.deepseek.optimizer import ContextSegment, DeepSeekOptimizer

CORE_5 = ["identity", "anti_mechanization", "emotion_state", "relationship", "history"]
NON_CORE_3 = ["profile", "mid_term", "heuristic"]


def _seg(name: str, tokens: int = 10) -> ContextSegment:
    """构造指定名称/Token 数的上下文段。"""
    return ContextSegment(name=name, content=f"{name}:{'x' * max(1, tokens)}", estimated_tokens=tokens)


def _all_segments() -> list[ContextSegment]:
    """构造 5 核心段 + 3 非核心段的完整段列表。"""
    return [_seg(n) for n in CORE_5] + [_seg(n) for n in NON_CORE_3]


class TestLeanFallbackCoverage:
    """spec 5.3.1-2: fallback 交集覆盖全部 5 个核心段。"""

    @patch(
        "src.core.adapters.agent_config_port.get_agent_config_provider",
        side_effect=RuntimeError("config port unavailable"),
    )
    def test_fallback_covers_all_core_segments(self, _mock: object) -> None:
        """配置端口异常 → fallback 生效 → lean 注入结果含全部 5 个核心段。"""
        optimizer = DeepSeekOptimizer()
        result = optimizer._lean_injection("agent_a", _all_segments(), 10000, 0)
        result_names = {s.name for s in result}
        assert set(CORE_5) <= result_names, f"fallback 缺核心段: {set(CORE_5) - result_names}"

    @patch(
        "src.core.adapters.agent_config_port.get_agent_config_provider",
        return_value=SimpleNamespace(has_agent=lambda aid: False),
    )
    def test_agent_without_config_falls_back(self, mock_provider: object) -> None:
        """无配置 agent（has_agent=False）→ fallback 生效且不崩溃。"""
        optimizer = DeepSeekOptimizer()
        result = optimizer._lean_injection("nobody", _all_segments(), 10000, 0)
        result_names = {s.name for s in result}
        assert "identity" in result_names
        assert "emotion_state" in result_names


class TestFallbackOrder:
    """spec 5.3.1-3: 预算不足时按 fallback 次序保留高优先级段。"""

    @patch(
        "src.core.adapters.agent_config_port.get_agent_config_provider",
        side_effect=RuntimeError("config down"),
    )
    def test_budget_two_segments_keeps_first_two(self, mock_provider: object) -> None:
        """预算不足时按 fallback 次序保留高优先级段（身份/去机制化优先）。

        用超大 get_token_limit stub 排除截断分支，使段按整段预算逐段保留，
        预算仅容 2 段 → 保留 identity + anti_mechanization。
        """
        optimizer = DeepSeekOptimizer()
        with patch.object(
            optimizer._budget_manager, "get_budget",
            return_value=SimpleNamespace(get_token_limit=lambda name, budget: 10000),
        ):
            segments = [_seg(n, tokens=100) for n in CORE_5]
            result = optimizer._lean_injection("agent-x", segments, 250, 0)
        result_names = [s.name for s in result]
        assert result_names == ["identity", "anti_mechanization"]


class TestConfiguredAgentSnapshot:
    """spec 5.3.1-4: 已配置 injection_priority 的智能体行为不变。"""

    def test_configured_priority_kept(self) -> None:
        """有配置 agent → 按配置顺序注入（含非核心段自定义），与修复前一致。"""
        custom_priority = ["relationship", "history", "profile"]
        registry = SimpleNamespace(
            has_agent=lambda aid: True,
            get_agent=lambda aid: SimpleNamespace(
                deepseek=SimpleNamespace(injection_priority=custom_priority)
            ),
        )
        optimizer = DeepSeekOptimizer()
        with patch(
            "src.core.adapters.agent_config_port.get_agent_config_provider",
            return_value=registry,
        ):
            result = optimizer._lean_injection("cfg-agent", _all_segments(), 10000, 0)
        result_names = {s.name for s in result}
        # lean 只注入核心段：配置交集 {relationship, history} 全部命中
        assert result_names == {"relationship", "history"}
        # 非核心段 profile 不进入 lean（交集守门）
        assert "profile" not in result_names


class TestAdaptiveFallback:
    """adaptive 复用面：非核心段保底不被破坏。"""

    @patch(
        "src.core.adapters.agent_config_port.get_agent_config_provider",
        side_effect=RuntimeError("config down"),
    )
    def test_adaptive_keeps_non_core_tail(self, mock_provider: object) -> None:
        """fallback 场景 _adaptive_injection 结果仍含 profile 段。"""
        optimizer = DeepSeekOptimizer()
        result = optimizer._adaptive_injection("agent-a", _all_segments(), 10000, 0)
        result_names = {s.name for s in result}
        assert "profile" in result_names
        assert set(CORE_5) <= result_names