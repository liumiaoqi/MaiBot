"""插话调度器——基于智能体自主报告的行为意图强度调度插话。"""

from __future__ import annotations

from dataclasses import dataclass

from src.common.logger import get_logger
from src.maisaka.agent_autonomy.autonomy_logger import AutonomyEventType, AutonomyLogger
from src.maisaka.agent_autonomy.behavior_intent import BehaviorIntent
from src.maisaka.agent_autonomy.interjection_cooldown import InterjectionCooldownManager

logger = get_logger("agent_autonomy.interjection_scheduler")


@dataclass
class ScheduledInterjection:
    """调度决策。"""

    agent_id: str
    intent: BehaviorIntent
    scheduled: bool = False
    skip_reason: str = ""


class InterjectionScheduler:
    """插话调度器。

    核心约束：不计算插话意愿，只基于智能体报告的意图强度排序。
    """

    def __init__(self, cooldown_manager: InterjectionCooldownManager) -> None:
        self._cooldown_manager = cooldown_manager
        self._autonomy_logger = AutonomyLogger.get()

    def schedule(
        self,
        pending_intents: list[tuple[str, BehaviorIntent]],
        active_agent_ids: list[str],
        primary_agent_id: str,
    ) -> list[ScheduledInterjection]:
        """基于行为意图强度调度插话。

        Args:
            pending_intents: 智能体报告的行为意图列表 [(agent_id, intent)]
            active_agent_ids: 活跃智能体 ID 列表
            primary_agent_id: 主发言智能体 ID（排除调度）

        Returns:
            调度决策列表（按意图强度降序）
        """
        # 按意图强度降序排序
        sorted_intents = sorted(
            pending_intents,
            key=lambda x: x[1].intent_strength,
            reverse=True,
        )

        results: list[ScheduledInterjection] = []

        for agent_id, intent in sorted_intents:
            # 排除主发言智能体
            if agent_id == primary_agent_id:
                results.append(ScheduledInterjection(
                    agent_id=agent_id,
                    intent=intent,
                    scheduled=False,
                    skip_reason="is_primary",
                ))
                continue

            # 检查是否活跃
            if agent_id not in active_agent_ids:
                results.append(ScheduledInterjection(
                    agent_id=agent_id,
                    intent=intent,
                    scheduled=False,
                    skip_reason="not_active",
                ))
                continue

            # 检查冷却和频率限制
            # 注意：需要 session_id，这里从 intent 的上下文中获取
            # 暂时使用空字符串，Orchestrator 调度时会传入正确的 session_id
            self._autonomy_logger.log(
                agent_id,
                AutonomyEventType.INTERJECTION,
                f"决定插话(强度={intent.intent_strength:.1f}, 来源={intent.intent_source})",
            )
            results.append(ScheduledInterjection(
                agent_id=agent_id,
                intent=intent,
                scheduled=True,
                skip_reason="",
            ))

        return results

    def schedule_with_session(
        self,
        pending_intents: list[tuple[str, BehaviorIntent]],
        active_agent_ids: list[str],
        primary_agent_id: str,
        session_id: str,
    ) -> list[ScheduledInterjection]:
        """带会话上下文的插话调度。"""
        sorted_intents = sorted(
            pending_intents,
            key=lambda x: x[1].intent_strength,
            reverse=True,
        )

        results: list[ScheduledInterjection] = []

        for agent_id, intent in sorted_intents:
            if agent_id == primary_agent_id:
                results.append(ScheduledInterjection(
                    agent_id=agent_id,
                    intent=intent,
                    scheduled=False,
                    skip_reason="is_primary",
                ))
                continue

            if agent_id not in active_agent_ids:
                results.append(ScheduledInterjection(
                    agent_id=agent_id,
                    intent=intent,
                    scheduled=False,
                    skip_reason="not_active",
                ))
                continue

            if not self._cooldown_manager.can_interject(session_id, agent_id):
                remaining = self._cooldown_manager.get_cooldown_remaining(session_id, agent_id)
                self._autonomy_logger.log(
                    agent_id,
                    AutonomyEventType.INTERJECTION,
                    f"跳过插话(冷却中, 剩余{remaining:.0f}s)",
                    level="warning",
                )
                results.append(ScheduledInterjection(
                    agent_id=agent_id,
                    intent=intent,
                    scheduled=False,
                    skip_reason=f"cooldown({remaining:.0f}s)",
                ))
                continue

            results.append(ScheduledInterjection(
                agent_id=agent_id,
                intent=intent,
                scheduled=True,
                skip_reason="",
            ))

        return results