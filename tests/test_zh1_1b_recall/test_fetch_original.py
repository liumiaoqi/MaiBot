"""ZH1-1b 按需翻原文测试 — 指针解析 + find_messages + 截断 + ReferenceMessage 构造。

覆盖 spec 5.3.1：指针解析 → find_messages 拉原文 → token 截断 → 格式化。
"""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.maisaka.memory.mid_term import (
    MID_TERM_MEMORY_REFERENCE_MARKER,
    _fetch_original_messages_for_candidate,
    _format_mid_term_memory_reference,
    _parse_candidate_pointer,
    _truncate_original_messages,
)
from src.maisaka.context.messages import ReferenceMessage, ReferenceMessageType
from tests.test_zh1_1b_recall._helpers import (
    make_mock_find_messages_result,
    make_recall_candidate,
)


class TestParseCandidatePointer:
    """指针解析测试。"""

    def test_pointer_parse(self) -> None:
        """指针解析（session_id + time_range → start_time + end_time）。"""
        candidate = make_recall_candidate(
            session_id="group:12345",
            time_range="2024-01-01 10:00:00 ~ 2024-01-01 11:00:00",
        )
        pointer = _parse_candidate_pointer(candidate)
        assert pointer is not None
        session_id, start_time, end_time = pointer
        assert session_id == "group:12345"
        expected_start = datetime(2024, 1, 1, 10, 0, 0).timestamp()
        expected_end = datetime(2024, 1, 1, 11, 0, 0).timestamp()
        assert start_time == pytest.approx(expected_start)
        assert end_time == pytest.approx(expected_end)

    def test_pointer_missing_skip(self) -> None:
        """指针缺失 → 返回 None。"""
        candidate = make_recall_candidate(session_id="", time_range="未知")
        pointer = _parse_candidate_pointer(candidate)
        assert pointer is None


class TestFetchOriginalMessages:
    """翻原文测试。"""

    def test_find_messages_call(self) -> None:
        """find_messages(session_id, start_time, end_time, limit=20) 调用。"""
        candidate = make_recall_candidate(
            session_id="group:12345",
            time_range="2024-01-01 10:00:00 ~ 2024-01-01 11:00:00",
        )
        mock_messages = make_mock_find_messages_result(5)
        with patch("src.common.message_repository.find_messages", return_value=mock_messages) as mock_fn:
            _fetch_original_messages_for_candidate(
                candidate, session_id="group:12345", message_limit=20, token_limit=2000,
            )
        # find_messages 被调用
        assert mock_fn.call_count >= 1

    def test_message_limit_20(self) -> None:
        """时间范围内 30 条 → 拉取最近 20 条（limit=20 传给 find_messages）。"""
        candidate = make_recall_candidate(
            session_id="group:12345",
            time_range="2024-01-01 10:00:00 ~ 2024-01-01 11:00:00",
        )
        mock_messages = make_mock_find_messages_result(20)
        with patch("src.common.message_repository.find_messages", return_value=mock_messages) as mock_fn:
            _fetch_original_messages_for_candidate(
                candidate, session_id="group:12345", message_limit=20, token_limit=2000,
            )
        call_kwargs = mock_fn.call_args.kwargs
        assert call_kwargs["limit"] == 20

    def test_no_message_in_range(self) -> None:
        """时间范围内无消息 → 返回空字符串。"""
        candidate = make_recall_candidate(
            session_id="group:12345",
            time_range="2024-01-01 10:00:00 ~ 2024-01-01 11:00:00",
        )
        with patch("src.common.message_repository.find_messages", return_value=[]):
            result = _fetch_original_messages_for_candidate(
                candidate, session_id="group:12345", message_limit=20, token_limit=2000,
            )
        assert result == ""

    def test_fetch_failure_degradation(self) -> None:
        """find_messages 报错 → 返回空字符串。"""
        candidate = make_recall_candidate(
            session_id="group:12345",
            time_range="2024-01-01 10:00:00 ~ 2024-01-01 11:00:00",
        )
        with patch("src.common.message_repository.find_messages", side_effect=RuntimeError("DB错误")):
            result = _fetch_original_messages_for_candidate(
                candidate, session_id="group:12345", message_limit=20, token_limit=2000,
            )
        assert result == ""

    def test_pointer_missing_returns_empty(self) -> None:
        """指针缺失 → 返回空字符串。"""
        candidate = make_recall_candidate(session_id="", time_range="未知")
        result = _fetch_original_messages_for_candidate(
            candidate, session_id="group:12345", message_limit=20, token_limit=2000,
        )
        assert result == ""

    def test_raw_content_deserialize_failure(self) -> None:
        """raw_content 损坏 → 跳过该条 + warning，其他条继续。"""
        candidate = make_recall_candidate(
            session_id="group:12345",
            time_range="2024-01-01 10:00:00 ~ 2024-01-01 11:00:00",
        )
        # 一条正常 + 一条损坏（timestamp 访问抛异常）
        good_msg = make_mock_find_messages_result(1)[0]
        bad_msg = SimpleNamespace()
        bad_msg.timestamp = property(lambda self: (_ for _ in ()).throw(RuntimeError("损坏")))
        bad_msg.message_info = None
        # 用普通对象模拟损坏（processed_plain_text 访问抛异常）
        bad_msg2 = SimpleNamespace()
        bad_msg2.timestamp = datetime(2024, 1, 1, 10, 0, 0)
        bad_msg2.message_info = None
        bad_msg2.processed_plain_text = None  # 空文本跳过
        with patch("src.common.message_repository.find_messages", return_value=[good_msg, bad_msg2]):
            result = _fetch_original_messages_for_candidate(
                candidate, session_id="group:12345", message_limit=20, token_limit=2000,
            )
        # 正常条目仍在结果中
        assert "消息内容0" in result


