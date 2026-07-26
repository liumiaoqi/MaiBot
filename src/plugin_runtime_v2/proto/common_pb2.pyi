from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RunnerMessage(_message.Message):
    __slots__ = ("hello", "event", "heartbeat")
    HELLO_FIELD_NUMBER: _ClassVar[int]
    EVENT_FIELD_NUMBER: _ClassVar[int]
    HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    hello: HelloPayload
    event: EventPayload
    heartbeat: HeartbeatResponse
    def __init__(self, hello: _Optional[_Union[HelloPayload, _Mapping]] = ..., event: _Optional[_Union[EventPayload, _Mapping]] = ..., heartbeat: _Optional[_Union[HeartbeatResponse, _Mapping]] = ...) -> None: ...

class HostMessage(_message.Message):
    __slots__ = ("hello_response", "event_ack", "heartbeat", "shutdown")
    HELLO_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    EVENT_ACK_FIELD_NUMBER: _ClassVar[int]
    HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    SHUTDOWN_FIELD_NUMBER: _ClassVar[int]
    hello_response: HelloResponse
    event_ack: EventAck
    heartbeat: HeartbeatRequest
    shutdown: ShutdownRequest
    def __init__(self, hello_response: _Optional[_Union[HelloResponse, _Mapping]] = ..., event_ack: _Optional[_Union[EventAck, _Mapping]] = ..., heartbeat: _Optional[_Union[HeartbeatRequest, _Mapping]] = ..., shutdown: _Optional[_Union[ShutdownRequest, _Mapping]] = ...) -> None: ...

class HelloPayload(_message.Message):
    __slots__ = ("runner_id", "sdk_version", "session_token", "scopes", "runner_listen_address")
    RUNNER_ID_FIELD_NUMBER: _ClassVar[int]
    SDK_VERSION_FIELD_NUMBER: _ClassVar[int]
    SESSION_TOKEN_FIELD_NUMBER: _ClassVar[int]
    SCOPES_FIELD_NUMBER: _ClassVar[int]
    RUNNER_LISTEN_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    runner_id: str
    sdk_version: str
    session_token: str
    scopes: _containers.RepeatedScalarFieldContainer[str]
    runner_listen_address: str
    def __init__(self, runner_id: _Optional[str] = ..., sdk_version: _Optional[str] = ..., session_token: _Optional[str] = ..., scopes: _Optional[_Iterable[str]] = ..., runner_listen_address: _Optional[str] = ...) -> None: ...

class HelloResponse(_message.Message):
    __slots__ = ("accepted", "host_version", "reason", "rejected_scopes")
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    HOST_VERSION_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    REJECTED_SCOPES_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    host_version: str
    reason: str
    rejected_scopes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, accepted: _Optional[bool] = ..., host_version: _Optional[str] = ..., reason: _Optional[str] = ..., rejected_scopes: _Optional[_Iterable[str]] = ...) -> None: ...

class HeartbeatRequest(_message.Message):
    __slots__ = ("timestamp_ms",)
    TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    timestamp_ms: int
    def __init__(self, timestamp_ms: _Optional[int] = ...) -> None: ...

class HeartbeatResponse(_message.Message):
    __slots__ = ("timestamp_ms",)
    TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    timestamp_ms: int
    def __init__(self, timestamp_ms: _Optional[int] = ...) -> None: ...

class ShutdownRequest(_message.Message):
    __slots__ = ("reason", "drain_timeout_ms")
    REASON_FIELD_NUMBER: _ClassVar[int]
    DRAIN_TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    reason: str
    drain_timeout_ms: int
    def __init__(self, reason: _Optional[str] = ..., drain_timeout_ms: _Optional[int] = ...) -> None: ...

class EventPayload(_message.Message):
    __slots__ = ("event_name", "payload")
    EVENT_NAME_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    event_name: str
    payload: str
    def __init__(self, event_name: _Optional[str] = ..., payload: _Optional[str] = ...) -> None: ...

class EventAck(_message.Message):
    __slots__ = ("received",)
    RECEIVED_FIELD_NUMBER: _ClassVar[int]
    received: bool
    def __init__(self, received: _Optional[bool] = ...) -> None: ...
