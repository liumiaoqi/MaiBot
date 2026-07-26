from src.plugin_runtime_v2.proto import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SendMessageRequest(_message.Message):
    __slots__ = ("session_id", "message_type", "text_content", "image_base64", "emoji_base64", "forward_message_id", "hybrid_payload")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    TEXT_CONTENT_FIELD_NUMBER: _ClassVar[int]
    IMAGE_BASE64_FIELD_NUMBER: _ClassVar[int]
    EMOJI_BASE64_FIELD_NUMBER: _ClassVar[int]
    FORWARD_MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    HYBRID_PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    message_type: str
    text_content: str
    image_base64: str
    emoji_base64: str
    forward_message_id: str
    hybrid_payload: str
    def __init__(self, session_id: _Optional[str] = ..., message_type: _Optional[str] = ..., text_content: _Optional[str] = ..., image_base64: _Optional[str] = ..., emoji_base64: _Optional[str] = ..., forward_message_id: _Optional[str] = ..., hybrid_payload: _Optional[str] = ...) -> None: ...

class SendMessageResponse(_message.Message):
    __slots__ = ("success", "error", "message_id")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    message_id: str
    def __init__(self, success: _Optional[bool] = ..., error: _Optional[str] = ..., message_id: _Optional[str] = ...) -> None: ...

class StorageGetRequest(_message.Message):
    __slots__ = ("key", "default_value")
    KEY_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_VALUE_FIELD_NUMBER: _ClassVar[int]
    key: str
    default_value: str
    def __init__(self, key: _Optional[str] = ..., default_value: _Optional[str] = ...) -> None: ...

class StorageGetResponse(_message.Message):
    __slots__ = ("found", "value", "error")
    FOUND_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    found: bool
    value: str
    error: str
    def __init__(self, found: _Optional[bool] = ..., value: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...

class StorageSetRequest(_message.Message):
    __slots__ = ("key", "value")
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    key: str
    value: str
    def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

class StorageSetResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: _Optional[bool] = ..., error: _Optional[str] = ...) -> None: ...

class StorageDeleteRequest(_message.Message):
    __slots__ = ("key",)
    KEY_FIELD_NUMBER: _ClassVar[int]
    key: str
    def __init__(self, key: _Optional[str] = ...) -> None: ...

class StorageDeleteResponse(_message.Message):
    __slots__ = ("deleted", "error")
    DELETED_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    deleted: bool
    error: str
    def __init__(self, deleted: _Optional[bool] = ..., error: _Optional[str] = ...) -> None: ...

class GetSessionInfoRequest(_message.Message):
    __slots__ = ("session_id",)
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    def __init__(self, session_id: _Optional[str] = ...) -> None: ...

class GetSessionInfoResponse(_message.Message):
    __slots__ = ("found", "session_id", "session_name", "platform", "is_group_session", "primary_agent_id", "error")
    FOUND_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_NAME_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    IS_GROUP_SESSION_FIELD_NUMBER: _ClassVar[int]
    PRIMARY_AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    found: bool
    session_id: str
    session_name: str
    platform: str
    is_group_session: bool
    primary_agent_id: str
    error: str
    def __init__(self, found: _Optional[bool] = ..., session_id: _Optional[str] = ..., session_name: _Optional[str] = ..., platform: _Optional[str] = ..., is_group_session: _Optional[bool] = ..., primary_agent_id: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...

class ToolDeclaration(_message.Message):
    __slots__ = ("name", "description", "parameters_schema", "output_schema")
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    OUTPUT_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    name: str
    description: str
    parameters_schema: str
    output_schema: str
    def __init__(self, name: _Optional[str] = ..., description: _Optional[str] = ..., parameters_schema: _Optional[str] = ..., output_schema: _Optional[str] = ...) -> None: ...

class EventDeclaration(_message.Message):
    __slots__ = ("name", "description", "event_schema")
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    EVENT_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    name: str
    description: str
    event_schema: str
    def __init__(self, name: _Optional[str] = ..., description: _Optional[str] = ..., event_schema: _Optional[str] = ...) -> None: ...

class RegisterComponentsRequest(_message.Message):
    __slots__ = ("plugin_id", "plugin_version", "tools", "events")
    PLUGIN_ID_FIELD_NUMBER: _ClassVar[int]
    PLUGIN_VERSION_FIELD_NUMBER: _ClassVar[int]
    TOOLS_FIELD_NUMBER: _ClassVar[int]
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    plugin_id: str
    plugin_version: str
    tools: _containers.RepeatedCompositeFieldContainer[ToolDeclaration]
    events: _containers.RepeatedCompositeFieldContainer[EventDeclaration]
    def __init__(self, plugin_id: _Optional[str] = ..., plugin_version: _Optional[str] = ..., tools: _Optional[_Iterable[_Union[ToolDeclaration, _Mapping]]] = ..., events: _Optional[_Iterable[_Union[EventDeclaration, _Mapping]]] = ...) -> None: ...

class RegisterComponentsResponse(_message.Message):
    __slots__ = ("accepted", "reasons")
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    REASONS_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    reasons: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, accepted: _Optional[bool] = ..., reasons: _Optional[_Iterable[str]] = ...) -> None: ...
