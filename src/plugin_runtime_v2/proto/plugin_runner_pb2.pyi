from src.plugin_runtime_v2.proto import common_pb2 as _common_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class InvokeToolRequest(_message.Message):
    __slots__ = ("tool_name", "args", "timeout_ms")
    TOOL_NAME_FIELD_NUMBER: _ClassVar[int]
    ARGS_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    tool_name: str
    args: str
    timeout_ms: int
    def __init__(self, tool_name: _Optional[str] = ..., args: _Optional[str] = ..., timeout_ms: _Optional[int] = ...) -> None: ...

class InvokeToolResponse(_message.Message):
    __slots__ = ("success", "result", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    result: str
    error: str
    def __init__(self, success: _Optional[bool] = ..., result: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...
