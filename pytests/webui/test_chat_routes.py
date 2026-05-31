from contextlib import contextmanager
from typing import Any, Iterator

import pytest

from src.webui.routers.chat import routes


class _DetachedGuardPerson:
    def __init__(self) -> None:
        self.closed = False
        self.person_id = "person-1"
        self.user_id = "user-1"
        self.person_name = "Test User"
        self.user_nickname = "Test Nickname"
        self.is_known = True
        self.platform = "qq"

    def __getattribute__(self, name: str) -> Any:
        if name not in {"closed", "__dict__", "__class__", "__getattribute__"}:
            if object.__getattribute__(self, "closed"):
                raise RuntimeError("person attribute accessed after session closed")
        return object.__getattribute__(self, name)


class _FakeExecResult:
    def __init__(self, person: _DetachedGuardPerson) -> None:
        self.person = person

    def all(self) -> list[_DetachedGuardPerson]:
        return [self.person]


class _FakeSession:
    def __init__(self, person: _DetachedGuardPerson) -> None:
        self.person = person

    def exec(self, statement: Any) -> _FakeExecResult:
        del statement
        return _FakeExecResult(self.person)


@pytest.mark.asyncio
async def test_get_persons_by_platform_serializes_before_session_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    person = _DetachedGuardPerson()

    @contextmanager
    def fake_get_db_session() -> Iterator[_FakeSession]:
        try:
            yield _FakeSession(person)
        finally:
            person.closed = True

    monkeypatch.setattr(routes, "get_db_session", fake_get_db_session)

    response = await routes.get_persons_by_platform(platform="qq", limit=50)

    assert response == {
        "success": True,
        "persons": [
            {
                "person_id": "person-1",
                "user_id": "user-1",
                "person_name": "Test User",
                "nickname": "Test Nickname",
                "is_known": True,
                "platform": "qq",
                "display_name": "Test User",
            }
        ],
        "total": 1,
    }
