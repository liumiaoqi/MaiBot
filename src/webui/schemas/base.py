from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    data: T
    message: str = ""


class ErrorResponse(BaseModel):
    error_code: str
    error_message: str
    details: Optional[dict[str, Any]] = None


def wrap_response(data: Any, message: str = "") -> dict[str, Any]:
    return ApiResponse(data=data, message=message).model_dump()