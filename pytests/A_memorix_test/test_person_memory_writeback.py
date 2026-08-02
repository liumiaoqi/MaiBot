from types import SimpleNamespace

import pytest

from src.person_info import person_info as person_info_module


class _FakeMemoryServicePort:
    def __init__(self) -> None:
        self.calls = []

    async def observe(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(success=True, detail="", stored_ids=["p1"])


@pytest.mark.asyncio
async def test_store_person_memory_from_answer_writes_person_fact(monkeypatch):
    class FakePerson:
        def __init__(self, person_id: str):
            self.person_id = person_id
            self.person_name = "Alice"
            self.is_known = True

    session = SimpleNamespace(platform="qq", user_id="10001", group_id="", session_id="session-1")
    fake_port = _FakeMemoryServicePort()
    monkeypatch.setattr(person_info_module, "get_session_info", lambda chat_id: session)
    monkeypatch.setattr(person_info_module, "get_person_id_by_person_name", lambda person_name: "person-1")
    monkeypatch.setattr(person_info_module, "Person", FakePerson)
    monkeypatch.setattr(person_info_module, "get_memory_service_port", lambda: fake_port)

    await person_info_module.store_person_memory_from_answer("Alice", "她喜欢猫和爵士乐", "session-1")

    assert len(fake_port.calls) == 1
    payload = fake_port.calls[0]
    assert payload["source_id"].startswith("person_fact:person-1:")
    assert "person_fact" in payload["tags"]
    assert payload["session_id"] == "session-1"
    assert payload["metadata"]["person_id"] == "person-1"
    assert payload["participants"] == ["Alice"]
    assert payload["metadata"]["user_id"] == "10001"
    assert payload["metadata"]["group_id"] == ""


@pytest.mark.asyncio
async def test_store_person_memory_from_answer_prefers_explicit_person_id(monkeypatch):
    class FakePerson:
        def __init__(self, person_id: str):
            self.person_id = person_id
            self.person_name = "Alice"
            self.is_known = True

    session = SimpleNamespace(platform="qq", user_id="10001", group_id="group-1", session_id="session-1")
    fake_port = _FakeMemoryServicePort()
    monkeypatch.setattr(person_info_module, "get_session_info", lambda chat_id: session)
    monkeypatch.setattr(person_info_module, "get_person_id_by_person_name", lambda person_name: "wrong-person")
    monkeypatch.setattr(person_info_module, "Person", FakePerson)
    monkeypatch.setattr(person_info_module, "get_memory_service_port", lambda: fake_port)

    await person_info_module.store_person_memory_from_answer(
        "Alice",
        "Alice 长期使用青轴键盘",
        "session-1",
        person_id="person-target",
    )

    assert len(fake_port.calls) == 1
    payload = fake_port.calls[0]
    assert payload["source_id"].startswith("person_fact:person-target:")
    assert payload["metadata"]["person_id"] == "person-target"


@pytest.mark.asyncio
async def test_store_person_memory_from_answer_skips_unknown_person(monkeypatch):
    class FakePerson:
        def __init__(self, person_id: str):
            self.person_id = person_id
            self.person_name = "Unknown"
            self.is_known = False

    session = SimpleNamespace(platform="qq", user_id="10001", group_id="", session_id="session-1")
    fake_port = _FakeMemoryServicePort()
    monkeypatch.setattr(person_info_module, "get_session_info", lambda chat_id: session)
    monkeypatch.setattr(person_info_module, "get_person_id_by_person_name", lambda person_name: "person-1")
    monkeypatch.setattr(person_info_module, "Person", FakePerson)
    monkeypatch.setattr(person_info_module, "get_memory_service_port", lambda: fake_port)

    await person_info_module.store_person_memory_from_answer("Alice", "她喜欢猫和爵士乐", "session-1")

    assert fake_port.calls == []


@pytest.mark.asyncio
async def test_store_person_memory_from_answer_skips_empty_content(monkeypatch):
    fake_port = _FakeMemoryServicePort()
    monkeypatch.setattr(person_info_module, "get_memory_service_port", lambda: fake_port)

    await person_info_module.store_person_memory_from_answer("Alice", "   ", "session-1")

    assert fake_port.calls == []
