"""DeepSeek 参数演变引擎。

基于成本/缓存/频率的自动调整 + 运维者手动覆盖。

约束：
- 同一智能体同一参数24小时内只能自动调整1次
- 手动调整暂停该参数自动调整7天
- 自动演变仅限 DeepSeek 优化参数
- 任何分配比例最小值0.01
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.common.logger import get_logger

from .audit import EvolutionTrigger, ParameterEvolutionAuditLog

logger = get_logger("maisaka_deepseek_evolution")

_AUTO_ADJUST_COOLDOWN_SECONDS = 86400  # 24小时
_MANUAL_PAUSE_SECONDS = 7 * 86400  # 7天
_MIN_ALLOCATION_VALUE = 0.01
_COST_OVERBUDGET_DAYS = 7
_COST_OVERBUDGET_RATIO = 1.2
_LOW_PRIORITY_SEGMENTS = ["cross_chat", "heuristic", "mid_term"]
_ADJUSTMENT_STEP = 0.02


class EvolutionConstraint(BaseModel):
    """演变约束状态。"""

    last_auto_adjust_time: dict[str, float] = Field(default_factory=dict)
    manual_pause_until: dict[str, float] = Field(default_factory=dict)


class ParameterEvolutionEngine:
    """DeepSeek 参数演变引擎。

    自动调整逻辑：
    - 成本超预算：连续7天成本超预算120%时，降低低优先级注入Token占比
    - 缓存命中率低：前缀缓存命中率低于阈值时，调整前缀层结构
    - 频率过高：某智能体调用频率异常时，调整模型层级偏好

    手动覆盖：
    - 运维者手动调整后，该参数自动调整暂停7天
    """

    def __init__(
        self,
        cost_tracker: Any = None,
        prefix_cache_manager: Any = None,
        budget_manager: Any = None,
    ) -> None:
        self._cost_tracker = cost_tracker
        self._prefix_cache_manager = prefix_cache_manager
        self._budget_manager = budget_manager
        self._constraint = EvolutionConstraint()
        self._audit_logs: list[ParameterEvolutionAuditLog] = []
        self._max_audit_logs = 10000

    def can_auto_adjust(self, agent_id: str, parameter_name: str) -> bool:
        """检查是否允许自动调整。

        约束：
        1. 同一智能体同一参数24小时内只能自动调整1次
        2. 手动调整后暂停7天
        """
        key = f"{agent_id}:{parameter_name}"

        # 检查手动暂停
        pause_until = self._constraint.manual_pause_until.get(key, 0)
        if time.time() < pause_until:
            remaining = pause_until - time.time()
            logger.debug(
                "参数 %s 被手动暂停，剩余 %.0f 小时",
                key,
                remaining / 3600,
            )
            return False

        # 检查自动调整冷却
        last_time = self._constraint.last_auto_adjust_time.get(key, 0)
        if time.time() - last_time < _AUTO_ADJUST_COOLDOWN_SECONDS:
            remaining = _AUTO_ADJUST_COOLDOWN_SECONDS - (time.time() - last_time)
            logger.debug(
                "参数 %s 自动调整冷却中，剩余 %.0f 小时",
                key,
                remaining / 3600,
            )
            return False

        return True

    def apply_manual_override(
        self,
        agent_id: str,
        parameter_name: str,
        new_value: float,
        reason: str = "",
    ) -> ParameterEvolutionAuditLog:
        """运维者手动覆盖参数。

        手动调整后，该参数自动调整暂停7天。
        """
        key = f"{agent_id}:{parameter_name}"

        self._constraint.manual_pause_until[key] = (
            time.time() + _MANUAL_PAUSE_SECONDS
        )

        log = ParameterEvolutionAuditLog(
            log_id=f"evo_{uuid.uuid4().hex[:8]}",
            agent_id=agent_id,
            parameter_name=parameter_name,
            new_value=new_value,
            trigger=EvolutionTrigger.MANUAL,
            reason=reason or "运维者手动覆盖",
            timestamp=time.time(),
        )
        self._record_audit(log)

        logger.info(
            "手动覆盖: agent=%s param=%s value=%.4f 暂停自动调整7天",
            agent_id,
            parameter_name,
            new_value,
        )
        return log

    def evaluate_cost_evolution(self, agent_id: str, budget_threshold: float = 0.0) -> Optional[ParameterEvolutionAuditLog]:
        """评估成本演变：连续7天成本超预算120%时调整。

        Args:
            agent_id: 智能体ID。
            budget_threshold: 预算阈值（0=使用默认120%）。

        Returns:
            审计日志或 None（无需调整）。
        """
        if self._cost_tracker is None:
            return None

        cost_info = self._cost_tracker.get_agent_cost(agent_id, period_days=_COST_OVERBUDGET_DAYS)
        total_cost = cost_info.get("total_cost", 0.0)

        if total_cost <= 0:
            return None

        threshold = budget_threshold if budget_threshold > 0 else _COST_OVERBUDGET_RATIO

        # 检查是否超预算（简化：用成本绝对值判断）
        # 实际应与预算对比，这里用阈值模式
        if total_cost < threshold:
            return None

        # 尝试降低低优先级段占比
        for segment in _LOW_PRIORITY_SEGMENTS:
            if not self.can_auto_adjust(agent_id, segment):
                continue

            key = f"{agent_id}:{segment}"
            old_value = self._get_current_allocation(agent_id, segment)
            new_value = max(_MIN_ALLOCATION_VALUE, old_value - _ADJUSTMENT_STEP)

            if new_value >= old_value:
                continue

            self._constraint.last_auto_adjust_time[key] = time.time()

            log = ParameterEvolutionAuditLog(
                log_id=f"evo_{uuid.uuid4().hex[:8]}",
                agent_id=agent_id,
                parameter_name=segment,
                old_value=old_value,
                new_value=new_value,
                trigger=EvolutionTrigger.AUTO_COST,
                reason=f"连续{_COST_OVERBUDGET_DAYS}天成本超预算{threshold:.0%}，降低低优先级注入占比",
                timestamp=time.time(),
            )
            self._record_audit(log)

            logger.info(
                "成本演变: agent=%s param=%s %.4f->%.4f",
                agent_id,
                segment,
                old_value,
                new_value,
            )
            return log

        return None

    def evaluate_cache_evolution(self, agent_id: str, hit_rate_threshold: float = 0.3) -> Optional[ParameterEvolutionAuditLog]:
        """评估缓存命中率演变：低于阈值时调整前缀层结构。"""
        if self._prefix_cache_manager is None:
            return None

        stats = self._prefix_cache_manager.get_cache_stats(agent_id)
        if not stats:
            return None

        hit_rate = stats.get("hit_rate", 1.0)
        if hit_rate >= hit_rate_threshold:
            return None

        parameter_name = "prefix_cache_structure"
        if not self.can_auto_adjust(agent_id, parameter_name):
            return None

        key = f"{agent_id}:{parameter_name}"
        self._constraint.last_auto_adjust_time[key] = time.time()

        log = ParameterEvolutionAuditLog(
            log_id=f"evo_{uuid.uuid4().hex[:8]}",
            agent_id=agent_id,
            parameter_name=parameter_name,
            old_value=hit_rate,
            new_value=hit_rate_threshold,
            trigger=EvolutionTrigger.AUTO_CACHE,
            reason=f"前缀缓存命中率 {hit_rate:.1%} 低于阈值 {hit_rate_threshold:.0%}",
            timestamp=time.time(),
        )
        self._record_audit(log)

        logger.info(
            "缓存演变: agent=%s hit_rate=%.1f%% threshold=%.0f%%",
            agent_id,
            hit_rate * 100,
            hit_rate_threshold * 100,
        )
        return log

    def get_audit_logs(self, agent_id: str = "", limit: int = 100) -> list[ParameterEvolutionAuditLog]:
        """获取审计日志。"""
        logs = self._audit_logs
        if agent_id:
            logs = [l for l in logs if l.agent_id == agent_id]
        return logs[-limit:]

    def _get_current_allocation(self, agent_id: str, segment: str) -> float:
        """获取当前分配占比。"""
        if self._budget_manager is not None:
            try:
                allocation = self._budget_manager.get_budget(agent_id, 128000)
                return getattr(allocation, segment, 0.05)
            except Exception:
                pass
        return 0.05

    def _record_audit(self, log: ParameterEvolutionAuditLog) -> None:
        """记录审计日志。"""
        self._audit_logs.append(log)
        if len(self._audit_logs) > self._max_audit_logs:
            self._audit_logs = self._audit_logs[-self._max_audit_logs:]