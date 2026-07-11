"""智能体管理 API 路由"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from sqlmodel import select

from src.common.database.database import get_db_session
from src.common.database.database_model import AgentRelationship, ChatSession, SubAgentExecutionRecord
from src.common.logger import get_logger
from src.maisaka.agent.config import AgentConfig
from src.maisaka.agent.emotion import EMOTION_LABELS_ZH, EmotionManager
from src.maisaka.agent.registry import AgentConfigRegistry

from src.core.adapters.routing_adapter import ChatManagerRoutingAdapter
from src.maisaka.relationship.level import RelationshipLevel
from src.webui.dependencies import require_auth
from src.webui.errors import AppError
from src.webui.errors.codes import ErrorCode
from src.webui.schemas.base import ApiResponse
from src.webui.schemas.agent import (
    ActiveAgentItem,
    ActiveAgentsResponse,
    AgentConfigResponse,
    AgentDetailResponse,
    AgentListResponse,
    AgentProfileResponse,
    AutonomyLogItem,
    AutonomyLogResponse,
    BatchBindError,
    BatchBindItem,
    BatchBindRequest,
    BatchBindResponse,
    BatchEmotionItem,
    BatchEmotionResponse,
    BatchLatestSubAgentItem,
    BatchLatestSubAgentResponse,
    BatchRelationshipResponse,
    BatchSessionCountResponse,
    BehaviorIntentItem,
    BehaviorIntentsResponse,
    BindGroupRequest,
    BindSessionRequest,
    CohabitantEntryItem,
    CohabitantInfo,
    EmotionBaselineResponse,
    EmotionBehaviorRuleResponse,
    EmotionBehaviorRulesResponse,
    EmotionStateResponse,
    GroupBindingResponse,
    GroupBindingsListResponse,
    InteractionConfigResponse,
    InteractionEventResponse,
    InterjectionEventItem,
    InterjectionEventsResponse,
    InternalRelationshipResponse,
    ManualTriggerRequest,
    ManualTriggerResponse,
    MigrationAdvanceResponse,
    MigrationStateResponse,
    MonologueEventResponse,
    PrimaryAgentResponse,
    RelationshipItem,
    RelationshipSummaryResponse,
    ReloadResponse,
    SessionAgentInfo,
    SessionBindingResponse,
    SessionVitalityResponse,
    SessionsByAgentResponse,
    SpeakerChangeItem,
    SpeakerChangesResponse,
    StateAwarenessResponse,
    SubAgentListResponse,
    SubAgentRecordResponse,
    SubAgentStatsResponse,
    SwitchSpeakerRequest,
    SwitchSpeakerResponse,
    TriggerInterjectionRequest,
    TriggerInterjectionResponse,
    VitalityAgentItem,
)

logger = get_logger("webui.agent")

router = APIRouter(prefix="/agent", tags=["Agent"], dependencies=[Depends(require_auth)])

def _get_registry() -> AgentConfigRegistry:
    return AgentConfigRegistry.get_instance()

def _get_agent_router() -> ChatManagerRoutingAdapter:
    """获取 ChatManager 持有的智能体路由器单例（通过适配器层访问）"""
    adapter = ChatManagerRoutingAdapter()
    if adapter._ensure_router() is None:
        raise AppError(ErrorCode.SYS_SERVICE_UNAVAILABLE, "ChatManager 尚未初始化，智能体路由器不可用")
    return adapter

def _config_to_response(config: AgentConfig) -> AgentConfigResponse:
    return AgentConfigResponse(
        agent_id=config.agent_id,
        display_name=config.display_name,
        personality=config.personality,
        reply_style=config.reply_style,
        is_default=config.is_default,
        color=config.color,
        emotion_baseline=config.emotion_baseline,
        emotion_decay_rate=config.emotion_decay_rate,
        relationship_growth_rate=config.relationship_growth_rate,
        talk_value_modifier=config.talk_value_modifier,
        idle_backoff_modifier=config.idle_backoff_modifier,
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

@router.get("/list", response_model=ApiResponse[AgentListResponse])
async def list_agents():
    """获取所有智能体配置列表"""
    try:
        registry = _get_registry()
        agents = registry.list_agents()
        return AgentListResponse(
            success=True,
            total=len(agents),
            data=[_config_to_response(a) for a in agents],
        )
    except Exception as e:
        logger.error(f"获取智能体列表失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "获取智能体列表失败") from e

@router.get("/{agent_id}", response_model=ApiResponse[AgentDetailResponse])
async def get_agent_detail(agent_id: str):
    """获取指定智能体详细配置"""
    try:
        registry = _get_registry()
        if not registry.has_agent(agent_id):
            raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_id}")
        config = registry.get_agent(agent_id)
        return AgentDetailResponse(success=True, data=_config_to_response(config))
    except Exception as e:
        logger.error(f"获取智能体详情失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "获取智能体详情失败") from e

@router.get("/emotion/{agent_id}", response_model=ApiResponse[EmotionStateResponse])
async def get_agent_emotion(agent_id: str):
    """获取指定智能体当前情绪状态"""
    try:
        registry = _get_registry()
        if not registry.has_agent(agent_id):
            raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_id}")
        config = registry.get_agent(agent_id)
        from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
        emotion_registry = AgentEmotionManagerRegistry()
        manager = emotion_registry.get_emotion_manager(agent_id)
        if manager is None:
            manager = EmotionManager(config)
        state = manager.state
        dominant = state.get_dominant()
        return EmotionStateResponse(
            success=True,
            agent_id=agent_id,
            emotions=state.emotions,
            dominant_emotion=dominant,
            dominant_emotion_label=EMOTION_LABELS_ZH.get(dominant, dominant),
            emotion_labels=EMOTION_LABELS_ZH,
        )
    except Exception as e:
        logger.error(f"获取智能体情绪状态失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "获取智能体情绪状态失败") from e

@router.get("/relationship/{agent_id}", response_model=ApiResponse[RelationshipSummaryResponse])
async def get_agent_relationships(agent_id: str):
    """获取指定智能体的关系概览"""
    try:
        registry = _get_registry()
        if not registry.has_agent(agent_id):
            raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_id}")
        relationships = []
        with get_db_session() as db:
            rows = db.query(AgentRelationship).filter(
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
        return RelationshipSummaryResponse(
            success=True,
            agent_id=agent_id,
            relationships=relationships,
        )
    except Exception as e:
        logger.error(f"获取智能体关系概览失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "获取智能体关系概览失败") from e

@router.get("/binding/session/{session_id}", response_model=ApiResponse[SessionBindingResponse])
async def get_session_binding(session_id: str):
    """获取会话绑定的智能体"""
    try:
        agent_router = _get_agent_router()
        agent_id = agent_router.get_session_binding(session_id)
        display_name = None
        if agent_id:
            registry = _get_registry()
            config = registry.get_agent(agent_id)
            display_name = config.display_name
        return SessionBindingResponse(
            success=True,
            session_id=session_id,
            agent_id=agent_id,
            display_name=display_name,
        )
    except Exception as e:
        logger.error(f"获取会话绑定失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "获取会话绑定失败") from e

@router.put("/binding/session/{session_id}", response_model=ApiResponse[SessionBindingResponse])
async def bind_session_agent(session_id: str, request: BindSessionRequest):
    """绑定会话到指定智能体（双写：内存路由器 + 数据库 + Activity）"""
    try:
        agent_router = _get_agent_router()
        try:
            agent_router.bind_session(session_id, request.agent_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        primary_agent = agent_router.get_session_primary_agent(session_id)
        try:
            with get_db_session() as db:
                statement = select(ChatSession).filter_by(session_id=session_id).limit(1)
                db_session = db.exec(statement).first()
                if db_session:
                    db_session.agent_id = primary_agent
                    db.add(db_session)
        except Exception as db_exc:
            agent_router.unbind_session(session_id, request.agent_id)
            logger.error(f"绑定写入数据库失败，已回滚内存绑定: session={session_id}, agent={request.agent_id}, error={db_exc}")
            raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "绑定写入数据库失败") from db_exc

        is_primary = (primary_agent == request.agent_id)
        try:
            from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

            orchestrator = AgentOrchestrator.get_by_session(session_id)
            if orchestrator is not None:
                orchestrator.activate_agent(request.agent_id, "manual_binding", is_primary=is_primary)
        except Exception as orch_exc:
            logger.warning(f"绑定触发Orchestrator激活失败（不影响绑定结果）: session={session_id}, agent={request.agent_id}, error={orch_exc}")

        try:
            from src.maisaka.agent_autonomy.activity_store import AgentActivityStore

            AgentActivityStore().save_activity(
                session_id=session_id,
                agent_id=request.agent_id,
                is_primary=is_primary,
                activation_reason="manual_binding",
            )
        except Exception as act_exc:
            logger.warning(f"绑定写入Activity记录失败（不影响绑定结果）: session={session_id}, agent={request.agent_id}, error={act_exc}")

        registry = _get_registry()
        config = registry.get_agent(request.agent_id)
        return SessionBindingResponse(
            success=True,
            session_id=session_id,
            agent_id=request.agent_id,
            display_name=config.display_name,
        )
    except Exception as e:
        logger.error(f"绑定会话智能体失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "绑定会话智能体失败") from e

@router.delete("/binding/session/{session_id}", response_model=ApiResponse[SessionBindingResponse])
async def unbind_session_agent(session_id: str):
    """解除会话的所有智能体绑定（四清：内存+数据库+Orchestrator退场+Activity关闭）"""
    try:
        agent_router = _get_agent_router()
        all_agents = agent_router.get_session_all_agents(session_id)

        for aid in all_agents:
            try:
                from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

                orchestrator = AgentOrchestrator.get_by_session(session_id)
                if orchestrator is not None and aid in orchestrator._active_agents:
                    orchestrator.deactivate_agent(aid, "manual_unbind")
            except Exception as orch_exc:
                logger.warning(f"解绑时Orchestrator退场失败（继续清除）: session={session_id}, agent={aid}, error={orch_exc}")

            try:
                from src.maisaka.agent_autonomy.activity_store import AgentActivityStore

                AgentActivityStore().deactivate(session_id, aid, "manual_unbind")
            except Exception as act_exc:
                logger.warning(f"解绑时Activity关闭失败（继续清除）: session={session_id}, agent={aid}, error={act_exc}")

        agent_router.unbind_session(session_id)

        with get_db_session() as db:
            statement = select(ChatSession).filter_by(session_id=session_id).limit(1)
            db_session = db.exec(statement).first()
            if db_session:
                db_session.agent_id = None
                db.add(db_session)

        return SessionBindingResponse(success=True, session_id=session_id)
    except Exception as e:
        logger.error(f"解除会话绑定失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "解除会话绑定失败") from e

@router.delete("/binding/session/{session_id}/{agent_id}", response_model=ApiResponse[SessionBindingResponse])
async def unbind_session_specific_agent(session_id: str, agent_id: str):
    """解除会话中指定智能体的绑定（多智能体场景下精确解绑）"""
    try:
        agent_router = _get_agent_router()

        try:
            from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

            orchestrator = AgentOrchestrator.get_by_session(session_id)
            if orchestrator is not None and agent_id in orchestrator._active_agents:
                orchestrator.deactivate_agent(agent_id, "manual_unbind")
        except Exception as orch_exc:
            logger.warning(f"解绑时Orchestrator退场失败（继续清除）: session={session_id}, agent={agent_id}, error={orch_exc}")

        try:
            from src.maisaka.agent_autonomy.activity_store import AgentActivityStore

            AgentActivityStore().deactivate(session_id, agent_id, "manual_unbind")
        except Exception as act_exc:
            logger.warning(f"解绑时Activity关闭失败（继续清除）: session={session_id}, agent={agent_id}, error={act_exc}")

        agent_router.unbind_session(session_id, agent_id)

        remaining_primary = agent_router.get_session_primary_agent(session_id)
        with get_db_session() as db:
            statement = select(ChatSession).filter_by(session_id=session_id).limit(1)
            db_session = db.exec(statement).first()
            if db_session:
                db_session.agent_id = remaining_primary
                db.add(db_session)

        return SessionBindingResponse(success=True, session_id=session_id, agent_id=agent_id)
    except Exception as e:
        logger.error(f"解除指定智能体绑定失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "解除指定智能体绑定失败") from e

@router.put("/binding/batch", response_model=ApiResponse[BatchBindResponse])
async def batch_bind_sessions(request: BatchBindRequest):
    """批量绑定会话到指定智能体（双写：内存路由器 + 数据库 + Activity）"""
    registry = _get_registry()
    agent_router = _get_agent_router()
    succeeded = 0
    failed = 0
    errors: list[BatchBindError] = []

    for item in request.bindings:
        try:
            if not registry.has_agent(item.agent_id):
                errors.append(BatchBindError(session_id=item.session_id, error=f"智能体 {item.agent_id} 不存在"))
                failed += 1
                continue
            agent_router.bind_session(item.session_id, item.agent_id)

            primary_agent = agent_router.get_session_primary_agent(item.session_id)
            with get_db_session() as db:
                statement = select(ChatSession).filter_by(session_id=item.session_id).limit(1)
                db_session = db.exec(statement).first()
                if db_session:
                    db_session.agent_id = primary_agent
                    db.add(db_session)

            is_primary = (primary_agent == item.agent_id)
            try:
                from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

                orchestrator = AgentOrchestrator.get_by_session(item.session_id)
                if orchestrator is not None:
                    orchestrator.activate_agent(item.agent_id, "manual_binding", is_primary=is_primary)
            except Exception as orch_exc:
                logger.warning(f"批量绑定触发Orchestrator激活失败: session={item.session_id}, agent={item.agent_id}, error={orch_exc}")

            try:
                from src.maisaka.agent_autonomy.activity_store import AgentActivityStore

                AgentActivityStore().save_activity(
                    session_id=item.session_id,
                    agent_id=item.agent_id,
                    is_primary=is_primary,
                    activation_reason="manual_binding",
                )
            except Exception as act_exc:
                logger.warning(f"批量绑定写入Activity记录失败: session={item.session_id}, agent={item.agent_id}, error={act_exc}")

            succeeded += 1
        except Exception as e:
            errors.append(BatchBindError(session_id=item.session_id, error=str(e)))
            failed += 1
            logger.warning(f"批量绑定 — 会话 {item.session_id} 绑定失败: {e}")

    return BatchBindResponse(
        success=failed == 0,
        total=len(request.bindings),
        succeeded=succeeded,
        failed=failed,
        errors=errors,
    )

@router.get("/binding/group", response_model=ApiResponse[GroupBindingsListResponse])
async def list_group_bindings():
    """列出所有群-智能体绑定"""
    try:
        agent_router = _get_agent_router()
        return GroupBindingsListResponse(
            success=True,
            bindings=agent_router.list_group_bindings(),
        )
    except Exception as e:
        logger.error(f"获取群绑定列表失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "获取群绑定列表失败") from e

@router.put("/binding/group", response_model=ApiResponse[GroupBindingResponse])
async def bind_group_agent(request: BindGroupRequest):
    """绑定群到指定智能体"""
    try:
        agent_router = _get_agent_router()
        try:
            agent_router.bind_group(request.group_id, request.agent_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        registry = _get_registry()
        config = registry.get_agent(request.agent_id)
        return GroupBindingResponse(
            success=True,
            group_id=request.group_id,
            agent_id=request.agent_id,
            display_name=config.display_name,
        )
    except Exception as e:
        logger.error(f"绑定群智能体失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "绑定群智能体失败") from e

@router.delete("/binding/group/{group_id}", response_model=ApiResponse[GroupBindingResponse])
async def unbind_group_agent(group_id: str):
    """解除群的智能体绑定"""
    try:
        agent_router = _get_agent_router()
        agent_router.unbind_group(group_id)
        return GroupBindingResponse(success=True, group_id=group_id, agent_id="")
    except Exception as e:
        logger.error(f"解除群绑定失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "解除群绑定失败") from e

@router.get("/sessions/{agent_id}", response_model=ApiResponse[SessionsByAgentResponse])
async def get_sessions_by_agent(agent_id: str):
    """获取使用指定智能体的所有会话（联合查询 ChatSession + Activity，精确展示活跃状态）"""
    try:
        registry = _get_registry()
        if not registry.has_agent(agent_id):
            raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_id}")
        config = registry.get_agent(agent_id)

        from src.maisaka.agent_autonomy.activity_store import AgentActivityStore

        activity_store = AgentActivityStore()
        active_activities = activity_store.get_active_sessions_by_agent(agent_id)
        active_session_ids = {a.session_id for a in active_activities}
        activity_map = {a.session_id: a for a in active_activities}

        agent_router = _get_agent_router()

        sessions = []
        with get_db_session() as db:
            statement = select(ChatSession).filter_by(agent_id=agent_id)
            for s in db.exec(statement):
                is_active = s.session_id in active_session_ids
                status = "active" if is_active else "bound_inactive"
                activity = activity_map.get(s.session_id)
                last_spoke = None
                if activity and activity.last_spoke_at:
                    last_spoke = activity.last_spoke_at.isoformat()

                is_primary = (agent_router.get_session_primary_agent(s.session_id) == agent_id)

                all_agents = agent_router.get_session_all_agents(s.session_id)
                cohabitants = []
                for other_id in all_agents:
                    if other_id == agent_id:
                        continue
                    other_config = registry.get_agent(other_id) if registry.has_agent(other_id) else None
                    other_primary = (agent_router.get_session_primary_agent(s.session_id) == other_id)
                    other_status = "active"
                    cohabitants.append(CohabitantInfo(
                        agent_id=other_id,
                        display_name=other_config.display_name if other_config else other_id,
                        is_primary=other_primary,
                        status=other_status,
                    ))

                sessions.append(SessionAgentInfo(
                    session_id=s.session_id,
                    display_name=s.group_name or s.user_nickname or s.session_id,
                    agent_id=agent_id,
                    agent_display_name=config.display_name,
                    status=status,
                    is_primary=is_primary,
                    last_spoke_at=last_spoke,
                    cohabitants=cohabitants,
                ))
        return SessionsByAgentResponse(
            success=True,
            agent_id=agent_id,
            sessions=sessions,
        )
    except Exception as e:
        logger.error(f"获取智能体会话列表失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "获取智能体会话列表失败") from e

@router.post("/reload", response_model=ApiResponse[ReloadResponse])
async def reload_agents():
    """重新加载所有智能体配置"""
    try:
        registry = _get_registry()
        registry.reload()
        agents = registry.list_agents()
        return ReloadResponse(
            success=True,
            message=f"已重新加载 {len(agents)} 个智能体配置",
            total=len(agents),
        )
    except Exception as e:
        logger.error(f"重新加载智能体配置失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "重新加载智能体配置失败") from e

# ========== 子智能体监控 API ==========

@router.get("/subagent/records", response_model=ApiResponse[SubAgentListResponse])
async def list_subagent_records(
    agent_id: Optional[str] = None,
    subagent_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
):
    """获取子智能体执行记录"""
    try:
        with get_db_session() as db:
            query = db.query(SubAgentExecutionRecord)
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
            return SubAgentListResponse(success=True, total=len(data), data=data)
    except Exception as e:
        logger.error(f"获取子智能体记录失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "获取子智能体记录失败") from e

@router.get("/subagent/stats", response_model=ApiResponse[SubAgentStatsResponse])
async def get_subagent_stats():
    """获取子智能体执行统计"""
    try:
        with get_db_session() as db:
            rows = db.query(SubAgentExecutionRecord).all()
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
            return SubAgentStatsResponse(
                success=True,
                total_executions=len(rows),
                by_type=by_type,
                by_status=by_status,
                total_input_tokens=total_input,
                total_output_tokens=total_output,
                total_cache_hit_tokens=total_cache,
            )
    except Exception as e:
        logger.error(f"获取子智能体统计失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "获取子智能体统计失败") from e

# ========== 情绪-行为映射 API ==========

@router.get("/emotion-behavior-rules/{agent_id}", response_model=ApiResponse[EmotionBehaviorRulesResponse])
async def get_emotion_behavior_rules(agent_id: str):
    """获取智能体的情绪-行为映射规则"""
    try:
        registry = _get_registry()
        if not registry.has_agent(agent_id):
            raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_id}")
        config = registry.get_agent(agent_id)
        rules = [
            EmotionBehaviorRuleResponse(
                emotion_type=rule.emotion_type,
                intensity_threshold=rule.intensity_threshold,
                behavior_tendency=rule.behavior_tendency,
                reply_style_modifier=rule.reply_style_modifier,
            )
            for rule in config.emotion_behavior_map
        ]
        return EmotionBehaviorRulesResponse(success=True, agent_id=agent_id, rules=rules)
    except Exception as e:
        logger.error(f"获取情绪-行为映射规则失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "获取情绪-行为映射规则失败") from e

# ========== 批量查询 API ==========

@router.get("/batch/emotion", response_model=ApiResponse[BatchEmotionResponse])
async def batch_get_emotions():
    """批量获取所有智能体的情绪状态"""
    result: Dict[str, BatchEmotionItem] = {}
    try:
        registry = _get_registry()
        agents = registry.list_agents()
        for agent in agents:
            try:
                from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
                emotion_registry = AgentEmotionManagerRegistry()
                manager = emotion_registry.get_emotion_manager(agent.agent_id)
                if manager is None:
                    manager = EmotionManager(agent)
                state = manager.state
                dominant = state.get_dominant()
                result[agent.agent_id] = BatchEmotionItem(
                    emotions=state.emotions,
                    dominant_emotion=dominant,
                    dominant_emotion_label=EMOTION_LABELS_ZH.get(dominant, dominant),
                    emotion_labels=EMOTION_LABELS_ZH,
                )
            except Exception as e:
                logger.warning(f"批量获取情绪 — 智能体 {agent.agent_id} 失败: {e}")
        return BatchEmotionResponse(success=True, data=result)
    except Exception as e:
        logger.error(f"批量获取情绪状态失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "批量获取情绪状态失败") from e

@router.get("/batch/relationships", response_model=ApiResponse[BatchRelationshipResponse])
async def batch_get_relationships():
    """批量获取所有智能体的关系概览"""
    result: Dict[str, List[RelationshipItem]] = {}
    try:
        registry = _get_registry()
        agents = registry.list_agents()
        with get_db_session() as db:
            for agent in agents:
                try:
                    rows = db.query(AgentRelationship).filter(
                        AgentRelationship.agent_id == agent.agent_id
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
                    result[agent.agent_id] = items
                except Exception as e:
                    logger.warning(f"批量获取关系 — 智能体 {agent.agent_id} 失败: {e}")
                    result[agent.agent_id] = []
        return BatchRelationshipResponse(success=True, data=result)
    except Exception as e:
        logger.error(f"批量获取关系概览失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "批量获取关系概览失败") from e

@router.get("/batch/sessions", response_model=ApiResponse[BatchSessionCountResponse])
async def batch_get_session_counts():
    """批量获取各智能体的已绑定会话数量"""
    result: Dict[str, int] = {}
    try:
        registry = _get_registry()
        agents = registry.list_agents()
        agent_ids = [a.agent_id for a in agents]
        with get_db_session() as db:
            for aid in agent_ids:
                try:
                    count = db.query(ChatSession).filter(
                        ChatSession.agent_id == aid
                    ).count()
                    result[aid] = count
                except Exception as e:
                    logger.warning(f"批量获取会话数 — 智能体 {aid} 失败: {e}")
                    result[aid] = 0
        return BatchSessionCountResponse(success=True, data=result)
    except Exception as e:
        logger.error(f"批量获取会话数量失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "批量获取会话数量失败") from e

@router.get("/batch/subagent-latest", response_model=ApiResponse[BatchLatestSubAgentResponse])
async def batch_get_latest_subagent_records():
    """批量获取各智能体最近一条子智能体执行记录"""
    result: Dict[str, Optional[BatchLatestSubAgentItem]] = {}
    try:
        registry = _get_registry()
        agents = registry.list_agents()
        agent_ids = [a.agent_id for a in agents]
        with get_db_session() as db:
            for aid in agent_ids:
                try:
                    row = db.query(SubAgentExecutionRecord).filter(
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
                except Exception as e:
                    logger.warning(f"批量获取子智能体记录 — 智能体 {aid} 失败: {e}")
                    result[aid] = None
        return BatchLatestSubAgentResponse(success=True, data=result)
    except Exception as e:
        logger.error(f"批量获取子智能体记录失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, "批量获取子智能体记录失败") from e

# ========== 插件迁移协调 API ==========

@router.get("/migration/states", response_model=List[MigrationStateResponse])
async def get_migration_states():
    """获取所有插件的迁移状态。"""
    from src.maisaka.migration import MigrationCoordinator

    coordinator = MigrationCoordinator()
    states = coordinator.get_all_states()
    return [
        MigrationStateResponse(
            plugin_id=s.plugin_id,
            plugin_name=s.plugin_name,
            current_phase=s.current_phase.value,
            previous_phase=s.previous_phase.value,
            last_updated=s.last_updated,
            notes=s.notes,
        )
        for s in states
    ]

@router.post("/migration/{plugin_id}/advance", response_model=ApiResponse[MigrationAdvanceResponse])
async def advance_migration(plugin_id: str):
    """推进指定插件的迁移阶段。"""
    from src.maisaka.migration import MigrationCoordinator

    coordinator = MigrationCoordinator()
    state = coordinator.advance(plugin_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"未找到插件: {plugin_id}")

    return MigrationAdvanceResponse(
        success=True,
        plugin_id=state.plugin_id,
        current_phase=state.current_phase.value,
        previous_phase=state.previous_phase.value,
    )

# ---- 内心独白 API ----

@router.get("/monologue/{agent_id}", response_model=List[MonologueEventResponse])
async def get_monologue_events(agent_id: str, limit: int = 10):
    """获取智能体内心独白列表。"""
    from src.common.database.database_model import InnerMonologueEvent

    with get_db_session() as session:
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

# ---- 智能体画像 API ----

@router.get("/profile/{observer_id}/{target_id}", response_model=ApiResponse[AgentProfileResponse])
async def get_agent_profile(observer_id: str, target_id: str):
    """获取智能体画像。"""
    from src.maisaka.agent_interaction.memory.adapter import AgentMemoryAdapter
    from src.maisaka.agent_interaction.memory.profile import AgentProfileService
    from src.maisaka.agent_interaction.event_store import InteractionEventStore

    adapter = AgentMemoryAdapter()
    store = InteractionEventStore()
    service = AgentProfileService(adapter, store)

    profile = await service.get_profile(observer_id, target_id)

    return AgentProfileResponse(
        observer_agent_id=profile.observer_agent_id,
        target_agent_id=profile.target_agent_id,
        summary=profile.summary,
        traits=profile.traits,
        interaction_count=profile.interaction_count,
        emotion_tendency=profile.emotion_tendency,
        refresh_status=profile.refresh_status,
    )

# ── 智能体间交互事件 API ──

@router.get("/interactions/recent", response_model=List[InteractionEventResponse])
async def get_recent_interactions(limit: int = 20):
    """获取最近的智能体间交互事件。"""
    from src.maisaka.agent_interaction.event_store import InteractionEventStore

    store = InteractionEventStore()
    events = await store.get_recent_events(limit=limit)
    return [
        InteractionEventResponse(
            event_id=e.event_id,
            initiator_agent_id=e.initiator_agent_id,
            target_agent_id=e.target_agent_id,
            interaction_type=e.interaction_type,
            trigger_reason=e.trigger_reason,
            content_summary=e.content_summary,
            emotion_effects=e.emotion_effects,
            relationship_effect=e.relationship_effect,
            memory_write_status=e.memory_write_status,
            echo_depth=e.echo_depth,
            echo_parent_event_id=e.echo_parent_event_id,
            metadata=e.metadata,
            created_at=e.created_at.isoformat() if e.created_at else None,
        )
        for e in events
    ]

@router.get("/interactions/history", response_model=List[InteractionEventResponse])
async def query_interaction_history(
    agent_id: str = "",
    target_agent_id: str = "",
    interaction_type: str = "",
    time_start: Optional[str] = None,
    time_end: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """按条件查询智能体间交互历史。"""
    from datetime import datetime as dt

    from src.maisaka.agent_interaction.event_store import InteractionEventStore

    store = InteractionEventStore()
    ts = dt.fromisoformat(time_start) if time_start else None
    te = dt.fromisoformat(time_end) if time_end else None
    events = await store.query_events(
        agent_id=agent_id,
        target_agent_id=target_agent_id,
        interaction_type=interaction_type,
        time_start=ts,
        time_end=te,
        limit=limit,
        offset=offset,
    )
    return [
        InteractionEventResponse(
            event_id=e.event_id,
            initiator_agent_id=e.initiator_agent_id,
            target_agent_id=e.target_agent_id,
            interaction_type=e.interaction_type,
            trigger_reason=e.trigger_reason,
            content_summary=e.content_summary,
            emotion_effects=e.emotion_effects,
            relationship_effect=e.relationship_effect,
            memory_write_status=e.memory_write_status,
            echo_depth=e.echo_depth,
            echo_parent_event_id=e.echo_parent_event_id,
            metadata=e.metadata,
            created_at=e.created_at.isoformat() if e.created_at else None,
        )
        for e in events
    ]

# ---- 交互触发管理 API ----

@router.post("/interactions/trigger", response_model=ApiResponse[ManualTriggerResponse])
async def manual_trigger_interaction(req: ManualTriggerRequest):
    """管理员手动触发交互。"""
    from src.maisaka.agent_interaction.engine import InteractionEngine
    from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
    from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager
    from src.maisaka.agent_interaction.event_store import InteractionEventStore

    engine = InteractionEngine(
        emotion_registry=AgentEmotionManagerRegistry(),
        relationship_manager=AgentRelationshipManager(),
        event_store=InteractionEventStore(),
    )
    result = await engine.execute_manual(
        initiator_id=req.initiator_id,
        target_id=req.target_id,
        interaction_type=req.interaction_type,
        reason=req.reason,
    )
    return ManualTriggerResponse(
        success=result.success,
        event_id=result.event_id,
        error=result.error,
    )

@router.get("/interactions/config", response_model=ApiResponse[InteractionConfigResponse])
async def get_interaction_config():
    """获取交互触发配置。"""
    from src.config.config import global_config

    cfg = global_config.agent_interaction
    return InteractionConfigResponse(
        enabled=cfg.enabled,
        cooldown_minutes=cfg.cooldown_minutes,
        max_interactions_per_hour=cfg.max_interactions_per_hour,
        max_interactions_per_day=cfg.max_interactions_per_day,
        echo_enabled=cfg.echo_enabled,
        echo_max_depth=cfg.echo_max_depth,
        echo_decay_ratio=cfg.echo_decay_ratio,
        monologue_enabled=cfg.monologue_enabled,
        monologue_min_interval_minutes=cfg.monologue_min_interval_minutes,
        monologue_idle_threshold_minutes=cfg.monologue_idle_threshold_minutes,
        monologue_emotion_intensity_threshold=cfg.monologue_emotion_intensity_threshold,
    )

@router.get("/interactions/hotspots")
async def get_interaction_hotspots():
    """获取交互热点对（24小时内交互超过5次的智能体对）。"""
    from src.maisaka.agent_interaction.event_store import InteractionEventStore
    from datetime import datetime, timedelta

    store = InteractionEventStore()
    time_start = datetime.now() - timedelta(hours=24)
    events = await store.query_events(time_start=time_start, limit=200)

    pair_counts: dict[str, int] = {}
    for e in events:
        key = f"{e.initiator_agent_id}:{e.target_agent_id}"
        pair_counts[key] = pair_counts.get(key, 0) + 1

    hotspots = [
        {"pair": pair, "count": count}
        for pair, count in pair_counts.items()
        if count >= 5
    ]
    return {"hotspots": hotspots}

@router.get("/interactions/{event_id}", response_model=ApiResponse[InteractionEventResponse])
async def get_interaction_detail(event_id: str):
    """获取指定交互事件的详情。"""
    from src.maisaka.agent_interaction.event_store import InteractionEventStore

    store = InteractionEventStore()
    event = await store.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"交互事件不存在: {event_id}")
    return InteractionEventResponse(
        event_id=event.event_id,
        initiator_agent_id=event.initiator_agent_id,
        target_agent_id=event.target_agent_id,
        interaction_type=event.interaction_type,
        trigger_reason=event.trigger_reason,
        content_summary=event.content_summary,
        emotion_effects=event.emotion_effects,
        relationship_effect=event.relationship_effect,
        memory_write_status=event.memory_write_status,
        echo_depth=event.echo_depth,
        echo_parent_event_id=event.echo_parent_event_id,
        metadata=event.event_metadata,
        created_at=event.created_at.isoformat() if event.created_at else None,
    )

# ========== 智能体自主性 API ==========

@router.get("/autonomy/active/{session_id}", response_model=ApiResponse[ActiveAgentsResponse])
async def get_active_agents(session_id: str):
    """获取会话的活跃智能体列表。"""
    from src.maisaka.agent_autonomy.activity_store import AgentActivityStore

    store = AgentActivityStore()
    activities = store.get_active_agents(session_id)
    return ActiveAgentsResponse(
        success=True,
        session_id=session_id,
        data=[
            ActiveAgentItem(
                agent_id=a.agent_id,
                is_primary=a.is_primary,
                activation_reason=a.activation_reason,
                activated_at=a.activated_at.isoformat() if a.activated_at else None,
                last_spoke_at=a.last_spoke_at.isoformat() if a.last_spoke_at else None,
            )
            for a in activities
        ],
    )

@router.get("/autonomy/primary/{session_id}", response_model=ApiResponse[PrimaryAgentResponse])
async def get_primary_agent(session_id: str):
    """获取会话的主发言智能体。"""
    from src.maisaka.agent_autonomy.activity_store import AgentActivityStore

    store = AgentActivityStore()
    primary = store.get_primary_agent(session_id)
    return PrimaryAgentResponse(
        success=True,
        session_id=session_id,
        agent_id=primary.agent_id if primary else None,
        activation_reason=primary.activation_reason if primary else "",
        activated_at=primary.activated_at.isoformat() if primary and primary.activated_at else None,
    )

@router.post("/autonomy/switch-speaker", response_model=ApiResponse[SwitchSpeakerResponse])
async def switch_speaker(req: SwitchSpeakerRequest):
    """切换主发言智能体。"""
    from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.get_by_session(req.session_id)
    if orchestrator is None:
        raise AppError(ErrorCode.BIZ_NOT_FOUND, "未找到该会话的自主性编排器")

    from_id = orchestrator.get_primary_agent()
    from_agent_id = from_id.agent_id if from_id else ""

    success = await orchestrator.switch_primary_speaker(
        target_agent_id=req.target_agent_id,
        reason=req.reason,
    )
    return SwitchSpeakerResponse(
        success=success,
        session_id=req.session_id,
        from_agent_id=from_agent_id,
        to_agent_id=req.target_agent_id if success else "",
    )

@router.post("/autonomy/trigger-interjection", response_model=ApiResponse[TriggerInterjectionResponse])
async def trigger_interjection(req: TriggerInterjectionRequest):
    """手动触发插话。"""
    from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.get_by_session(req.session_id)
    if orchestrator is None:
        raise AppError(ErrorCode.BIZ_NOT_FOUND, "未找到该会话的自主性编排器")

    if req.agent_id not in [a.agent_id for a in orchestrator.get_active_agents()]:
        await orchestrator.activate_agent(req.agent_id, "manual_interjection")

    from src.maisaka.agent_autonomy.behavior_intent import BehaviorIntent
    intent = BehaviorIntent(
        intent_type="want_to_interject",
        intent_strength=100.0,
        intent_source="manual_trigger",
        source_description=f"手动触发: {req.reason}",
    )
    orchestrator.report_intent(req.agent_id, intent)

    return TriggerInterjectionResponse(
        success=True,
        session_id=req.session_id,
        agent_id=req.agent_id,
    )

@router.get("/autonomy/intents/{session_id}", response_model=ApiResponse[BehaviorIntentsResponse])
async def get_behavior_intents(session_id: str, limit: int = 50):
    """获取会话的行为意图列表。"""
    from src.common.database.database_model import AgentAutonomyBehaviorIntent

    with get_db_session() as db:
        rows = (
            db.query(AgentAutonomyBehaviorIntent)
            .filter(AgentAutonomyBehaviorIntent.session_id == session_id)
            .order_by(AgentAutonomyBehaviorIntent.created_at.desc())
            .limit(limit)
            .all()
        )
        return BehaviorIntentsResponse(
            success=True,
            session_id=session_id,
            data=[
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
            ],
        )

@router.get("/autonomy/interjection-events/{session_id}", response_model=ApiResponse[InterjectionEventsResponse])
async def get_interjection_events(session_id: str, limit: int = 50):
    """获取会话的插话事件列表。"""
    from src.common.database.database_model import AgentAutonomyInterjectionEvent

    with get_db_session() as db:
        rows = (
            db.query(AgentAutonomyInterjectionEvent)
            .filter(AgentAutonomyInterjectionEvent.session_id == session_id)
            .order_by(AgentAutonomyInterjectionEvent.created_at.desc())
            .limit(limit)
            .all()
        )
        return InterjectionEventsResponse(
            success=True,
            session_id=session_id,
            data=[
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
            ],
        )

@router.get("/autonomy/speaker-changes/{session_id}", response_model=ApiResponse[SpeakerChangesResponse])
async def get_speaker_changes(session_id: str, limit: int = 50):
    """获取会话的发言权变更记录。"""
    from src.common.database.database_model import AgentAutonomySpeakerChangeRecord

    with get_db_session() as db:
        rows = (
            db.query(AgentAutonomySpeakerChangeRecord)
            .filter(AgentAutonomySpeakerChangeRecord.session_id == session_id)
            .order_by(AgentAutonomySpeakerChangeRecord.created_at.desc())
            .limit(limit)
            .all()
        )
        return SpeakerChangesResponse(
            success=True,
            session_id=session_id,
            data=[
                SpeakerChangeItem(
                    record_id=r.record_id,
                    from_agent_id=r.from_agent_id,
                    to_agent_id=r.to_agent_id,
                    change_type=r.change_type,
                    change_reason=r.change_reason,
                    created_at=r.created_at.isoformat() if r.created_at else None,
                )
                for r in rows
            ],
        )

@router.get("/autonomy-logs", response_model=ApiResponse[AutonomyLogResponse])
async def get_autonomy_logs(
    agent_id: Optional[str] = None,
    event_type: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    """查询智能体自主性活动日志。"""
    import json
    from pathlib import Path

    log_dir = Path("logs")
    if not log_dir.exists():
        return AutonomyLogResponse()

    log_files = sorted(log_dir.glob("app_*.log.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not log_files:
        return AutonomyLogResponse()

    max_lines = 5000
    all_items: list[AutonomyLogItem] = []

    for log_file in log_files[:3]:
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-max_lines:]
        except Exception:
            continue

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            event = entry.get("event", "")
            if not isinstance(event, str) or "[Autonomy:" not in event:
                continue

            item = _parse_autonomy_log(entry, event)
            if item is None:
                continue

            if agent_id and item.agent_id != agent_id:
                continue
            if event_type and item.event_type != event_type:
                continue
            if start_time and item.timestamp < start_time:
                continue
            if end_time and item.timestamp > end_time:
                continue

            all_items.append(item)

    all_items.sort(key=lambda x: x.timestamp, reverse=True)

    total = len(all_items)
    start = (page - 1) * page_size
    end = start + page_size
    items = all_items[start:end]

    return AutonomyLogResponse(items=items, total=total, page=page, page_size=page_size)

def _parse_autonomy_log(entry: dict, event: str) -> Optional[AutonomyLogItem]:
    """解析 [Autonomy:{agent_id}] {event_type}: {detail} 格式日志。"""
    import re

    match = re.match(r"\[Autonomy:(\S+?)\]\s+(\S+?):\s+(.*)", event)
    if not match:
        return None

    agent_id = match.group(1)
    event_type = match.group(2)
    detail = match.group(3)

    timestamp = entry.get("timestamp", "")
    if isinstance(timestamp, (int, float)):
        from datetime import datetime
        timestamp = datetime.fromtimestamp(timestamp).isoformat()

    return AutonomyLogItem(
        agent_id=agent_id,
        event_type=event_type,
        detail=detail,
        timestamp=str(timestamp),
        session_id="",
        log_level=entry.get("level", "info"),
    )

@router.get("/vitality", response_model=ApiResponse[SessionVitalityResponse])
async def get_session_vitality(session_id: str):
    """查询会话智能体生命力状态（三态分类）。"""
    from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator
    from src.maisaka.agent.registry import AgentConfigRegistry

    registry = AgentConfigRegistry()
    orch = AgentOrchestrator.get_by_session(session_id)

    active_items: list[VitalityAgentItem] = []
    standby_items: list[VitalityAgentItem] = []
    dormant_items: list[VitalityAgentItem] = []

    def _get_display_name(agent_id: str) -> str:
        try:
            agent = registry.get_agent(agent_id)
            return agent.display_name
        except Exception:
            return agent_id

    # 活跃智能体
    if orch is not None:
        for agent in orch.get_active_agents():
            active_items.append(VitalityAgentItem(
                agent_id=agent.agent_id,
                display_name=_get_display_name(agent.agent_id),
                state="active",
                vitality_value=100.0,
            ))

        # 待命智能体
        for info in orch._vitality_manager.get_standby_agents(session_id):
            standby_items.append(VitalityAgentItem(
                agent_id=info.agent_id,
                display_name=_get_display_name(info.agent_id),
                state="standby",
                vitality_value=info.vitality_value,
                last_stimulus_at=info.last_stimulus_at.isoformat() if info.last_stimulus_at else None,
            ))

    # 沉睡智能体：绑定但非活跃且非待命
    try:
        agent_router = _get_agent_router()
        bound_agents = agent_router.get_session_all_agents(session_id)
        active_ids = {item.agent_id for item in active_items}
        standby_ids = {item.agent_id for item in standby_items}
        for agent_id in bound_agents:
            if agent_id not in active_ids and agent_id not in standby_ids:
                dormant_items.append(VitalityAgentItem(
                    agent_id=agent_id,
                    display_name=_get_display_name(agent_id),
                    state="dormant",
                    vitality_value=0.0,
                ))
    except Exception:
        pass

    return SessionVitalityResponse(
        success=True,
        session_id=session_id,
        active_agents=active_items,
        standby_agents=standby_items,
        dormant_agents=dormant_items,
    )

# ========== 状态互知 API ==========

@router.get("/state-awareness", response_model=ApiResponse[StateAwarenessResponse])
async def get_state_awareness(session_id: str):
    """查询会话智能体感知关系和摘要预览。"""
    from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

    orch = AgentOrchestrator.get_by_session(session_id)
    if orch is None:
        return StateAwarenessResponse(success=True, session_id=session_id)

    try:
        preview = orch._summary_generator.generate_preview(session_id)
    except Exception as exc:
        logger.warning(f"状态互知预览生成失败: session={session_id} error={exc}")
        preview = {"cohabitant_entries": [], "summary_texts": {}}

    entries = [
        CohabitantEntryItem(
            agent_id=e.get("agent_id", ""),
            display_name=e.get("display_name", ""),
            state=e.get("state", ""),
            vitality_level=e.get("vitality_level", ""),
            emotion_tendency=e.get("emotion_tendency", ""),
        )
        for e in preview.get("cohabitant_entries", [])
    ]

    summary_texts = preview.get("summary_texts", {})
    summary_preview = ""
    if summary_texts:
        first_observer = next(iter(summary_texts), "")
        summary_preview = summary_texts.get(first_observer, "")

    active_rules: list[Dict[str, Any]] = []
    try:
        from src.config.config import global_config

        cfg = global_config.agent_autonomy
        if cfg.state_awareness_enabled:
            rule_result = orch._rule_engine.evaluate_for_interjection(session_id)
            for rule_name in rule_result.triggered_rules:
                active_rules.append({"rule_name": rule_name, "active": True})
    except Exception:
        pass

    return StateAwarenessResponse(
        success=True,
        session_id=session_id,
        cohabitant_entries=entries,
        summary_preview=summary_preview,
        active_rules=active_rules,
    )