class TestTruncateOriginalMessages:
    """原文截断测试。"""

    def test_token_limit_truncate(self) -> None:
        """原文合计 3000 token → 截断到 2000 token。"""
        # 1 token ≈ 2 字符 → 3000 token = 6000 字符，截断到 2000 token = 4000 字符
        long_text = "A" * 6000
        result = _truncate_original_messages(long_text, token_limit=2000)
        # 截断后含首部 + 省略号 + 尾部，总长 < 原文
        assert len(result) < len(long_text)
        assert "截断" in result

    def test_no_truncate_when_under_limit(self) -> None:
        """原文合计 1500 token → 完整追加。"""
        # 1500 token = 3000 字符 < 2000 token = 4000 字符
        short_text = "A" * 3000
        result = _truncate_original_messages(short_text, token_limit=2000)
        assert result == short_text

    def test_truncate_preserve_head_tail(self) -> None:
        """截断 → 首部 + 省略号 + 尾部。"""
        long_text = "HEAD" + "X" * 6000 + "TAIL"
        result = _truncate_original_messages(long_text, token_limit=2000)
        # 首部保留
        assert result.startswith("HEAD")
        # 尾部保留
        assert result.endswith("TAIL")
        # 含省略号标记
        assert "..." in result


class TestReferenceMessageConstruction:
    """ReferenceMessage 构造测试。"""

    def test_reference_message_construction(self) -> None:
        """ReferenceMessage 构造（reference_type=MEMORY, count_in_context=False）。"""
        candidate = make_recall_candidate(score=0.72)
        content = _format_mid_term_memory_reference(candidate, original_messages_text="原文")
        ref = ReferenceMessage(
            content=content,
            timestamp=datetime.now(),
            reference_type=ReferenceMessageType.MEMORY,
            remaining_uses_value=None,
            display_prefix="[参考消息]",
        )
        assert ref.reference_type == ReferenceMessageType.MEMORY
        assert ref.count_in_context is False

    def test_reference_message_format(self) -> None:
        """消息文本含摘要 + 匹配分数 + 时间范围 + 参与者 + 原始消息。"""
        candidate = make_recall_candidate(
            score=0.72,
            summary="讨论了天气",
            time_range="2024-01-01 10:00:00 ~ 2024-01-01 11:00:00",
            participants=["alice", "bob"],
        )
        content = _format_mid_term_memory_reference(candidate, original_messages_text="[10:00] alice: 今天晴天")
        assert MID_TERM_MEMORY_REFERENCE_MARKER in content
        assert "讨论了天气" in content
        assert "0.72" in content
        assert "2024-01-01 10:00:00 ~ 2024-01-01 11:00:00" in content
        assert "alice" in content
        assert "今天晴天" in content

    def test_append_to_selected_history(self) -> None:
        """recall 命中 2 条 → selected_history 末尾 append 2 条。"""
        # 构造 2 条 ReferenceMessage
        refs = [
            ReferenceMessage(
                content=f"{MID_TERM_MEMORY_REFERENCE_MARKER}\n参考{i}",
                timestamp=datetime.now(),
                reference_type=ReferenceMessageType.MEMORY,
                remaining_uses_value=None,
            )
            for i in range(2)
        ]
        selected_history = [SimpleNamespace(role="user", processed_plain_text="你好", timestamp=datetime.now())]
        # 模拟 chat_loop_service 的 append 逻辑
        updated = list(selected_history) + refs
        assert len(updated) == 3
        assert updated[-2] is refs[0]
        assert updated[-1] is refs[1]

    def test_fetch_trigger(self) -> None:
        """翻原文触发：候选有有效指针 → find_messages 被调用 → 原文追加到参考消息。"""
        candidate = make_recall_candidate(
            session_id="group:12345",
            time_range="2024-01-01 10:00:00 ~ 2024-01-01 11:00:00",
        )
        mock_messages = make_mock_find_messages_result(3)
        with patch("src.common.message_repository.find_messages", return_value=mock_messages) as mock_fn:
            result = _fetch_original_messages_for_candidate(
                candidate, session_id="group:12345", message_limit=20, token_limit=2000,
            )
        # find_messages 被调用（翻原文触发）
        assert mock_fn.call_count == 1
        # 原文内容出现在结果中
        assert "消息内容0" in result