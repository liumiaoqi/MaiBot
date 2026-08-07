"""智能体绑定管理 Service 层（WebUI 专用）

从 routers/agent.py 下沉的 ORM 操作函数 + 纯转换函数 + 辅助函数。
router 层退化为薄包装：HTTP 解析 + session 管理 + 响应包装 + 错误处理。
"""

from typing import Any, Dict, List, Optional

from sqlmodel import select

from src.common.database.database_model import (
    AgentAutonomyBehaviorIntent,
    AgentAutonomyInterjectionEvent,
    AgentAutonomySpeakerChangeRecord,
    AgentRelationship,
    ChatSession,
    InnerMonologueEvent,
    SubAgentExecutionRecord,
)
from src.common.logger import get_logger
from src.core.adapters.agent_config_port import get_agent_config_provider
from src.core.protocols import AgentRoutingService
from src.maisaka.agent.config import AgentConfig
from src.maisaka.relationship.level import RelationshipLevel
from src.webui.errors import AppError
from src.webui.errors.codes import ErrorCode
from src.webui.schemas.agent import (
    AgentConfigResponse,
    BatchLatestSubAgentItem,
    BehaviorIntentItem,
    CohabitantInfo,
    InterjectionEventItem,
    InternalRelationshipResponse,
    LayeredPersonalityResponse,
    MonologueEventResponse,
    RelationshipItem,
    SessionAgentInfo,
    SpeakerChangeItem,
    SubAgentRecordResponse,
)

logger = get_logger("webui.agent_service")


# ── 辅助函数 ──────────────────────────────────────────────────────

def _get_registry() -> Any:
    return get_agent_config_provider()

def _get_agent_router() -> AgentRoutingService:
    """获取 ChatManager 持有的智能体路由器单例（通过 Port 注册点访问）"""
    from src.core.routing_port_registry import get_routing_service
    adapter = get_routing_service()
    if adapter is None:
        raise AppError(ErrorCode.SYS_SERVICE_UNAVAILABLE, "ChatManager 尚未初始化，智能体路由器不可用")
    return adapter

def _config_to_response(config: AgentConfig) -> AgentConfigResponse:
    return AgentConfigResponse(
        agent_id=config.agent_id,
        display_name=config.display_name,
        layered_personality=(
            LayeredPersonalityResponse(
                existence_layer=config.layered_personality.existence_layer,
                expression_layer=config.layered_personality.expression_layer,
                experience_layer=config.layered_personality.experience_layer,
                identity_layer=config.layered_personality.identity_layer,
                self_constraints=config.layered_personality.self_constraints,
            )
            if config.layered_personality
            else None
        ),
        reply_style=config.reply_style,
        is_default=config.is_default,
        color=config.color,
        emotion_baseline=config.emotion_baseline,
        emotion_decay_rate=config.emotion_decay_rate,
        relationship_growth_rate=config.relationship_growth_rate,
        talk_value_modifier=config.talk_value_modifier,

        memory_focus_areas=config.memory_focus_areas,
        internal_relationships=[
            InternalRelationshipResponse(
                target_agent_id=rel.target_agent_id,
                relationship_type=rel.relationship_type,
                attitude=rel.attitude,
                interaction_style=rel.interaction_style,
                mention_tendency=rel.mention_tendency,
                anti_mechanization=rel.anti_mechanization,
            )
            for rel in config.internal_relationships
        ],
        anti_mechanization_rules=config.anti_mechanization_rules,
    )


# ── ORM 操作函数（接收 session 参数，不自行创建 session）──────────

def query_agent_relationships(session: Any, agent_id: str) -> List[Dict[str, Any]]:
    """查询指定智能体的关系概览。

    Returns:
        关系字典列表，每项包含 user_id, level, level_name, score, total_interactions。
    """
    relationships = []
    rows = session.query(AgentRelationship).filter(
        AgentRelationship.agent_id == agent_id
    ).all()
    for row in rows:
        level = RelationshipLevel(row.level) if isinstance(row.level, int) else RelationshipLevel.from_score(row.score)
        relationships.append({
            "user_id": row.user_id,
            "level": level.value,
            "level_name": level.label_zh(),
            "score": row.score,
            "total_interactions": row.interaction_count,
        })
    return relationships


