"""Token 预算分配模型，管理各上下文注入段的 Token 占比。"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from src.common.logger import get_logger

logger = get_logger("maisaka_deepseek_budget")

_DEFAULT_ALLOCATIONS = {
    "identity": 0.10,
    "anti_mechanization": 0.03,
    "internal_relationships": 0.05,
    "emotion_state": 0.03,
    "relationship": 0.03,
    "profile": 0.10,
    "mid_term": 0.10,
    "heuristic": 0.06,
    "cross_chat": 0.05,
    "history": 0.35,
    "reserved": 0.10,
}

_AGENT_OVERRIDES: dict[str, dict[str, float]] = {
    "kiana": {"history": 0.40, "profile": 0.08, "emotion_state": 0.04},
    "fu_hua": {"profile": 0.15, "history": 0.30, "heuristic": 0.08},
    "silver_wolf": {"history": 0.38, "identity": 0.08},
    "himeko": {"history": 0.38, "profile": 0.12},
    "elysia": {"emotion_state": 0.05, "history": 0.35},
    "mei": {"profile": 0.12, "relationship": 0.04},
    "bronya": {"history": 0.38, "heuristic": 0.08},
    "seele": {"emotion_state": 0.04, "profile": 0.12},
    "veliona": {"history": 0.38, "relationship": 0.04},
    "columbina": {"identity": 0.08, "history": 0.35},
    "signora": {"history": 0.38, "anti_mechanization": 0.04},
    "tighnari": {"profile": 0.12, "heuristic": 0.08},
    "welt": {"history": 0.35, "cross_chat": 0.08},
}


class TokenBudgetAllocation(BaseModel):
    """Token 预算分配，各段占比之和必须等于 1.0。"""

    identity: float = Field(default=0.10, ge=0.01, le=0.50, description="人设注入占比")
    anti_mechanization: float = Field(default=0.03, ge=0.01, le=0.20, description="反机械化规则占比")
    internal_relationships: float = Field(default=0.05, ge=0.01, le=0.20, description="内部关系网占比")
    emotion_state: float = Field(default=0.03, ge=0.01, le=0.20, description="情绪状态占比")
    relationship: float = Field(default=0.03, ge=0.01, le=0.20, description="关系状态占比")
    profile: float = Field(default=0.10, ge=0.01, le=0.30, description="画像注入占比")
    mid_term: float = Field(default=0.10, ge=0.01, le=0.30, description="中期记忆占比")
    heuristic: float = Field(default=0.06, ge=0.01, le=0.20, description="启发式记忆占比")
    cross_chat: float = Field(default=0.05, ge=0.01, le=0.20, description="跨聊上下文占比")
    history: float = Field(default=0.35, ge=0.01, le=0.60, description="对话历史占比")
    reserved: float = Field(default=0.10, ge=0.01, le=0.30, description="预留占比")

    @model_validator(mode="after")
    def validate_allocation(self) -> "TokenBudgetAllocation":
        """校验各占比之和等于 1.0（容差 0.01）。"""
        total = (
            self.identity + self.anti_mechanization + self.internal_relationships
            + self.emotion_state + self.relationship + self.profile
            + self.mid_term + self.heuristic + self.cross_chat
            + self.history + self.reserved
        )
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Token预算分配之和为 {total:.4f}，必须等于 1.0")
        return self

    def get_token_limit(self, segment: str, total_budget: int) -> int:
        """计算指定段的 Token 上限。"""
        ratio = getattr(self, segment, None)
        if ratio is None:
            return 0
        return int(total_budget * ratio)


class TokenBudgetManager:
    """Token 预算管理器，按智能体维度提供预算分配。"""

    def __init__(self) -> None:
        self._cache: dict[str, TokenBudgetAllocation] = {}

    def get_budget(self, agent_id: str, model_context_window: int = 128000) -> TokenBudgetAllocation:
        """获取指定智能体的 Token 预算分配。"""
        if agent_id in self._cache:
            return self._cache[agent_id]

        overrides = _AGENT_OVERRIDES.get(agent_id, {})
        alloc_dict = {**_DEFAULT_ALLOCATIONS, **overrides}

        try:
            budget_ratio = 1.0
            try:
                from src.maisaka.agent.registry import AgentConfigRegistry

                registry = AgentConfigRegistry()
                if registry.has_agent(agent_id):
                    budget_ratio = registry.get_agent(agent_id).deepseek.token_budget_ratio
            except Exception:
                pass

            scaled = {k: v * budget_ratio for k, v in alloc_dict.items()}
            total = sum(scaled.values())
            normalized = {k: v / total for k, v in scaled.items()}

            allocation = TokenBudgetAllocation(**normalized)
        except Exception:
            logger.warning(f"Token预算分配失败: {agent_id}，使用默认分配")
            allocation = TokenBudgetAllocation()

        self._cache[agent_id] = allocation
        return allocation