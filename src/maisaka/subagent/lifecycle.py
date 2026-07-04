"""子智能体生命周期管理器。

管理 ephemeral（用完即弃）和 persistent（可恢复）两种生命周期模式。
- ephemeral: 任务完成后立即销毁，丢弃未完成的中间结果。
- persistent: 任务完成后保留状态，可恢复执行。
"""

from __future__ import annotations

import logging
from typing import Optional

from .models import (
    SubAgentLifecycle,
    SubAgentSpec,
    SubAgentState,
    SubAgentStatus,
    generate_subagent_id,
)

logger = logging.getLogger(__name__)


class SubAgentLifecycleManager:
    """子智能体生命周期管理器。

    提供 create / complete / fail / suspend / resume / destroy 方法，
    按 lifecycle 模式决定终态行为。
    """

    def __init__(self) -> None:
        self._instances: dict[str, SubAgentStatus] = {}

    def create(self, spec: SubAgentSpec) -> SubAgentStatus:
        """创建子智能体实例。

        Args:
            spec: 子智能体规格。

        Returns:
            SubAgentStatus: 初始状态（PENDING）。
        """
        subagent_id = generate_subagent_id()
        status = SubAgentStatus(
            subagent_id=subagent_id,
            spec=spec,
            state=SubAgentState.PENDING,
        )
        self._instances[subagent_id] = status
        logger.info(
            "子智能体创建: id=%s type=%s lifecycle=%s agent_id=%s",
            subagent_id,
            spec.subagent_type.value,
            spec.lifecycle.value,
            spec.agent_id,
        )
        return status

    def start(self, subagent_id: str) -> Optional[SubAgentStatus]:
        """将子智能体从 PENDING 转为 RUNNING。

        Args:
            subagent_id: 子智能体实例ID。

        Returns:
            更新后的 SubAgentStatus，不存在则返回 None。
        """
        status = self._instances.get(subagent_id)
        if status is None:
            return None
        if status.state != SubAgentState.PENDING:
            logger.warning(
                "子智能体状态非PENDING，无法启动: id=%s state=%s",
                subagent_id,
                status.state.value,
            )
            return status
        import time

        status.state = SubAgentState.RUNNING
        status.started_at = time.time()
        logger.info("子智能体启动: id=%s", subagent_id)
        return status

    def complete(self, subagent_id: str, result_summary: str = "") -> Optional[SubAgentStatus]:
        """标记子智能体完成。

        - ephemeral: 完成后转为 DESTROYED。
        - persistent: 完成后转为 SUSPENDED（可恢复）。

        Args:
            subagent_id: 子智能体实例ID。
            result_summary: 结果摘要。

        Returns:
            更新后的 SubAgentStatus，不存在则返回 None。
        """
        status = self._instances.get(subagent_id)
        if status is None:
            return None
        import time

        status.completed_at = time.time()
        status.progress = 1.0
        status.result_summary = result_summary

        if status.spec.lifecycle == SubAgentLifecycle.EPHEMERAL:
            status.state = SubAgentState.DESTROYED
            logger.info(
                "ephemeral 子智能体完成并销毁: id=%s", subagent_id
            )
        else:
            status.state = SubAgentState.SUSPENDED
            logger.info(
                "persistent 子智能体完成并挂起: id=%s", subagent_id
            )
        return status

    def fail(self, subagent_id: str, error_message: str = "") -> Optional[SubAgentStatus]:
        """标记子智能体失败。

        - ephemeral: 失败后转为 DESTROYED，丢弃中间结果。
        - persistent: 失败后保留 FAILED 状态，已处理的部分结果保留在 result_summary 中。

        Args:
            subagent_id: 子智能体实例ID。
            error_message: 错误信息。

        Returns:
            更新后的 SubAgentStatus，不存在则返回 None。
        """
        status = self._instances.get(subagent_id)
        if status is None:
            return None
        import time

        status.completed_at = time.time()
        status.error_message = error_message

        if status.spec.lifecycle == SubAgentLifecycle.EPHEMERAL:
            status.state = SubAgentState.DESTROYED
            logger.info(
                "ephemeral 子智能体失败并销毁: id=%s error=%s",
                subagent_id,
                error_message,
            )
        else:
            status.state = SubAgentState.FAILED
            logger.info(
                "persistent 子智能体失败（保留状态）: id=%s error=%s",
                subagent_id,
                error_message,
            )
        return status

    def suspend(self, subagent_id: str, progress: float = 0.0, progress_description: str = "") -> Optional[SubAgentStatus]:
        """挂起 persistent 子智能体。

        Args:
            subagent_id: 子智能体实例ID。
            progress: 当前进度。
            progress_description: 进度描述。

        Returns:
            更新后的 SubAgentStatus，不存在或非 persistent 则返回 None。
        """
        status = self._instances.get(subagent_id)
        if status is None:
            return None
        if status.spec.lifecycle != SubAgentLifecycle.PERSISTENT:
            logger.warning("仅 persistent 子智能体可挂起: id=%s", subagent_id)
            return None
        status.state = SubAgentState.SUSPENDED
        status.progress = progress
        status.progress_description = progress_description
        logger.info("persistent 子智能体挂起: id=%s progress=%.2f", subagent_id, progress)
        return status

    def resume(self, subagent_id: str) -> Optional[SubAgentStatus]:
        """恢复 SUSPENDED 的 persistent 子智能体。

        Args:
            subagent_id: 子智能体实例ID。

        Returns:
            更新后的 SubAgentStatus，不存在或状态不允许则返回 None。
        """
        status = self._instances.get(subagent_id)
        if status is None:
            return None
        if status.state != SubAgentState.SUSPENDED:
            logger.warning(
                "子智能体非SUSPENDED状态，无法恢复: id=%s state=%s",
                subagent_id,
                status.state.value,
            )
            return None
        status.state = SubAgentState.RUNNING
        logger.info("persistent 子智能体恢复: id=%s", subagent_id)
        return status

    def cancel(self, subagent_id: str) -> Optional[SubAgentStatus]:
        """取消子智能体。

        - ephemeral: 转为 DESTROYED，丢弃中间结果。
        - persistent: 转为 CANCELLED，保留已处理的部分结果。

        Args:
            subagent_id: 子智能体实例ID。

        Returns:
            更新后的 SubAgentStatus，不存在则返回 None。
        """
        status = self._instances.get(subagent_id)
        if status is None:
            return None
        import time

        status.completed_at = time.time()

        if status.spec.lifecycle == SubAgentLifecycle.EPHEMERAL:
            status.state = SubAgentState.DESTROYED
            logger.info("ephemeral 子智能体取消并销毁: id=%s", subagent_id)
        else:
            status.state = SubAgentState.CANCELLED
            logger.info("persistent 子智能体取消（保留部分结果）: id=%s", subagent_id)
        return status

    def get_status(self, subagent_id: str) -> Optional[SubAgentStatus]:
        """获取子智能体运行状态。"""
        return self._instances.get(subagent_id)

    def list_by_agent(self, agent_id: str) -> list[SubAgentStatus]:
        """列出指定父级智能体的所有子智能体。"""
        return [
            s for s in self._instances.values() if s.spec.agent_id == agent_id
        ]

    def list_active(self) -> list[SubAgentStatus]:
        """列出所有活跃（非终态）的子智能体。"""
        return [s for s in self._instances.values() if not s.is_terminal]

    def cleanup_terminal(self) -> int:
        """清理所有终态实例，返回清理数量。"""
        terminal_ids = [
            sid for sid, s in self._instances.items() if s.is_terminal
        ]
        for sid in terminal_ids:
            del self._instances[sid]
        if terminal_ids:
            logger.info("清理 %d 个终态子智能体", len(terminal_ids))
        return len(terminal_ids)