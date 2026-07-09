from __future__ import annotations

from typing import Any


class ServiceRegistry:
    def __init__(self) -> None:
        self._services: dict[str, Any] = {}

    def register(self, name: str, service: Any) -> None:
        self._services[name] = service

    def get(self, name: str) -> Any:
        if name not in self._services:
            raise KeyError(f"服务未注册: {name}")
        return self._services[name]

    def has(self, name: str) -> bool:
        return name in self._services


service_registry = ServiceRegistry()