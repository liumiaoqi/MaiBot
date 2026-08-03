"""MF-P0-002 验收：memory_flow_service 游标恢复不再抛 AttributeError。

对应 tasks.md 2.4：_load_last_trigger_message_count 调用
get_memory_service_port().get_paragraphs_by_source 正常恢复聊天摘要写回游标。
"""

from unittest.mock import AsyncMock, MagicMock

from src.services.memory_flow_service import ChatSummaryWritebackService


async def test_load_last_trigger_message_count_restores_cursor(monkeypatch) -> None:
    """port 返回段落 → 恢复 trigger_message_count 游标。"""
    import src.services.memory_flow_service as mfs

    port = MagicMock()
    port.get_paragraphs_by_source = AsyncMock(return_value=[
        {
            "hash": "h1",
            "content": "摘要",
            "metadata": {"trigger_message_count": 42},
            "created_at": 1000.0,
        },
    ])
    monkeypatch.setattr(mfs, "get_memory_service_port", lambda: port)

    service = ChatSummaryWritebackService()
    restored = await service._load_last_trigger_message_count(
        session_id="chat_1",
        total_message_count=100,
    )
    assert restored == 42
    port.get_paragraphs_by_source.assert_called_once_with("chat_summary:chat_1")


async def test_load_last_trigger_message_count_no_paragraphs_returns_zero(monkeypatch) -> None:
    """无段落 → 返回 0（从头触发）。"""
    import src.services.memory_flow_service as mfs

    port = MagicMock()
    port.get_paragraphs_by_source = AsyncMock(return_value=[])
    monkeypatch.setattr(mfs, "get_memory_service_port", lambda: port)

    service = ChatSummaryWritebackService()
    restored = await service._load_last_trigger_message_count(
        session_id="chat_1",
        total_message_count=50,
    )
    assert restored == 0


async def test_load_last_trigger_message_count_failure_degrades(monkeypatch) -> None:
    """port 抛异常 → 降级返回 0，不冒泡 AttributeError。"""
    import src.services.memory_flow_service as mfs

    port = MagicMock()
    port.get_paragraphs_by_source = AsyncMock(side_effect=RuntimeError("端口异常"))
    monkeypatch.setattr(mfs, "get_memory_service_port", lambda: port)

    service = ChatSummaryWritebackService()
    restored = await service._load_last_trigger_message_count(
        session_id="chat_1",
        total_message_count=50,
    )
    assert restored == 0


async def test_legacy_summary_without_trigger_count_aligns(monkeypatch) -> None:
    """旧摘要无 trigger_message_count → 对齐当前计数（避免重复写）。"""
    import src.services.memory_flow_service as mfs

    port = MagicMock()
    port.get_paragraphs_by_source = AsyncMock(return_value=[
        {"hash": "h1", "content": "旧摘要", "metadata": {}, "created_at": 500.0},
    ])
    monkeypatch.setattr(mfs, "get_memory_service_port", lambda: port)

    service = ChatSummaryWritebackService()
    restored = await service._load_last_trigger_message_count(
        session_id="chat_1",
        total_message_count=80,
    )
    assert restored == 80
