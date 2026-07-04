"""智能体管理 API 路由"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sqlmodel import select

from src.common.database.database import get_db_session
from src.common.database.database_model import ChatSession
from src.common.logger import get_logger
from src.maisaka.agent.config import AgentConfig
from src.maisaka.agent.emotion import EMOTION_LABELS_ZH, EMOTION_TYPES, EmotionManager
from src.maisaka.agent.registry import AgentConfigRegistry
from src.maisaka.agent.router import AgentRouter
from src.common.database.database_model import AgentRelationship
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
        state = manager.get_state()
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