def set_session_agent_binding(session: Any, session_id: str, agent_id: Optional[str]) -> None:
    """更新或清除会话的智能体绑定（ChatSession.agent_id）。

    Args:
        session: 数据库会话。
        session_id: 聊天会话 ID。
        agent_id: 目标智能体 ID，None 表示清除绑定。
    """
    statement = select(ChatSession).filter_by(session_id=session_id).limit(1)
    db_session = session.exec(statement).first()
    if db_session:
        db_session.agent_id = agent_id
        session.add(db_session)


def get_sessions_by_agent(session: Any, agent_id: str) -> List[SessionAgentInfo]:
    """获取使用指定智能体的所有会话（联合查询 ChatSession + Activity，精确展示活跃状态）。

    Returns:
        SessionAgentInfo 列表。
    """
    from src.maisaka.agent_autonomy.activity_store import AgentActivityStore
    from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

    registry = _get_registry()
    if not registry.has_agent(agent_id):
        raise AppError(ErrorCode.BIZ_NOT_FOUND, f"智能体不存在: {agent_id}", http_status=404)
    config = registry.get_agent(agent_id)

    activity_store = AgentActivityStore()
    active_activities = activity_store.get_active_sessions_by_agent(agent_id)
    active_session_ids = {a.session_id for a in active_activities}
    activity_map = {a.session_id: a for a in active_activities}

    agent_router = _get_agent_router()

    sessions = []
    statement = select(ChatSession).filter_by(agent_id=agent_id)
    for s in session.exec(statement):
        is_active = s.session_id in active_session_ids
        status = "active" if is_active else "bound_inactive"
        activity = activity_map.get(s.session_id)
        last_spoke = None
        if activity and activity.last_spoke_at:
            last_spoke = activity.last_spoke_at.isoformat()

        is_primary = (agent_router.get_primary_agent(s.session_id) == agent_id)

        orch = AgentOrchestrator.get_by_session(s.session_id)
        agent_vitality = 0.0
        if orch is not None:
            agent_vitality = orch._vitality_manager.get_agent_vitality(agent_id, s.session_id)

        all_agents = agent_router.get_session_all_agents(s.session_id)
        cohabitants = []
        for other_id in all_agents:
            if other_id == agent_id:
                continue
            other_config = registry.get_agent(other_id) if registry.has_agent(other_id) else None
            other_primary = (agent_router.get_primary_agent(s.session_id) == other_id)
            other_status = "active"
            other_vitality = 0.0
            if orch is not None:
                other_vitality = orch._vitality_manager.get_agent_vitality(other_id, s.session_id)
            cohabitants.append(CohabitantInfo(
                agent_id=other_id,
                display_name=other_config.display_name if other_config else other_id,
                is_primary=other_primary,
                status=other_status,
                vitality_value=other_vitality,
            ))

        sessions.append(SessionAgentInfo(
            session_id=s.session_id,
            display_name=s.group_name or s.user_nickname or s.session_id,
            agent_id=agent_id,
            agent_display_name=config.display_name,
            status=status,
            is_primary=is_primary,
            last_spoke_at=last_spoke,
            vitality_value=agent_vitality,
            cohabitants=cohabitants,
        ))
    return sessions


