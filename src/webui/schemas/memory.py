from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

class NodeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(..., min_length=1)

class NodeRenameRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    old_name: str = Field(..., min_length=1)
    new_name: str = Field(..., min_length=1)

class EdgeCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    subject: str = Field(..., min_length=1)
    predicate: str = Field(..., min_length=1)
    object: str = Field(..., min_length=1)
    confidence: float = Field(1.0, ge=0.0)

class EdgeDeleteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    hash: str = ""
    subject: str = ""
    object: str = ""

class EdgeWeightRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    hash: str = ""
    subject: str = ""
    object: str = ""
    weight: float = Field(..., ge=0.0)

class SourceDeleteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    source: str = Field(..., min_length=1)

class SourceBatchDeleteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    sources: list[str] = Field(default_factory=list)

class EpisodeRebuildRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    source: str = ""
    sources: list[str] = Field(default_factory=list)
    all: bool = False

class EpisodeProcessPendingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    limit: int = Field(20, ge=1, le=200)
    max_retry: int = Field(3, ge=1, le=20)

class ProfileOverrideRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    person_id: str = Field(..., min_length=1)
    override_text: str = ""
    updated_by: str = ""
    source: str = "webui"

class ProfileEvidenceCorrectRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    evidence_type: str = Field(..., min_length=1)
    hash: str = Field(..., min_length=1)
    requested_by: str = "webui"
    reason: str = "profile_evidence_correction"
    refresh: bool = True
    limit: int = Field(12, ge=1, le=100)

class ImportChatTarget(BaseModel):
    """记忆导入可选择的聊天流。"""

    model_config = ConfigDict(extra='forbid')

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
    model_config = ConfigDict(extra='forbid')

    success: bool
    data: list[ImportChatTarget]

class MemoryTimelineChat(BaseModel):
    model_config = ConfigDict(extra='forbid')

    chat_id: str
    chat_name: str
    platform: Optional[str] = None
    group_id: Optional[str] = None
    user_id: Optional[str] = None
    is_group: bool = False

class MemoryTimelineRange(BaseModel):
    model_config = ConfigDict(extra='forbid')

    time_start: Optional[float] = None
    time_end: Optional[float] = None
    min_time: Optional[float] = None
    max_time: Optional[float] = None

class MemoryTimelineJumpTarget(BaseModel):
    model_config = ConfigDict(extra='forbid')

    tab: str
    params: dict[str, Any] = Field(default_factory=dict)

class MemoryTimelineEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')

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
    model_config = ConfigDict(extra='forbid')

    success: bool
    chat: MemoryTimelineChat
    range: MemoryTimelineRange
    items: list[MemoryTimelineEvent]
    summary: dict[str, Any]

class MaintainRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    target: str = Field(..., min_length=1)
    hours: Optional[float] = None

class AutoSaveRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    enabled: bool

class VectorRebuildRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    dry_run: bool = False
    batch_size: int = Field(32, ge=1, le=512)
    include_relations: Optional[bool] = None

class MemoryConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    config: dict[str, Any] = Field(default_factory=dict)

class MemoryRawConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    config: str = ""

class TuningApplyProfileRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    profile: dict[str, Any] = Field(default_factory=dict)
    reason: str = "manual"
    validate_result: bool = Field(default=True, alias="validate")

class TuningApplyBestRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    persist: bool = False
    validate_result: bool = Field(default=True, alias="validate")

class V5ActionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    target: str = Field(..., min_length=1)
    strength: Optional[float] = Field(default=None, ge=0.0)
    reason: str = ""
    updated_by: str = "webui"

class DeleteActionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    mode: str = Field(..., min_length=1)
    selector: dict[str, Any] | str = Field(default_factory=dict)
    reason: str = ""
    requested_by: str = "webui"

class DeleteRestoreRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    operation_id: str = ""
    mode: str = ""
    selector: dict[str, Any] | str = Field(default_factory=dict)
    reason: str = ""
    requested_by: str = "webui"

class DeletePurgeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    grace_hours: Optional[float] = Field(default=None, ge=0.0)
    limit: int = Field(1000, ge=1, le=5000)

class MemoryCorrectionPreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    request_text: str = Field(..., min_length=1)
    scope: str = "person_profile"
    person_id: str = ""
    person_keyword: str = ""
    chat_id: str = ""
    limit: Optional[int] = Field(default=None, ge=1)
    requested_by: str = "webui"
    reason: str = ""

class MemoryCorrectionExecuteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    plan_id: str = Field(..., min_length=1)
    confirmed: bool = True
    requested_by: str = "webui"
    reason: str = ""

class MemoryCorrectionRollbackRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    requested_by: str = "webui"
    reason: str = ""

class FeedbackRollbackRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    requested_by: str = "webui"
    reason: str = ""
