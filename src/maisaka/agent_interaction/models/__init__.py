from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class InteractionEventCreate(BaseModel):
    initiator_agent_id: str
    target_agent_id: str
    interaction_type: str
    trigger_reason: str = ""
    content_summary: str = ""
    emotion_effects: str = "{}"
    relationship_effect: float = 0.0
    memory_write_status: str = "skipped"
    echo_depth: int = 0
    echo_parent_event_id: str = ""
    metadata: str = "{}"


class InteractionEventRead(BaseModel):
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
    created_at: Optional[datetime] = None


class InteractionCooldownRead(BaseModel):
    agent_pair_key: str
    last_interaction_at: Optional[datetime] = None
    interaction_count_hourly: int = 0
    interaction_count_daily: int = 0
    hourly_reset_at: Optional[datetime] = None
    daily_reset_at: Optional[datetime] = None


class InnerMonologueEventRead(BaseModel):
    monologue_id: str
    agent_id: str
    emotion_snapshot: str
    content: str
    self_emotion_effect: str
    memory_references: str
    created_at: Optional[datetime] = None


class AgentInteractionRelationshipCreate(BaseModel):
    agent_id: str
    target_agent_id: str
    score: float = 0.0
    relationship_type: str = ""
    attitude: str = ""


class AgentInteractionRelationshipRead(BaseModel):
    id: int
    agent_id: str
    target_agent_id: str
    score: float
    relationship_type: str
    attitude: str
    interaction_count: int
    last_interaction_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None