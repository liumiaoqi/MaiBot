"""ReplyerServiceAdapter — 将 replyer_manager 包装为 ReplyerServicePort 接口。"""

from typing import Any, Optional


class ReplyerServiceAdapter:
    def __init__(self, replyer_manager: Any) -> None:
        self._replyer_manager = replyer_manager

    def get_replyer(
        self,
        chat_stream: Optional[Any] = None,
        chat_id: Optional[str] = None,
        request_type: str = "replyer",
        replyer_type: str = "default",
    ) -> Optional[Any]:
        return self._replyer_manager.get_replyer(
            chat_stream=chat_stream,
            chat_id=chat_id,
            request_type=request_type,
            replyer_type=replyer_type,
        )
