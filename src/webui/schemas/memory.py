from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

class NodeRequest(BaseModel):
    name: str = Field(..., min_length=1)

class NodeRenameRequest(BaseModel):
    old_name: str = Field(..., min_length=1)
    new_name: str = Field(..., min_length=1)

class EdgeCreateRequest(BaseModel):
    subject: str = Field(..., min_length=1)
    predicate: str = Field(..., min_length=1)
    object: str = Field(..., min_length=1)
    confidence: float = Field(1.0, ge=0.0)

class EdgeDeleteRequest(BaseModel):
    hash: str = ""
    subject: str = ""
    object: str = ""

class EdgeWeightRequest(BaseModel):
    hash: str = ""
    subject: str = ""
    object: str = ""
    weight: float = Field(..., ge=0.0)

class SourceDeleteRequest(BaseModel):
    source: str = Field(..., min_length=1)

class SourceBatchDeleteRequest(BaseModel):
    sources: list[str] = Field(default_factory=list)

class EpisodeRebuildRequest(BaseModel):
    source: str = ""
    sources: list[str] = Field(default_factory=list)
    all: bool = False

class EpisodeProcessPendingRequest(BaseModel):
    limit: int = Field(20, ge=1, le=200)
    max_retry: int = Field(3, ge=1, le=20)

class ProfileOverrideRequest(BaseModel):
    person_id: str = Field(..., min_length=1)
    override_text: str = ""
    updated_by: str = ""
    source: str = "webui"

class ProfileEvidenceCorrectRequest(BaseModel):
    evidence_type: str = Field(..., min_length=1)
    hash: str = Field(..., min_length=1)
    requested_by: str = "webui"
    reason: str = "profile_evidence_correction"
    refresh: bool = True
    limit: int = Field(12, ge=1, le=100)

class ImportChatTarget(BaseModel):
    """记忆导入可选择的聊天流。"""

    chat_id: str
    chat_name: str
    platform: Optional[str] = None
    group_id: Optional[str] = None
    user_id: Optional[str] = None
    account_id: Optional[str] = None
    scope: Optional[str] = None
    is_group: bool = False
    last_active_at: Optional[float] = None

class ImportChatTargetsResponse(BaseModel):
    success: bool
    data: list[ImportChatTarget]

class MemoryTimelineChat(BaseModel):
    chat_id: str
    chat_name: str
    platform: Optional[str] = None
    group_id: Optional[str] = None
    user_id: Optional[str] = None
    is_group: bool = False

class MemoryTimelineRange(BaseModel):
    time_start: Optional[float] = None
    time_end: Optional[float] = None
    min_time: Optional[float] = None
    max_time: Optional[float] = None

class MemoryTimelineJumpTarget(BaseModel):
    tab: str
    params: dict[str, Any] = Field(default_factory=dict)

class MemoryTimelineEvent(BaseModel):
    event_id: str
    event_type: str
    category: str
    occurred_at: float
    chat_id: str
    chat_name: str
    title: str
    summary: str
    object_count: int = 1
    key_id: str = ""
    source: str = ""
    attribution: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    jump_target: MemoryTimelineJumpTarget

class MemoryTimelineResponse(BaseModel):
    success: bool
    chat: MemoryTimelineChat
    range: MemoryTimelineRange
    items: list[MemoryTimelineEvent]
    summary: dict[str, Any]

class MaintainRequest(BaseModel):
    target: str = Field(..., min_length=1)
    hours: Optional[float] = None

class AutoSaveRequest(BaseModel):
    enabled: bool

class VectorRebuildRequest(BaseModel):
    dry_run: bool = False
    batch_size: int = Field(32, ge=1, le=512)
    include_relations: Optional[bool] = None

class MemoryConfigUpdateRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)

class MemoryRawConfigUpdateRequest(BaseModel):
    config: str = ""

class TuningApplyProfileRequest(BaseModel):
    profile: dict[str, Any] = Field(default_factory=dict)
    reason: str = "manual"
    validate_result: bool = Field(default=True, alias="validate")

class TuningApplyBestRequest(BaseModel):
    persist: bool = False
    validate_result: bool = Field(default=True, alias="validate")

class V5ActionRequest(BaseModel):
    target: str = Field(..., min_length=1)
    strength: Optional[float] = Field(default=None, ge=0.0)
    reason: str = ""
    updated_by: str = "webui"

class DeleteActionRequest(BaseModel):
    mode: str = Field(..., min_length=1)
    selector: dict[str, Any] | str = Field(default_factory=dict)
    reason: str = ""
    requested_by: str = "webui"

class DeleteRestoreRequest(BaseModel):
    operation_id: str = ""
    mode: str = ""
    selector: dict[str, Any] | str = Field(default_factory=dict)
    reason: str = ""
    requested_by: str = "webui"

class DeletePurgeRequest(BaseModel):
    grace_hours: Optional[float] = Field(default=None, ge=0.0)
    limit: int = Field(1000, ge=1, le=5000)

class MemoryCorrectionPreviewRequest(BaseModel):
    request_text: str = Field(..., min_length=1)
    scope: str = "person_profile"
    person_id: str = ""
    person_keyword: str = ""
    chat_id: str = ""
    limit: Optional[int] = Field(default=None, ge=1)
    requested_by: str = "webui"
    reason: str = ""

class MemoryCorrectionExecuteRequest(BaseModel):
    plan_id: str = Field(..., min_length=1)
    confirmed: bool = True
    requested_by: str = "webui"
    reason: str = ""

class MemoryCorrectionRollbackRequest(BaseModel):
    requested_by: str = "webui"
    reason: str = ""

class FeedbackRollbackRequest(BaseModel):
    requested_by: str = "webui"
    reason: str = ""
