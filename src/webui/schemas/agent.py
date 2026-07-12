from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

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

class CohabitantInfo(BaseModel):
    agent_id: str
    display_name: str
    is_primary: bool = False
    status: str = "bound_inactive"
    vitality_value: float = 0.0

class SessionAgentInfo(BaseModel):
    session_id: str
    display_name: str
    agent_id: str
    agent_display_name: str
    status: str = "bound_inactive"
    is_primary: bool = False
    last_spoke_at: Optional[str] = None
    vitality_value: float = 0.0
    cohabitants: List[CohabitantInfo] = Field(default_factory=list)

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

class EmotionBehaviorRuleResponse(BaseModel):
    emotion_type: str
    intensity_threshold: int
    behavior_tendency: str
    reply_style_modifier: str

class EmotionBehaviorRulesResponse(BaseModel):
    success: bool
    agent_id: str
    rules: List[EmotionBehaviorRuleResponse] = Field(default_factory=list)

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

class MonologueEventResponse(BaseModel):
    monologue_id: str
    agent_id: str
    emotion_snapshot: str
    content: str
    self_emotion_effect: str
    memory_references: str
    created_at: Optional[str] = None

class AgentProfileResponse(BaseModel):
    observer_agent_id: str
    target_agent_id: str
    summary: str
    traits: List[str] = []
    interaction_count: int = 0
    emotion_tendency: str = ""
    refresh_status: str = "pending"

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

class VitalityAgentItem(BaseModel):
    agent_id: str
    display_name: str = ""
    state: str = "active"
    vitality_value: float = 0.0
    last_stimulus_at: Optional[str] = None

class SessionVitalityResponse(BaseModel):
    success: bool
    session_id: str
    active_agents: List[VitalityAgentItem] = Field(default_factory=list)
    standby_agents: List[VitalityAgentItem] = Field(default_factory=list)
    dormant_agents: List[VitalityAgentItem] = Field(default_factory=list)

class CohabitantEntryItem(BaseModel):
    agent_id: str
    display_name: str
    state: str
    vitality_level: str
    emotion_tendency: str = ""

class StateAwarenessResponse(BaseModel):
    success: bool
    session_id: str
    cohabitant_entries: List[CohabitantEntryItem] = Field(default_factory=list)
    summary_preview: str = ""
    active_rules: List[Dict[str, Any]] = Field(default_factory=list)