def list_subagent_records(
    session: Any,
    agent_id: Optional[str],
    subagent_type: Optional[str],
    status: Optional[str],
    limit: int,
) -> List[SubAgentRecordResponse]:
    """获取子智能体执行记录。

    Returns:
        SubAgentRecordResponse 列表。
    """
    query = session.query(SubAgentExecutionRecord)
    if agent_id:
        query = query.filter(SubAgentExecutionRecord.agent_id == agent_id)
    if subagent_type:
        query = query.filter(SubAgentExecutionRecord.subagent_type == subagent_type)
    if status:
        query = query.filter(SubAgentExecutionRecord.status == status)
    query = query.order_by(SubAgentExecutionRecord.id.desc()).limit(limit)
    rows = query.all()

    data = []
    for row in rows:
        data.append(SubAgentRecordResponse(
            id=row.id,
            subagent_id=row.subagent_id,
            agent_id=row.agent_id,
            subagent_type=row.subagent_type,
            session_id=row.session_id,
            lifecycle=row.lifecycle,
            status=row.status,
            trigger_type=row.trigger_type,
            trigger_reason=row.trigger_reason,
            fork_context_captured=row.fork_context_captured,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cache_hit_tokens=row.cache_hit_tokens,
            started_at=row.started_at.isoformat() if row.started_at else None,
            completed_at=row.completed_at.isoformat() if row.completed_at else None,
            error_message=row.error_message,
            result_summary=row.result_summary,
        ))
    return data


def get_subagent_stats(session: Any) -> Dict[str, Any]:
    """获取子智能体执行统计。

    Returns:
        包含 total_executions, by_type, by_status, total_input_tokens,
        total_output_tokens, total_cache_hit_tokens 的字典。
    """
    rows = session.query(SubAgentExecutionRecord).all()
    by_type: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    total_input = 0
    total_output = 0
    total_cache = 0
    for row in rows:
        by_type[row.subagent_type] = by_type.get(row.subagent_type, 0) + 1
        by_status[row.status] = by_status.get(row.status, 0) + 1
        total_input += row.input_tokens
        total_output += row.output_tokens
        total_cache += row.cache_hit_tokens
    return {
        "total_executions": len(rows),
        "by_type": by_type,
        "by_status": by_status,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cache_hit_tokens": total_cache,
    }


def batch_get_relationships(session: Any, agent_ids: List[str]) -> Dict[str, List[RelationshipItem]]:
    """批量获取智能体关系概览。

    Args:
        session: 数据库会话。
        agent_ids: 智能体 ID 列表。

    Returns:
        Dict[str, List[RelationshipItem]]: 每个智能体的关系列表，失败时为空列表。
    """
    result: Dict[str, List[RelationshipItem]] = {}
    for agent_id in agent_ids:
        try:
            rows = session.query(AgentRelationship).filter(
                AgentRelationship.agent_id == agent_id
            ).all()
            items = []
            for row in rows:
                level = RelationshipLevel(row.level) if isinstance(row.level, int) else RelationshipLevel.from_score(row.score)
                items.append(RelationshipItem(
                    user_id=row.user_id,
                    level=level.value,
                    level_name=level.label_zh(),
                    score=row.score,
                    total_interactions=row.interaction_count,
                ))
            result[agent_id] = items
        except AppError:
            raise
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARN, "批量获取智能体关系失败", exception=e)
            logger.warning(f"批量获取关系 — 智能体 {agent_id} 失败: {e}")
            result[agent_id] = []
    return result


def batch_get_session_counts(session: Any, agent_ids: List[str]) -> Dict[str, int]:
    """批量获取各智能体的已绑定会话数量。

    Returns:
        Dict[str, int]: 每个智能体的会话数量，失败时为 0。
    """
    result: Dict[str, int] = {}
    for aid in agent_ids:
        try:
            count = session.query(ChatSession).filter(
                ChatSession.agent_id == aid
            ).count()
            result[aid] = count
        except AppError:
            raise
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARN, "批量获取会话数量失败", exception=e)
            logger.warning(f"批量获取会话数 — 智能体 {aid} 失败: {e}")
            result[aid] = 0
    return result


