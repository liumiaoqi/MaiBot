"""话题账本 — 话题起点判定、预算扣减与动作记账。

一个会话一个 TopicLedger。进程内用一把 asyncio.Lock 串行化「读-判-写」，
跨进程靠 topic_id 主键兜底：并发重复建行时捕获冲突并回读已有行，
不产生第二行、不二次开场。
"""

import asyncio

from datetime import datetime
from uuid import uuid7

from sqlalchemy.exc import IntegrityError

from src.common.database.database import get_db_session
from src.common.database.database_model import ButlerTopicActionRecord, ButlerTopicState
from src.common.logger import get_logger
from src.core.error_escalation.types import ErrorLevel
from src.core.error_escalation_port_registry import get_error_escalation_port
from src.maisaka.agent_autonomy.butler_closure import (
    ActionKind,
    BudgetDecision,
    ButlerClosureConfig,
    OpeningOutcome,
    TopicContext,
    TopicTrigger,
)


__all__ = ["TopicLedger"]


logger = get_logger("agent_autonomy.topic_ledger")


class TopicLedger:
    """单个会话的话题状态与预算记账。"""

    def __init__(self, session_id: str, config: ButlerClosureConfig) -> None:
        self._session_id = session_id
        self._config = config
        self._lock = asyncio.Lock()
        self._current: TopicContext | None = None
        self._action_seq = 0

    def _threshold_seconds(self) -> float:
        return float(self._config.silence_threshold_minutes) * 60.0

    async def resolve(
        self,
        *,
        message_id: str,
        message_at: datetime,
        session_last_active_at: datetime | None,
    ) -> TopicContext:
        """返回当前消息所属话题；不存在或已越过静默阈值时建新行（is_new=True）。

        判定是确定性的，不依赖 LLM：
        - 该会话无任何话题行 → 新建 + SESSION_FIRST（升级后存量会话也算首条，P3 已定稿）；
        - 最新行 last_visible_at 与本条消息间隔 ≥ 阈值 → 新建 + SILENCE_GAP，旧行回填 ended_reason；
        - 否则复用最新行, is_new=False。
        """
        # session_last_active_at 当前不参与判定：静默间隔只认话题行的 last_visible_at

        async with self._lock:
            with get_db_session(auto_commit=False) as session:
                latest = (
                    session.query(ButlerTopicState)
                    .filter(ButlerTopicState.session_id == self._session_id)
                    .order_by(ButlerTopicState.started_at.desc())
                    .first()
                )

                if latest is not None:
                    gap = (message_at - latest.last_visible_at).total_seconds()
                    if gap < self._threshold_seconds():
                        return self._to_context(latest, is_new=False)
                    latest.ended_reason = "silence_gap"
                    latest.updated_at = message_at
                    trigger = TopicTrigger.SILENCE_GAP
                    silence_seconds = max(gap, 0.0)
                else:
                    trigger = TopicTrigger.SESSION_FIRST
                    silence_seconds = 0.0

                topic_id = self._build_topic_id(message_id=message_id, message_at=message_at)
                row = ButlerTopicState(
                    topic_id=topic_id,
                    session_id=self._session_id,
                    started_at=message_at,
                    trigger_type=trigger.value,
                    silence_seconds=silence_seconds,
                    last_visible_at=message_at,
                    budget_limit=self._config.budget_limit,
                    budget_used=0,
                    closure_used=False,
                    opening_outcome="pending",
                    opening_reason="",
                    opening_chars=0,
                    scene_missing="",
                    ended_reason="",
                    updated_at=message_at,
                )
                session.add(row)
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    existing = (
                        session.query(ButlerTopicState)
                        .filter(ButlerTopicState.topic_id == topic_id)
                        .first()
                    )
                    if existing is None:
                        raise
                    return self._to_context(existing, is_new=False)
                return self._to_context(row, is_new=True)

    async def try_consume(self, topic_id: str, kind: ActionKind) -> BudgetDecision:
        """锁内「读-判-增-写」，预算耗尽即拒绝。"""
        del kind  # 预算扣减与动作类型无关；动作类型由 record_action 单独留痕

        async with self._lock:
            with get_db_session(auto_commit=False) as session:
                row = (
                    session.query(ButlerTopicState)
                    .filter(ButlerTopicState.topic_id == topic_id)
                    .first()
                )
                if row is None:
                    return BudgetDecision(
                        granted=False,
                        used=0,
                        limit=self._config.budget_limit,
                        exhausted=True,
                    )

                if row.budget_used >= row.budget_limit:
                    return BudgetDecision(
                        granted=False,
                        used=row.budget_used,
                        limit=row.budget_limit,
                        exhausted=True,
                    )

                row.budget_used += 1
                row.updated_at = datetime.now()
                session.commit()
                return BudgetDecision(
                    granted=True,
                    used=row.budget_used,
                    limit=row.budget_limit,
                    exhausted=row.budget_used >= row.budget_limit,
                )

    async def mark_opening(
        self,
        topic_id: str,
        outcome: OpeningOutcome,
        *,
        chars: int = 0,
        reason: str = "",
        missing: tuple[str, ...] = (),
    ) -> None:
        """记录开场结果；写入失败只上报，不阻断发言链路。"""
        try:
            with get_db_session(auto_commit=False) as session:
                try:
                    row = (
                        session.query(ButlerTopicState)
                        .filter(ButlerTopicState.topic_id == topic_id)
                        .first()
                    )
                    if row is None:
                        return
                    row.opening_outcome = outcome.value
                    row.opening_reason = reason
                    row.opening_chars = chars
                    row.scene_missing = ",".join(missing)[:200]
                    row.updated_at = datetime.now()
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    self._report_failure("mark_opening", topic_id, exc)
        except Exception as exc:
            self._report_failure("mark_opening", topic_id, exc)

    async def record_action(
        self,
        topic_id: str,
        kind: ActionKind,
        *,
        outcome: str = "",
        target_agent_id: str = "",
        detail: str = "",
    ) -> None:
        """追加一条动作流水；写入失败只上报，不阻断发言链路。"""
        try:
            with get_db_session(auto_commit=False) as session:
                try:
                    row = (
                        session.query(ButlerTopicState)
                        .filter(ButlerTopicState.topic_id == topic_id)
                        .first()
                    )
                    used = row.budget_used if row is not None else 0
                    limit = row.budget_limit if row is not None else self._config.budget_limit
                    record = ButlerTopicActionRecord(
                        record_id=self._build_record_id(topic_id),
                        topic_id=topic_id,
                        session_id=self._session_id,
                        kind=kind.value,
                        outcome=outcome,
                        budget_used_after=used,
                        budget_limit=limit,
                        target_agent_id=target_agent_id,
                        detail=detail[:500],
                        created_at=datetime.now(),
                    )
                    session.add(record)
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    self._report_failure("record_action", topic_id, exc)
        except Exception as exc:
            self._report_failure("record_action", topic_id, exc)

    async def touch_last_visible(self, topic_id: str, at: datetime) -> None:
        """更新话题的最后可见消息时间。"""
        try:
            with get_db_session(auto_commit=False) as session:
                try:
                    row = (
                        session.query(ButlerTopicState)
                        .filter(ButlerTopicState.topic_id == topic_id)
                        .first()
                    )
                    if row is None:
                        return
                    row.last_visible_at = at
                    row.updated_at = at
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    self._report_failure("touch_last_visible", topic_id, exc)
        except Exception as exc:
            self._report_failure("touch_last_visible", topic_id, exc)

    def current(self) -> TopicContext | None:
        """最近一次 resolve 得到的话题上下文。"""
        return self._current

    def _to_context(self, row: ButlerTopicState, *, is_new: bool) -> TopicContext:
        context = TopicContext(
            topic_id=row.topic_id,
            session_id=row.session_id,
            trigger=TopicTrigger(row.trigger_type),
            started_at=row.started_at,
            silence_seconds=row.silence_seconds,
            budget_limit=row.budget_limit,
            budget_used=row.budget_used,
            closure_used=row.closure_used,
            is_new=is_new,
        )
        self._current = context
        return context

    def _build_topic_id(self, *, message_id: str, message_at: datetime) -> str:
        if message_id:
            return f"tg:{self._session_id}:{message_id}"
        return f"tg:{self._session_id}:{int(message_at.timestamp())}"

    def _build_record_id(self, topic_id: str) -> str:
        self._action_seq += 1
        candidate = f"bta:{topic_id}:{self._action_seq}"
        if len(candidate) <= 128:
            return candidate
        return f"bta:{uuid7()}"

    def _report_failure(self, action: str, topic_id: str, exc: Exception) -> None:
        """记账失败双通道：日志 + 错误上报。"""
        logger.warning(
            f"话题记账失败 action={action} session={self._session_id} topic={topic_id}: {exc}",
            exc_info=True,
        )
        port = get_error_escalation_port()
        if port is not None:
            port.report(
                ErrorLevel.ERROR,
                f"话题记账失败 action={action} session={self._session_id}",
                exception=exc,
            )
