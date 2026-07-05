"""智能体管理 API 路由"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sqlmodel import select

from src.common.database.database import get_db_session
from src.common.database.database_model import AgentRelationship, ChatSession, SubAgentExecutionRecord
from src.common.logger import get_logger
from src.maisaka.agent.config import AgentConfig
from src.maisaka.agent.emotion import EMOTION_LABELS_ZH, EmotionManager
from src.maisaka.agent.registry import AgentConfigRegistry
from src.maisaka.agent.router import AgentRouter

from src.maisaka.relationship.level import RelationshipLevel
from src.webui.dependencies import require_auth

logger = get_logger("webui.agent")

router = APIRouter(prefix="/agent", tags=["Agent"], dependencies=[Depends(require_auth)])


def _get_registry() -> AgentConfigRegistry:
    return AgentConfigRegistry()


def _get_router() -> AgentRouter:
    return AgentRouter(_get_registry())


class EmotionBaselineResponse(BaseModel):
    emotions: Dict[str, int] = Field(default_factory=dict, description="情绪基线值")
    labels: Dict[str, str] = Field(default_factory=dict, description="情绪中文标签")


class InternalRelationshipResponse(BaseModel):
    target_agent_id: str
    relationship_type: str
    attitude: str
    interaction_style: str = ""
    mention_tendency: float = 0.3
    anti_mechanization: str = ""


class AgentConfigResponse(BaseModel):
    agent_id: str
    display_name: str
    personality: str = ""
    reply_style: str = ""
    is_default: bool = False
    color: str = "#9b59b6"
    emotion_baseline: Dict[str, int] = Field(default_factory=dict)
    emotion_decay_rate: float = 0.12
    relationship_growth_rate: float = 1.0
    talk_value_modifier: float = 1.0
    idle_backoff_modifier: float = 1.0
    memory_focus_areas: List[str] = Field(default_factory=list)
    internal_relationships: List[InternalRelationshipResponse] = Field(default_factory=list)
    anti_mechanization_rules: List[str] = Field(default_factory=list)


class AgentListResponse(BaseModel):
    success: bool
    total: int
    data: List[AgentConfigResponse]


class AgentDetailResponse(BaseModel):
    success: bool
    data: AgentConfigResponse


class SessionBindingResponse(BaseModel):
    success: bool
    session_id: str
    agent_id: Optional[str] = None
    display_name: Optional[str] = None


class BindSessionRequest(BaseModel):
    agent_id: str = Field(..., description="要绑定的智能体ID")


class BatchBindItem(BaseModel):
    session_id: str = Field(..., description="会话ID")
    agent_id: str = Field(..., description="要绑定的智能体ID")


class BatchBindRequest(BaseModel):
    bindings: List[BatchBindItem] = Field(..., description="批量绑定列表")


class BatchBindError(BaseModel):
    session_id: str
    error: str


class BatchBindResponse(BaseModel):
    success: bool
    total: int
    succeeded: int
    failed: int
    errors: List[BatchBindError] = Field(default_factory=list)


class BindGroupRequest(BaseModel):
    group_id: str = Field(..., description="群ID")
    agent_id: str = Field(..., description="要绑定的智能体ID")


class GroupBindingResponse(BaseModel):
    success: bool
    group_id: str
    agent_id: str
    display_name: Optional[str] = None


class GroupBindingsListResponse(BaseModel):
    success: bool
    bindings: Dict[str, str]


class SessionAgentInfo(BaseModel):
    session_id: str
    display_name: str
    agent_id: str
    agent_display_name: str


class SessionsByAgentResponse(BaseModel):
    success: bool
    agent_id: str
    sessions: List[SessionAgentInfo]


class ReloadResponse(BaseModel):
    success: bool
    message: str
    total: int


class EmotionStateResponse(BaseModel):
    success: bool
    agent_id: str
    emotions: Dict[str, float] = Field(default_factory=dict)
    dominant_emotion: str = "calm"
    dominant_emotion_label: str = "平静"
    emotion_labels: Dict[str, str] = Field(default_factory=dict)


class RelationshipSummaryResponse(BaseModel):
    success: bool
    agent_id: str
    relationships: List[Dict[str, Any]] = Field(default_factory=list)


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


@router.get("/list", response_model=AgentListResponse)
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
        raise HTTPException(status_code=500, detail="获取智能体列表失败") from e


@router.get("/{agent_id}", response_model=AgentDetailResponse)
async def get_agent_detail(agent_id: str):
    """获取指定智能体详细配置"""
    try:
        registry = _get_registry()
        if not registry.has_agent(agent_id):
            raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_id}")
        config = registry.get_agent(agent_id)
        return AgentDetailResponse(success=True, data=_config_to_response(config))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取智能体详情失败: {e}")
        raise HTTPException(status_code=500, detail="获取智能体详情失败") from e


@router.get("/emotion/{agent_id}", response_model=EmotionStateResponse)
async def get_agent_emotion(agent_id: str):
    """获取指定智能体当前情绪状态"""
    try:
        registry = _get_registry()
        if not registry.has_agent(agent_id):
            raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_id}")
        config = registry.get_agent(agent_id)
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取智能体情绪状态失败: {e}")
        raise HTTPException(status_code=500, detail="获取智能体情绪状态失败") from e


@router.get("/relationship/{agent_id}", response_model=RelationshipSummaryResponse)
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取智能体关系概览失败: {e}")
        raise HTTPException(status_code=500, detail="获取智能体关系概览失败") from e


@router.get("/binding/session/{session_id}", response_model=SessionBindingResponse)
async def get_session_binding(session_id: str):
    """获取会话绑定的智能体"""
    try:
        agent_router = _get_router()
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
        raise HTTPException(status_code=500, detail="获取会话绑定失败") from e


@router.put("/binding/session/{session_id}", response_model=SessionBindingResponse)
async def bind_session_agent(session_id: str, request: BindSessionRequest):
    """绑定会话到指定智能体"""
    try:
        agent_router = _get_router()
        try:
            agent_router.bind_session(session_id, request.agent_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        with get_db_session() as db:
            statement = select(ChatSession).filter_by(session_id=session_id).limit(1)
            db_session = db.exec(statement).first()
            if db_session:
                db_session.agent_id = request.agent_id
                db.add(db_session)

        registry = _get_registry()
        config = registry.get_agent(request.agent_id)
        return SessionBindingResponse(
            success=True,
            session_id=session_id,
            agent_id=request.agent_id,
            display_name=config.display_name,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"绑定会话智能体失败: {e}")
        raise HTTPException(status_code=500, detail="绑定会话智能体失败") from e


@router.delete("/binding/session/{session_id}", response_model=SessionBindingResponse)
async def unbind_session_agent(session_id: str):
    """解除会话的智能体绑定"""
    try:
        agent_router = _get_router()
        agent_router.unbind_session(session_id)
        return SessionBindingResponse(success=True, session_id=session_id)
    except Exception as e:
        logger.error(f"解除会话绑定失败: {e}")
        raise HTTPException(status_code=500, detail="解除会话绑定失败") from e


@router.put("/binding/batch", response_model=BatchBindResponse)
async def batch_bind_sessions(request: BatchBindRequest):
    """批量绑定会话到指定智能体"""
    registry = _get_registry()
    agent_router = _get_router()
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
            with get_db_session() as db:
                statement = select(ChatSession).filter_by(session_id=item.session_id).limit(1)
                db_session = db.exec(statement).first()
                if db_session:
                    db_session.agent_id = item.agent_id
                    db.add(db_session)
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


@router.get("/binding/group", response_model=GroupBindingsListResponse)
async def list_group_bindings():
    """列出所有群-智能体绑定"""
    try:
        agent_router = _get_router()
        return GroupBindingsListResponse(
            success=True,
            bindings=agent_router.list_group_bindings(),
        )
    except Exception as e:
        logger.error(f"获取群绑定列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取群绑定列表失败") from e


@router.put("/binding/group", response_model=GroupBindingResponse)
async def bind_group_agent(request: BindGroupRequest):
    """绑定群到指定智能体"""
    try:
        agent_router = _get_router()
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"绑定群智能体失败: {e}")
        raise HTTPException(status_code=500, detail="绑定群智能体失败") from e


@router.delete("/binding/group/{group_id}", response_model=GroupBindingResponse)
async def unbind_group_agent(group_id: str):
    """解除群的智能体绑定"""
    try:
        agent_router = _get_router()
        agent_router.unbind_group(group_id)
        return GroupBindingResponse(success=True, group_id=group_id, agent_id="")
    except Exception as e:
        logger.error(f"解除群绑定失败: {e}")
        raise HTTPException(status_code=500, detail="解除群绑定失败") from e


@router.get("/sessions/{agent_id}", response_model=SessionsByAgentResponse)
async def get_sessions_by_agent(agent_id: str):
    """获取使用指定智能体的所有会话"""
    try:
        registry = _get_registry()
        if not registry.has_agent(agent_id):
            raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_id}")
        config = registry.get_agent(agent_id)

        sessions = []
        with get_db_session() as db:
            statement = select(ChatSession).filter_by(agent_id=agent_id)
            for s in db.exec(statement):
                sessions.append(SessionAgentInfo(
                    session_id=s.session_id,
                    display_name=s.group_name or s.user_nickname or s.session_id,
                    agent_id=agent_id,
                    agent_display_name=config.display_name,
                ))
        return SessionsByAgentResponse(
            success=True,
            agent_id=agent_id,
            sessions=sessions,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取智能体会话列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取智能体会话列表失败") from e


@router.post("/reload", response_model=ReloadResponse)
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
        raise HTTPException(status_code=500, detail="重新加载智能体配置失败") from e


# ========== 子智能体监控 API ==========


class SubAgentRecordResponse(BaseModel):
    id: int
    subagent_id: str
    agent_id: str
    subagent_type: str
    session_id: Optional[str] = None
    lifecycle: str
    status: str
    trigger_type: str
    trigger_reason: str
    fork_context_captured: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit_tokens: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: str = ""
    result_summary: str = ""


class SubAgentListResponse(BaseModel):
    success: bool
    total: int
    data: List[SubAgentRecordResponse]


class SubAgentStatsResponse(BaseModel):
    success: bool
    total_executions: int
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_status: Dict[str, int] = Field(default_factory=dict)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_hit_tokens: int = 0


@router.get("/subagent/records", response_model=SubAgentListResponse)
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
        raise HTTPException(status_code=500, detail="获取子智能体记录失败") from e


@router.get("/subagent/stats", response_model=SubAgentStatsResponse)
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
        raise HTTPException(status_code=500, detail="获取子智能体统计失败") from e


# ========== 情绪-行为映射 API ==========


class EmotionBehaviorRuleResponse(BaseModel):
    emotion_type: str
    intensity_threshold: int
    behavior_tendency: str
    reply_style_modifier: str


class EmotionBehaviorRulesResponse(BaseModel):
    success: bool
    agent_id: str
    rules: List[EmotionBehaviorRuleResponse] = Field(default_factory=list)


@router.get("/emotion-behavior-rules/{agent_id}", response_model=EmotionBehaviorRulesResponse)
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取情绪-行为映射规则失败: {e}")
        raise HTTPException(status_code=500, detail="获取情绪-行为映射规则失败") from e


# ========== 批量查询 API ==========


class BatchEmotionItem(BaseModel):
    emotions: Dict[str, float] = Field(default_factory=dict)
    dominant_emotion: str = "calm"
    dominant_emotion_label: str = "平静"
    emotion_labels: Dict[str, str] = Field(default_factory=dict)


class BatchEmotionResponse(BaseModel):
    success: bool
    data: Dict[str, BatchEmotionItem] = Field(default_factory=dict)


class RelationshipItem(BaseModel):
    user_id: str
    level: int
    level_name: str
    score: float
    total_interactions: int


class BatchRelationshipResponse(BaseModel):
    success: bool
    data: Dict[str, List[RelationshipItem]] = Field(default_factory=dict)


class BatchSessionCountResponse(BaseModel):
    success: bool
    data: Dict[str, int] = Field(default_factory=dict)


class BatchLatestSubAgentItem(BaseModel):
    id: int
    subagent_id: str
    agent_id: str
    subagent_type: str
    status: str
    completed_at: Optional[str] = None
    result_summary: str = ""


class BatchLatestSubAgentResponse(BaseModel):
    success: bool
    data: Dict[str, Optional[BatchLatestSubAgentItem]] = Field(default_factory=dict)


@router.get("/batch/emotion", response_model=BatchEmotionResponse)
async def batch_get_emotions():
    """批量获取所有智能体的情绪状态"""
    result: Dict[str, BatchEmotionItem] = {}
    try:
        registry = _get_registry()
        agents = registry.list_agents()
        for agent in agents:
            try:
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
        raise HTTPException(status_code=500, detail="批量获取情绪状态失败") from e


@router.get("/batch/relationships", response_model=BatchRelationshipResponse)
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
        raise HTTPException(status_code=500, detail="批量获取关系概览失败") from e


@router.get("/batch/sessions", response_model=BatchSessionCountResponse)
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
        raise HTTPException(status_code=500, detail="批量获取会话数量失败") from e


@router.get("/batch/subagent-latest", response_model=BatchLatestSubAgentResponse)
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
        raise HTTPException(status_code=500, detail="批量获取子智能体记录失败") from e


# ========== 插件迁移协调 API ==========


class MigrationStateResponse(BaseModel):
    plugin_id: str
    plugin_name: str
    current_phase: str
    previous_phase: str
    last_updated: float = 0.0
    notes: str = ""


class MigrationAdvanceResponse(BaseModel):
    success: bool
    plugin_id: str
    current_phase: str
    previous_phase: str


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


@router.post("/migration/{plugin_id}/advance", response_model=MigrationAdvanceResponse)
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


class MonologueEventResponse(BaseModel):
    monologue_id: str
    agent_id: str
    emotion_snapshot: str
    content: str
    self_emotion_effect: str
    memory_references: str
    created_at: Optional[str] = None


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


class AgentProfileResponse(BaseModel):
    observer_agent_id: str
    target_agent_id: str
    summary: str
    traits: List[str] = []
    interaction_count: int = 0
    emotion_tendency: str = ""
    refresh_status: str = "pending"


@router.get("/profile/{observer_id}/{target_id}", response_model=AgentProfileResponse)
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


class InteractionEventResponse(BaseModel):
    event_id: str
    initiator_agent_id: str
    target_agent_id: str
    interaction_type: str
    trigger_reason: str
    content_summary: str
    emotion_effects: str
    relationship_effect: float
    memory_write_status: str
    echo_depth: int
    echo_parent_event_id: str
    metadata: str
    created_at: Optional[str] = None


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


class ManualTriggerRequest(BaseModel):
    initiator_id: str
    target_id: str
    interaction_type: str
    reason: str = ""


class ManualTriggerResponse(BaseModel):
    success: bool
    event_id: str = ""
    error: str = ""


class InteractionConfigResponse(BaseModel):
    enabled: bool = True
    cooldown_minutes: int = 30
    max_interactions_per_hour: int = 2
    max_interactions_per_day: int = 8
    echo_enabled: bool = True
    echo_max_depth: int = 3
    echo_decay_ratio: float = 0.5
    monologue_enabled: bool = True
    monologue_min_interval_minutes: int = 15
    monologue_idle_threshold_minutes: int = 30
    monologue_emotion_intensity_threshold: int = 40


@router.post("/interactions/trigger", response_model=ManualTriggerResponse)
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


@router.get("/interactions/config", response_model=InteractionConfigResponse)
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


@router.get("/interactions/{event_id}", response_model=InteractionEventResponse)
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


class ActiveAgentItem(BaseModel):
    agent_id: str
    is_primary: bool = False
    activation_reason: str = ""
    activated_at: Optional[str] = None
    last_spoke_at: Optional[str] = None


class ActiveAgentsResponse(BaseModel):
    success: bool
    session_id: str
    data: List[ActiveAgentItem] = Field(default_factory=list)


class PrimaryAgentResponse(BaseModel):
    success: bool
    session_id: str
    agent_id: Optional[str] = None
    activation_reason: str = ""
    activated_at: Optional[str] = None


class SwitchSpeakerRequest(BaseModel):
    session_id: str = Field(..., description="会话ID")
    target_agent_id: str = Field(..., description="目标智能体ID")
    reason: str = "manual_switch"


class SwitchSpeakerResponse(BaseModel):
    success: bool
    session_id: str
    from_agent_id: str = ""
    to_agent_id: str = ""


class TriggerInterjectionRequest(BaseModel):
    session_id: str = Field(..., description="会话ID")
    agent_id: str = Field(..., description="插话智能体ID")
    reason: str = "manual_trigger"


class TriggerInterjectionResponse(BaseModel):
    success: bool
    session_id: str
    agent_id: str = ""
    error: str = ""


class BehaviorIntentItem(BaseModel):
    intent_id: str
    agent_id: str
    intent_type: str
    intent_strength: float
    intent_source: str
    source_description: str
    status: str
    created_at: Optional[str] = None


class BehaviorIntentsResponse(BaseModel):
    success: bool
    session_id: str
    data: List[BehaviorIntentItem] = Field(default_factory=list)


class InterjectionEventItem(BaseModel):
    event_id: str
    agent_id: str
    primary_agent_id: str
    interjection_type: str
    trigger_reason: str
    intent_strength: float
    content_summary: str
    created_at: Optional[str] = None


class InterjectionEventsResponse(BaseModel):
    success: bool
    session_id: str
    data: List[InterjectionEventItem] = Field(default_factory=list)


class SpeakerChangeItem(BaseModel):
    record_id: str
    from_agent_id: str
    to_agent_id: str
    change_type: str
    change_reason: str
    created_at: Optional[str] = None


class SpeakerChangesResponse(BaseModel):
    success: bool
    session_id: str
    data: List[SpeakerChangeItem] = Field(default_factory=list)


@router.get("/autonomy/active/{session_id}", response_model=ActiveAgentsResponse)
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


@router.get("/autonomy/primary/{session_id}", response_model=PrimaryAgentResponse)
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


@router.post("/autonomy/switch-speaker", response_model=SwitchSpeakerResponse)
async def switch_speaker(req: SwitchSpeakerRequest):
    """切换主发言智能体。"""
    from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.get_by_session(req.session_id)
    if orchestrator is None:
        raise HTTPException(status_code=404, detail="未找到该会话的自主性编排器")

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


@router.post("/autonomy/trigger-interjection", response_model=TriggerInterjectionResponse)
async def trigger_interjection(req: TriggerInterjectionRequest):
    """手动触发插话。"""
    from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.get_by_session(req.session_id)
    if orchestrator is None:
        raise HTTPException(status_code=404, detail="未找到该会话的自主性编排器")

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


@router.get("/autonomy/intents/{session_id}", response_model=BehaviorIntentsResponse)
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


@router.get("/autonomy/interjection-events/{session_id}", response_model=InterjectionEventsResponse)
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


@router.get("/autonomy/speaker-changes/{session_id}", response_model=SpeakerChangesResponse)
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


class AutonomyLogItem(BaseModel):
    agent_id: str = ""
    event_type: str = ""
    detail: str = ""
    timestamp: str = ""
    session_id: str = ""
    log_level: str = "info"


class AutonomyLogResponse(BaseModel):
    items: List[AutonomyLogItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50


@router.get("/autonomy-logs", response_model=AutonomyLogResponse)
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