from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseAdminHandler(ABC):
    """Admin Handler 基类 — 消灭 Kernel 内的字符串分发 if/elif 链。"""

    @abstractmethod
    async def handle(self, action: str, **kwargs) -> Dict[str, Any]:
        """处理 Admin API 请求，子类重写实现分发逻辑。"""

    def _unsupported(self, domain: str, action: str) -> Dict[str, Any]:
        return {"success": False, "error": f"不支持的 {domain} action: {action}"}

    @staticmethod
    def _str_action(action: str) -> str:
        return str(action or "").strip().lower()

    def _require_initialized(self, *stores) -> Dict[str, Any] | None:
        """检查依赖是否就绪，未就绪时返回错误字典。"""
        for store in stores:
            if store is None:
                return {"success": False, "error": "运行时未初始化"}
        return None