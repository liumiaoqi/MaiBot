from typing import Any

from .codes import ERROR_CODE_HTTP_STATUS, ErrorCode


class AppError(Exception):
    error_code: ErrorCode
    error_message: str
    details: dict[str, Any] | None
    http_status: int

    def __init__(
        self,
        error_code: ErrorCode,
        error_message: str = "",
        details: dict[str, Any] | None = None,
        http_status: int | None = None,
    ) -> None:
        self.error_code = error_code
        self.error_message = error_message or error_code.value
        self.details = details
        self.http_status = http_status if http_status is not None else ERROR_CODE_HTTP_STATUS.get(error_code, 500)
        super().__init__(self.error_message)