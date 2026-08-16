"""ZH1-1b 双向去重测试 — 已加载摘要不 recall + 已 recall 原文不重复。

覆盖 spec 5.4.1：方向 1 排除已加载摘要（summary_id），方向 2 排除已 recall 原文。
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.maisaka.memory.mid_term import (
    MID_TERM_MEMORY_REFERENCE_MARKER,
    _collect_recalled_mid_term_memory_reference_identities,
    _is_mid_term_memory_candidate_already_recalled,
)
from src.maisaka.context.messages import ReferenceMessage, ReferenceMessageType
from tests.test_zh1_1b_recall._helpers import make_recall_candidate


def _make_recall_ref_content(message_id: str, segment: str) -> str:
    """构造已 recall 的 ReferenceMessage content（含摘要ID + 匹配段标签）。"""
    return "\n".join([
        MID_TERM_MEMORY_REFERENCE_MARKER,
        f"摘要ID: {message_id}",
        f"匹配段: {segment}",
        "summary: 测试",
    ])


class TestDedup:
    """双向去重测试。"""

    def test_loaded_summary_not_recall(self) -> None:
        """history 含 summary_id=A + 候选源含 A → recall 排除 A。"""
        candidate_a = make_recall_candidate(message_id="mtm:A", segment_text="天气")
        result = _is_mid_term_memory_candidate_already_recalled(
            candidate_a,
            recalled_keys=set(),
            recalled_segments=set(),
            existing_summary_ids={"mtm:A"},
        )
        assert result is True

    def test_unloaded_summary_can_recall(self) -> None:
        """history 无 summary_id=A + 候选源含 A → A 可参与 recall。"""
        candidate_a = make_recall_candidate(message_id="mtm:A", segment_text="天气")
        result = _is_mid_term_memory_candidate_already_recalled(
            candidate_a,
            recalled_keys=set(),
            recalled_segments=set(),
            existing_summary_ids={"mtm:B"},
        )
        assert result is False

    def test_existing_summary_ids_passed(self) -> None:
        """history 含 3 条 ComplexSessionMessage（A/B/C）→ existing_summary_ids={A,B,C}。"""
        # 模拟 chat_loop_service 构造 existing_summary_ids 的逻辑
        from src.maisaka.memory.mid_term import is_mid_term_memory_message
        from tests.test_zh1_1b_recall._helpers import make_mid_term_complex_message

        history = [
            make_mid_term_complex_message(message_id="mtm:A"),
            make_mid_term_complex_message(message_id="mtm:B"),
            make_mid_term_complex_message(message_id="mtm:C"),
        ]
        existing_ids = {msg.message_id for msg in history if is_mid_term_memory_message(msg)}
        assert existing_ids == {"mtm:A", "mtm:B", "mtm:C"}

    def test_recalled_original_not_repeated(self) -> None:
        """selected_history 含 (msg1, seg1) → recall 不重复 append。"""
        # 构造已 recall 的 ReferenceMessage
        ref = ReferenceMessage(
            content=_make_recall_ref_content("mtm:A", "天气"),
            timestamp=datetime.now(),
            reference_type=ReferenceMessageType.MEMORY,
            remaining_uses_value=None,
        )
        recalled_keys, recalled_segments = _collect_recalled_mid_term_memory_reference_identities([ref])
        # 候选 (mtm:A, 天气) 应被排除
        candidate = make_recall_candidate(message_id="mtm:A", segment_text="天气")
        result = _is_mid_term_memory_candidate_already_recalled(
            candidate,
            recalled_keys=recalled_keys,
            recalled_segments=recalled_segments,
        )
        assert result is True

    def test_dedup_both_directions(self) -> None:
        """history 含 summary_id=A + selected_history 含 (msg1, seg1) → 双向排除。"""
        ref = ReferenceMessage(
            content=_make_recall_ref_content("mtm:A", "天气"),
            timestamp=datetime.now(),
            reference_type=ReferenceMessageType.MEMORY,
            remaining_uses_value=None,
        )
        recalled_keys, recalled_segments = _collect_recalled_mid_term_memory_reference_identities([ref])
        candidate = make_recall_candidate(message_id="mtm:A", segment_text="天气")
        # 方向 1：existing_summary_ids 含 A
        result = _is_mid_term_memory_candidate_already_recalled(
            candidate,
            recalled_keys=recalled_keys,
            recalled_segments=recalled_segments,
            existing_summary_ids={"mtm:A"},
        )
        assert result is True

    def test_dedup_idempotent(self) -> None:
        """同轮再次 recall 命中 (msg1, seg1) → 不重复 append。"""
        ref = ReferenceMessage(
            content=_make_recall_ref_content("mtm:A", "天气"),
            timestamp=datetime.now(),
            reference_type=ReferenceMessageType.MEMORY,
            remaining_uses_value=None,
        )
        recalled_keys, recalled_segments = _collect_recalled_mid_term_memory_reference_identities([ref])
        candidate = make_recall_candidate(message_id="mtm:A", segment_text="天气")
        # 第一次排除
        result1 = _is_mid_term_memory_candidate_already_recalled(
            candidate, recalled_keys=recalled_keys, recalled_segments=recalled_segments,
        )
        # 第二次排除（幂等）
        result2 = _is_mid_term_memory_candidate_already_recalled(
            candidate, recalled_keys=recalled_keys, recalled_segments=recalled_segments,
        )
        assert result1 is True
        assert result2 is True

    def test_dedup_no_false_kill(self) -> None:
        """history 含 summary_id=A + 候选源含 B → B 不被排除。"""
        candidate_b = make_recall_candidate(message_id="mtm:B", segment_text="美食")
        result = _is_mid_term_memory_candidate_already_recalled(
            candidate_b,
            recalled_keys=set(),
            recalled_segments=set(),
            existing_summary_ids={"mtm:A"},
        )
        assert result is False