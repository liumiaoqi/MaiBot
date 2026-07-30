"""ReplyerServiceAdapter — 将 replyer_manager 包装为 ReplyerServicePort 接口。"""

import time
from typing import Any, Optional

from src.core.service_manager.types import HealthCheckResult


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

    async def health_probe(self) -> HealthCheckResult:
        """检查回复器服务是否可用。

        验证 replyer_manager 已注入且 get_replyer 可调用。快速返回（≤5s）。
        """
        now = time.monotonic()
        if self._replyer_manager is None:
            return HealthCheckResult(
                alive=False, timestamp=now, detail="replyer_manager 为 None"
            )
        if not callable(getattr(self._replyer_manager, "get_replyer", None)):
            return HealthCheckResult(
                alive=False, timestamp=now, detail="replyer_manager.get_replyer 不可调用"
            )
        return HealthCheckResult(
            alive=True, timestamp=now, detail="回复器服务可用"
        )
