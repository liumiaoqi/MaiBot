"""DeepSeek 长上下文注入策略优化器。

三级注入策略：
- full: 1M窗口全量注入完整对话历史+完整画像+跨聊原文+内部关系网全量
- adaptive: 按智能体级注入策略优先级截断
- lean: 128K窗口精简注入
"""

from __future__ import annotations

from src.common.logger import get_logger

from .budget import TokenBudgetManager

logger = get_logger("maisaka_deepseek_optimizer")

_FULL_STRATEGY_THRESHOLD = 900000
_LEAN_STRATEGY_THRESHOLD = 200000


class ContextSegment:
    """上下文段，包含内容和预估 Token 数。"""

    def __init__(self, name: str, content: str, estimated_tokens: int = 0) -> None:
        self.name = name
        self.content = content
        self.estimated_tokens = estimated_tokens or self._estimate_tokens(content)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """粗略估算 Token 数（中文约1.5字/token，英文约4字符/token）。"""
        cn_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        en_chars = len(text) - cn_chars
        return int(cn_chars / 1.5 + en_chars / 4)


class DeepSeekOptimizer:
    """DeepSeek 长上下文注入策略优化器。"""

    def __init__(self) -> None:
        self._budget_manager = TokenBudgetManager()

    def select_strategy(self, agent_id: str, model_context_window: int) -> str:
        """根据模型上下文窗口容量自动选择注入策略。"""
        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry()
            if registry.has_agent(agent_id):
                config = registry.get_agent(agent_id).deepseek
                if not config.enabled:
                    return "lean"
                return config.injection_strategy
        except Exception:
            pass

        if model_context_window >= _FULL_STRATEGY_THRESHOLD:
            return "full"
        if model_context_window >= _LEAN_STRATEGY_THRESHOLD:
            return "adaptive"
        return "lean"

    def optimize_injection(
        self,
        agent_id: str,
        segments: list[ContextSegment],
        model_context_window: int = 128000,
        reserved_output_tokens: int = 4096,
    ) -> list[ContextSegment]:
        """根据注入策略优化上下文段列表，返回截断后的段列表。"""
        strategy = self.select_strategy(agent_id, model_context_window)

        if strategy == "full":
            return self._full_injection(agent_id, segments, model_context_window, reserved_output_tokens)
        if strategy == "adaptive":
            return self._adaptive_injection(agent_id, segments, model_context_window, reserved_output_tokens)
        return self._lean_injection(agent_id, segments, model_context_window, reserved_output_tokens)

    def _full_injection(
        self,
        agent_id: str,
        segments: list[ContextSegment],
        model_context_window: int,
        reserved_output_tokens: int,
    ) -> list[ContextSegment]:
        """全量注入策略：1M窗口，注入所有段。"""
        budget = model_context_window - reserved_output_tokens
        total = sum(s.estimated_tokens for s in segments)
        if total <= budget:
            return segments

        logger.info(f"full策略: 总Token {total} 超出预算 {budget}，回退到adaptive")
        return self._adaptive_injection(agent_id, segments, model_context_window, reserved_output_tokens)

    def _adaptive_injection(
        self,
        agent_id: str,
        segments: list[ContextSegment],
        model_context_window: int,
        reserved_output_tokens: int,
    ) -> list[ContextSegment]:
        """自适应注入策略：按优先级截断低优先级段。"""
        budget = model_context_window - reserved_output_tokens
        allocation = self._budget_manager.get_budget(agent_id, model_context_window)

        priority_order = self._get_injection_priority(agent_id)

        segment_map = {s.name: s for s in segments}
        result: list[ContextSegment] = []
        remaining_budget = budget

        for segment_name in priority_order:
            segment = segment_map.get(segment_name)
            if segment is None:
                continue

            segment_budget = allocation.get_token_limit(segment_name, budget)
            if segment.estimated_tokens <= segment_budget and segment.estimated_tokens <= remaining_budget:
                result.append(segment)
                remaining_budget -= segment.estimated_tokens
            elif remaining_budget > 100:
                truncated = self._truncate_segment(segment, min(segment_budget, remaining_budget))
                result.append(truncated)
                remaining_budget -= truncated.estimated_tokens

        for segment in segments:
            if segment.name not in priority_order and segment.name not in {s.name for s in result}:
                if segment.estimated_tokens <= remaining_budget:
                    result.append(segment)
                    remaining_budget -= segment.estimated_tokens

        return result

    def _lean_injection(
        self,
        agent_id: str,
        segments: list[ContextSegment],
        model_context_window: int,
        reserved_output_tokens: int,
    ) -> list[ContextSegment]:
        """精简注入策略：128K窗口，仅注入核心段。"""
        budget = model_context_window - reserved_output_tokens
        allocation = self._budget_manager.get_budget(agent_id, model_context_window)

        core_segments = {"identity", "anti_mechanization", "emotion_state", "relationship", "history"}
        priority_order = self._get_injection_priority(agent_id)

        segment_map = {s.name: s for s in segments}
        result: list[ContextSegment] = []
        remaining_budget = budget

        ordered_names = [n for n in priority_order if n in core_segments]
        for segment_name in ordered_names:
            segment = segment_map.get(segment_name)
            if segment is None:
                continue

            segment_budget = allocation.get_token_limit(segment_name, budget)
            if segment.estimated_tokens <= segment_budget and segment.estimated_tokens <= remaining_budget:
                result.append(segment)
                remaining_budget -= segment.estimated_tokens
            elif remaining_budget > 100:
                truncated = self._truncate_segment(segment, min(segment_budget, remaining_budget))
                result.append(truncated)
                remaining_budget -= truncated.estimated_tokens

        return result

    @staticmethod
    def _get_injection_priority(agent_id: str) -> list[str]:
        """获取智能体的注入优先级。"""
        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry()
            if registry.has_agent(agent_id):
                return registry.get_agent(agent_id).deepseek.injection_priority
        except Exception:
            pass
        return ["identity", "anti_mechanization", "profile", "mid_term", "heuristic"]

    @staticmethod
    def _truncate_segment(segment: ContextSegment, max_tokens: int) -> ContextSegment:
        """截断段内容到指定 Token 上限。"""
        if max_tokens <= 0:
            return ContextSegment(name=segment.name, content="", estimated_tokens=0)

        char_limit = int(max_tokens * 1.5)
        truncated_content = segment.content[:char_limit]
        return ContextSegment(name=segment.name, content=truncated_content, estimated_tokens=max_tokens)