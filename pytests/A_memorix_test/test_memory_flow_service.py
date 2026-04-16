from types import SimpleNamespace

import pytest

from src.services import memory_flow_service as memory_flow_module


def test_person_fact_parse_fact_list_deduplicates_and_filters_short_items():
    raw = '["他喜欢猫", "他喜欢猫", "好", "", "他会弹吉他"]'

    result = memory_flow_module.PersonFactWritebackService._parse_fact_list(raw)

    assert result == ["他喜欢猫", "他会弹吉他"]


def test_person_fact_looks_ephemeral_detects_short_chitchat():
    assert memory_flow_module.PersonFactWritebackService._looks_ephemeral("哈哈")
    assert memory_flow_module.PersonFactWritebackService._looks_ephemeral("好的？")
    assert not memory_flow_module.PersonFactWritebackService._looks_ephemeral("她最近在学法语和钢琴")


def test_person_fact_resolve_target_person_for_private_chat(monkeypatch):
    class FakePerson:
        def __init__(self, person_id: str):
            self.person_id = person_id
            self.is_known = True

    service = memory_flow_module.PersonFactWritebackService.__new__(memory_flow_module.PersonFactWritebackService)
    monkeypatch.setattr(memory_flow_module, "is_bot_self", lambda platform, user_id: False)
    monkeypatch.setattr(memory_flow_module, "get_person_id", lambda platform, user_id: f"{platform}:{user_id}")
    monkeypatch.setattr(memory_flow_module, "Person", FakePerson)

    message = SimpleNamespace(session=SimpleNamespace(platform="qq", user_id="123", group_id=""))

    person = service._resolve_target_person(message)

    assert person is not None
    assert person.person_id == "qq:123"


@pytest.mark.asyncio
async def test_chat_summary_writeback_service_triggers_when_threshold_reached(monkeypatch):
    events: list[tuple[str, object]] = []

    monkeypatch.setattr(
        memory_flow_module,
        "global_config",
        SimpleNamespace(
            memory=SimpleNamespace(
                chat_summary_writeback_enabled=True,
                chat_summary_writeback_message_threshold=3,
                chat_summary_writeback_context_length=7,
            )
        ),
    )
    monkeypatch.setattr(memory_flow_module, "count_messages", lambda **kwargs: 5)

    async def fake_ingest_summary(**kwargs):
        events.append(("ingest_summary", kwargs))
        return SimpleNamespace(success=True, detail="ok")

    monkeypatch.setattr(memory_flow_module.memory_service, "ingest_summary", fake_ingest_summary)

    service = memory_flow_module.ChatSummaryWritebackService()
    message = SimpleNamespace(session_id="session-1", session=SimpleNamespace(user_id="user-1", group_id="group-1"))

    await service._handle_message(message)

    assert len(events) == 1
    _, payload = events[0]
    assert payload["external_id"] == "chat_auto_summary:session-1:5"
    assert payload["chat_id"] == "session-1"
    assert payload["text"] == ""
    assert payload["metadata"]["generate_from_chat"] is True
    assert payload["metadata"]["context_length"] == 7
    assert payload["metadata"]["trigger"] == "message_threshold"
    assert payload["user_id"] == "user-1"
    assert payload["group_id"] == "group-1"


@pytest.mark.asyncio
async def test_chat_summary_writeback_service_skips_when_threshold_not_reached(monkeypatch):
    called = False

    monkeypatch.setattr(
        memory_flow_module,
        "global_config",
        SimpleNamespace(
            memory=SimpleNamespace(
                chat_summary_writeback_enabled=True,
                chat_summary_writeback_message_threshold=6,
                chat_summary_writeback_context_length=9,
            )
        ),
    )
    monkeypatch.setattr(memory_flow_module, "count_messages", lambda **kwargs: 5)

    async def fake_ingest_summary(**kwargs):
        nonlocal called
        called = True
        return SimpleNamespace(success=True, detail="ok")

    monkeypatch.setattr(memory_flow_module.memory_service, "ingest_summary", fake_ingest_summary)

    service = memory_flow_module.ChatSummaryWritebackService()
    message = SimpleNamespace(session_id="session-1", session=SimpleNamespace(user_id="user-1", group_id="group-1"))

    await service._handle_message(message)

    assert called is False


@pytest.mark.asyncio
async def test_memory_automation_service_auto_starts_and_delegates():
    events: list[tuple[str, str]] = []

    class FakeFactWriteback:
        async def start(self):
            events.append(("start", "fact"))

        async def enqueue(self, message):
            events.append(("sent", message.session_id))

        async def shutdown(self):
            events.append(("shutdown", "fact"))

    class FakeChatSummaryWriteback:
        async def start(self):
            events.append(("start", "summary"))

        async def enqueue(self, message):
            events.append(("summary", message.session_id))

        async def shutdown(self):
            events.append(("shutdown", "summary"))

    service = memory_flow_module.MemoryAutomationService()
    service.fact_writeback = FakeFactWriteback()
    service.chat_summary_writeback = FakeChatSummaryWriteback()

    await service.on_message_sent(SimpleNamespace(session_id="session-1"))
    await service.shutdown()

    assert events == [
        ("start", "fact"),
        ("start", "summary"),
        ("sent", "session-1"),
        ("summary", "session-1"),
        ("shutdown", "summary"),
        ("shutdown", "fact"),
    ]


@pytest.mark.asyncio
async def test_memory_automation_service_on_incoming_message_auto_starts_only():
    events: list[tuple[str, str]] = []

    class FakeFactWriteback:
        async def start(self):
            events.append(("start", "fact"))

        async def enqueue(self, message):
            events.append(("sent", message.session_id))

        async def shutdown(self):
            events.append(("shutdown", "fact"))

    class FakeChatSummaryWriteback:
        async def start(self):
            events.append(("start", "summary"))

        async def enqueue(self, message):
            events.append(("summary", message.session_id))

        async def shutdown(self):
            events.append(("shutdown", "summary"))

    service = memory_flow_module.MemoryAutomationService()
    service.fact_writeback = FakeFactWriteback()
    service.chat_summary_writeback = FakeChatSummaryWriteback()

    await service.on_incoming_message(SimpleNamespace(session_id="session-1"))
    await service.shutdown()

    assert events == [
        ("start", "fact"),
        ("start", "summary"),
        ("shutdown", "summary"),
        ("shutdown", "fact"),
    ]
