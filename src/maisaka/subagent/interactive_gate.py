"""非交互门控。

当子智能体标记为 interactive=False 时，
其发起的 ask 请求（需要人类审批的操作）自动拒绝并返回拒绝响应，
避免后台智能体弹出人类审批导致死锁。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import SubAgentSpec, SubAgentStatus, SubAgentState

logger = logging.getLogger(__name__)


@dataclass
class AskRequest:
    """ask 请求（需要人类审批的操作）。"""

    subagent_id: str
    action: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AskResponse:
    """ask 响应。"""

    approved: bool
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class InteractiveGate:
    """非交互门控。

    - interactive=False 的子智能体发起的 ask 请求自动拒绝。
    - interactive=True 的子智能体 ask 请求正常走审批流程。
    """

    NON_INTERACTIVE_REJECTION_REASON = "子智能体标记为非交互模式，ask 请求自动拒绝"

    def __init__(self) -> None:
        self._pending_requests: dict[str, AskRequest] = {}
        self._rejection_count: int = 0

    def evaluate_ask(
        self,
        spec: SubAgentSpec,
        request: AskRequest,
    ) -> AskResponse:
        """评估子智能体的 ask 请求。

        Args:
            spec: 子智能体规格。
            request: ask 请求。

        Returns:
            AskResponse: 非交互模式返回拒绝响应；交互模式返回待审批响应。
        """
        if not spec.interactive:
            self._rejection_count += 1
            logger.debug(
                "非交互门控拒绝: subagent_id=%s action=%s",
                request.subagent_id,
                request.action,
            )
            return AskResponse(
                approved=False,
                reason=self.NON_INTERACTIVE_REJECTION_REASON,
            )

        self._pending_requests[request.subagent_id] = request
        logger.debug(
            "交互模式 ask 请求待审批: subagent_id=%s action=%s",
            request.subagent_id,
            request.action,
        )
        return AskResponse(
            approved=False,
            reason="等待人类审批",
        )

    def approve(self, subagent_id: str, reason: str = "") -> Optional[AskResponse]:
        """审批通过指定子智能体的待审批请求。

        Args:
            subagent_id: 子智能体实例ID。
            reason: 审批通过原因。

        Returns:
            AskResponse 或 None（无待审批请求）。
        """
        request = self._pending_requests.pop(subagent_id, None)
        if request is None:
            return None
        return AskResponse(approved=True, reason=reason or "审批通过")

    def reject(self, subagent_id: str, reason: str = "") -> Optional[AskResponse]:
        """审批拒绝指定子智能体的待审批请求。

        Args:
            subagent_id: 子智能体实例ID。
            reason: 拒绝原因。

        Returns:
            AskResponse 或 None（无待审批请求）。
        """
        request = self._pending_requests.pop(subagent_id, None)
        if request is None:
            return None
        return AskResponse(approved=False, reason=reason or "审批拒绝")

    @property
    def rejection_count(self) -> int:
        """非交互模式累计拒绝次数。"""
        return self._rejection_count

    @property
    def pending_count(self) -> int:
        """当前待审批请求数。"""
        return len(self._pending_requests)

    def should_auto_reject(self, spec: SubAgentSpec) -> bool:
        """判断是否应自动拒绝（供外部快速检查）。"""
        return not spec.interactive