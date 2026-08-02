from typing import Any

import pytest

from src.A_memorix.host_service import AMemorixHostService


class _FakeKernel:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def search_memory(self, request: Any) -> dict[str, Any]:
        self.requests.append(request)
        return {"summary": "", "hits": []}

@pytest.mark.asyncio
async def test_host_service_passes_shared_memory_session_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AMemorixHostService()
    fake_kernel = _FakeKernel()

    async def fake_ensure_kernel() -> _FakeKernel:
        return fake_kernel

    monkeypatch.setattr(service, "is_enabled", lambda: True)
    monkeypatch.setattr(service, "_ensure_kernel", fake_ensure_kernel)
    monkeypatch.setattr(service, "_read_config", lambda: {"global_memory_sharing_enabled": False})
    monkeypatch.setattr(
        "src.A_memorix.host_service.AMemorixConfigUtils.get_shared_memory_session_ids",
        lambda chat_id: {"session-a", "session-b"} if chat_id == "session-a" else {chat_id},
    )

    await service.invoke(
        "search_memory",
        {
            "query": "围巾",
            "limit": 3,
            "mode": "search",
            "chat_id": "session-a",
            "respect_filter": True,
        },
    )

    assert len(fake_kernel.requests) == 1
    request = fake_kernel.requests[0]
    assert request.chat_id == "session-a"
    assert set(request.shared_chat_ids) == {"session-a", "session-b"}


@pytest.mark.asyncio
async def test_host_service_global_memory_sharing_uses_global_search_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AMemorixHostService()
    fake_kernel = _FakeKernel()

    async def fake_ensure_kernel() -> _FakeKernel:
        return fake_kernel

    def fail_shared_group_lookup(chat_id: str) -> set[str]:
        raise AssertionError(f"全局共享开启时不应解析共享记忆组: {chat_id}")

    monkeypatch.setattr(service, "is_enabled", lambda: True)
    monkeypatch.setattr(service, "_ensure_kernel", fake_ensure_kernel)
    monkeypatch.setattr(service, "_read_config", lambda: {"global_memory_sharing_enabled": True})
    monkeypatch.setattr(
        "src.A_memorix.host_service.AMemorixConfigUtils.get_shared_memory_session_ids",
        fail_shared_group_lookup,
    )

    await service.invoke(
        "search_memory",
        {
            "query": "围巾",
            "limit": 3,
            "mode": "search",
            "chat_id": "session-a",
            "group_id": "group-a",
            "user_id": "user-a",
            "respect_filter": True,
        },
    )

    assert len(fake_kernel.requests) == 1
    request = fake_kernel.requests[0]
    assert request.chat_id == ""
    assert tuple(request.shared_chat_ids) == ()
    assert request.group_id == "group-a"
    assert request.user_id == "user-a"
