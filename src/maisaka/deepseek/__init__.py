"""DeepSeek 深度优化模块。"""

from .audit import EvolutionTrigger, ParameterEvolutionAuditLog
from .batch_scheduler import BatchScheduler, BatchTask, BatchTaskType
from .budget import TokenBudgetAllocation, TokenBudgetManager
from .cost_tracker import CostTracker, CostRecord
from .evolution import ParameterEvolutionEngine
from .model_scheduler import ModelScheduler, ModelTier, get_model_scheduler
from .optimizer import ContextSegment, DeepSeekOptimizer, get_deepseek_optimizer
from .prefix_cache import PrefixCacheManager, PrefixLayer

# 域级单例（webui 层 + evolution 共用——状态跨请求存活）
_budget_manager = TokenBudgetManager()
_prefix_cache_manager = PrefixCacheManager()
_batch_scheduler = BatchScheduler()
_cost_tracker = CostTracker()

__all__ = [
    "BatchScheduler",
    "BatchTask",
    "BatchTaskType",
    "ContextSegment",
    "CostRecord",
    "CostTracker",
    "DeepSeekOptimizer",
    "EvolutionTrigger",
    "ModelScheduler",
    "ModelTier",
    "ParameterEvolutionAuditLog",
    "ParameterEvolutionEngine",
    "PrefixCacheManager",
    "PrefixLayer",
    "TokenBudgetAllocation",
    "TokenBudgetManager",
    "get_deepseek_optimizer",
    "get_model_scheduler",
]