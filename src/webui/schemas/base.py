from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(extra='forbid')

    code: int = 0
    data: T
    message: str = ""


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    error_code: str
    error_message: str
    details: Optional[dict[str, Any]] = None


def wrap_response(data: Any, message: str = "") -> dict[str, Any]:
    return ApiResponse(data=data, message=message).model_dump()
