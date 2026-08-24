"""ZG-25 测试共享夹具。"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.core.token_meter.service as svc
from src.core.token_meter import TokenMeter, _set_instance


@pytest.fixture(autouse=True)
def _wire_token_meter():
    """ZG-N6：确保 TokenMeter 单例已接线（token_estimator 薄委托层需要）。"""
    original = svc._instance
    _set_instance(TokenMeter())
    yield
    svc._instance = original


@pytest.fixture(autouse=True)
def _reset_session_generations():
    """ZG-25 升级：清理适配层 session generation 计数器，避免测试间污染。"""
    from src.maisaka.context import compaction_adapter

    original = dict(compaction_adapter._session_generations)
    compaction_adapter._session_generations.clear()
    yield
    compaction_adapter._session_generations.clear()
    compaction_adapter._session_generations.update(original)


def make_assistant_message(content: str, timestamp: datetime | None = None) -> MagicMock:
    """构造轻量 AssistantMessage 替身（避免 dataclass slots 限制）。"""
    msg = MagicMock()
    msg.__class__.__name__ = "AssistantMessage"
    msg.content = content
    msg.processed_plain_text = content
    msg.role = "assistant"
    msg.timestamp = timestamp or datetime.now()
    msg.tool_calls = []
    msg.count_in_context = True
    return msg


def make_user_message(content: str, timestamp: datetime | None = None) -> MagicMock:
    """构造轻量 UserMessage 替身。"""
    msg = MagicMock()
    msg.__class__.__name__ = "SessionBackedMessage"
    msg.content = content
    msg.processed_plain_text = content
    msg.role = "user"
    msg.timestamp = timestamp or datetime.now()
    msg.tool_calls = []
    msg.count_in_context = True
    return msg


def make_mock_llm_service(summary_text: str = "这是摘要") -> MagicMock:
    """构造 mock LLMService，generate_response_with_messages 返回摘要。"""
    service = MagicMock()
    result = MagicMock()
    result.response = summary_text
    service.generate_response_with_messages = AsyncMock(return_value=result)
    return service


def make_mock_llm_service_raising(exc: Exception) -> MagicMock:
    """构造 mock LLMService，generate_response_with_messages 抛异常。"""
    service = MagicMock()
    service.generate_response_with_messages = AsyncMock(side_effect=exc)
    return service


def make_long_history(count: int = 20, text_size: int = 100) -> list:
    """构造超阈值 selected_history（交替 user/assistant，每条 text_size 字符）。"""
    history = []
    base_ts = datetime(2026, 8, 17, 10, 0, 0)
    for i in range(count):
        content = f"消息{i}_" + "x" * text_size
        if i % 2 == 0:
            history.append(make_user_message(content, timestamp=base_ts))
        else:
            history.append(make_assistant_message(content, timestamp=base_ts))
    return history


@pytest.fixture
def compaction_config():
    from src.maisaka.context.compaction import CompactionConfig

    return CompactionConfig(
        enable=True,
        threshold_ratio=0.5,
        retain_ratio=0.2,
        min_segment_size=4,
        min_segment_tokens=100,
        timeout_ms=5000,
        summary_max_tokens=200,
    )


@pytest.fixture
def disabled_config():
    from src.maisaka.context.compaction import CompactionConfig

    return CompactionConfig(enable=False)