def batch_get_latest_subagent_records(
    session: Any,
    agent_ids: List[str],
) -> Dict[str, Optional[BatchLatestSubAgentItem]]:
    """批量获取各智能体最近一条子智能体执行记录。

    Returns:
        Dict[str, Optional[BatchLatestSubAgentItem]]: 每个智能体最近记录，无记录或失败时为 None。
    """
    result: Dict[str, Optional[BatchLatestSubAgentItem]] = {}
    for aid in agent_ids:
        try:
            row = session.query(SubAgentExecutionRecord).filter(
                SubAgentExecutionRecord.agent_id == aid
            ).order_by(
                SubAgentExecutionRecord.completed_at.desc()
            ).first()
            if row:
                result[aid] = BatchLatestSubAgentItem(
                    id=row.id,
                    subagent_id=row.subagent_id,
                    agent_id=row.agent_id,
                    subagent_type=row.subagent_type,
                    status=row.status,
                    completed_at=row.completed_at.isoformat() if row.completed_at else None,
                    result_summary=row.result_summary,
                )
            else:
                result[aid] = None
        except AppError:
            raise
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARN, "批量获取子智能体记录失败", exception=e)
            logger.warning(f"批量获取子智能体记录 — 智能体 {aid} 失败: {e}")
            result[aid] = None
    return result


def get_monologue_events(session: Any, agent_id: str, limit: int) -> List[MonologueEventResponse]:
    """获取智能体内心独白列表。

    Returns:
        MonologueEventResponse 列表。
    """
    stmt = (
        select(InnerMonologueEvent)
        .where(InnerMonologueEvent.agent_id == agent_id)
        .order_by(InnerMonologueEvent.created_at.desc())
        .limit(limit)
    )
    result = session.execute(stmt)
    rows = result.scalars().all()
    return [
        MonologueEventResponse(
            monologue_id=r.monologue_id,
            agent_id=r.agent_id,
            emotion_snapshot=r.emotion_snapshot,
            content=r.content,
            self_emotion_effect=r.self_emotion_effect,
            memory_references=r.memory_references,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]


def get_behavior_intents(session: Any, session_id: str, limit: int) -> List[BehaviorIntentItem]:
    """获取会话的行为意图列表。

    Returns:
        BehaviorIntentItem 列表。
    """
    rows = (
        session.query(AgentAutonomyBehaviorIntent)
        .filter(AgentAutonomyBehaviorIntent.session_id == session_id)
        .order_by(AgentAutonomyBehaviorIntent.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        BehaviorIntentItem(
            intent_id=r.intent_id,
            agent_id=r.agent_id,
            intent_type=r.intent_type,
            intent_strength=r.intent_strength,
            intent_source=r.intent_source,
            source_description=r.source_description,
            status=r.status,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]


def get_interjection_events(session: Any, session_id: str, limit: int) -> List[InterjectionEventItem]:
    """获取会话的插话事件列表。

    Returns:
        InterjectionEventItem 列表。
    """
    rows = (
        session.query(AgentAutonomyInterjectionEvent)
        .filter(AgentAutonomyInterjectionEvent.session_id == session_id)
        .order_by(AgentAutonomyInterjectionEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        InterjectionEventItem(
            event_id=r.event_id,
            agent_id=r.agent_id,
            primary_agent_id=r.primary_agent_id,
            interjection_type=r.interjection_type,
            trigger_reason=r.trigger_reason,
            intent_strength=r.intent_strength,
            content_summary=r.content_summary,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]


def get_speaker_changes(session: Any, session_id: str, limit: int) -> List[SpeakerChangeItem]:
    """获取会话的发言权变更记录。

    Returns:
        SpeakerChangeItem 列表。
    """
    rows = (
        session.query(AgentAutonomySpeakerChangeRecord)
        .filter(AgentAutonomySpeakerChangeRecord.session_id == session_id)
        .order_by(AgentAutonomySpeakerChangeRecord.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        SpeakerChangeItem(
            record_id=r.record_id,
            from_agent_id=r.from_agent_id,
            to_agent_id=r.to_agent_id,
            change_type=r.change_type,
            change_reason=r.change_reason,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]