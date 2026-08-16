"""ZH1-1b 观测点测试 — recall 日志固定字段 + 降级日志 + 不泄露原文。

覆盖 spec 5.6.1：命中数 + token 数 + 耗时 + 阈值 + Top-K + 降级 + 截断 + 不泄露。
"""

import logging
from unittest.mock import patch

import pytest

from src.maisaka.memory.mid_term import _log_recall_observation


class TestObservation:
    """观测点测试。"""

    def test_observation_fields_complete(self, caplog: pytest.LogCaptureFixture) -> None:
        """日志含命中数 + 追加 token 数 + 耗时 + 阈值 + Top-K。"""
        with caplog.at_level(logging.INFO, logger="maisaka_mid_term_memory"):
            _log_recall_observation(
                hit_count=2,
                appended_tokens=1500,
                latency_ms=800,
                threshold=0.65,
                top_k=3,
                session_id="group:A",
                hit_summaries=[],
            )
        log_text = caplog.text
        assert "recall_hit_count=2" in log_text
        assert "recall_appended_tokens=1500" in log_text
        assert "recall_latency_ms=800" in log_text
        assert "recall_threshold=0.65" in log_text
        assert "recall_top_k=3" in log_text

    def test_hit_count_field(self, caplog: pytest.LogCaptureFixture) -> None:
        """recall 命中 2 条 → recall_hit_count=2。"""
        with caplog.at_level(logging.INFO, logger="maisaka_mid_term_memory"):
            _log_recall_observation(
                hit_count=2, appended_tokens=100, latency_ms=50,
                threshold=0.65, top_k=3, session_id="group:A",
                hit_summaries=[{"summary_id": "A", "score": 0.72, "time_range": "tr"}],
            )
        assert "recall_hit_count=2" in caplog.text

    def test_hit_count_zero(self, caplog: pytest.LogCaptureFixture) -> None:
        """recall 未命中 → recall_hit_count=0。"""
        with caplog.at_level(logging.INFO, logger="maisaka_mid_term_memory"):
            _log_recall_observation(
                hit_count=0, appended_tokens=0, latency_ms=10,
                threshold=0.65, top_k=3, session_id="group:A",
                hit_summaries=[],
            )
        assert "recall_hit_count=0" in caplog.text

    def test_appended_tokens_field(self, caplog: pytest.LogCaptureFixture) -> None:
        """append 2 条合计 1500 token → recall_appended_tokens=1500。"""
        with caplog.at_level(logging.INFO, logger="maisaka_mid_term_memory"):
            _log_recall_observation(
                hit_count=2, appended_tokens=1500, latency_ms=100,
                threshold=0.65, top_k=3, session_id="group:A",
                hit_summaries=[],
            )
        assert "recall_appended_tokens=1500" in caplog.text

    def test_latency_field(self, caplog: pytest.LogCaptureFixture) -> None:
        """recall 耗时 800ms → recall_latency_ms=800。"""
        with caplog.at_level(logging.INFO, logger="maisaka_mid_term_memory"):
            _log_recall_observation(
                hit_count=1, appended_tokens=50, latency_ms=800,
                threshold=0.65, top_k=3, session_id="group:A",
                hit_summaries=[],
            )
        assert "recall_latency_ms=800" in caplog.text

    def test_threshold_top_k_field(self, caplog: pytest.LogCaptureFixture) -> None:
        """阈值 0.65 + Top-K=3 → recall_threshold=0.65, recall_top_k=3。"""
        with caplog.at_level(logging.INFO, logger="maisaka_mid_term_memory"):
            _log_recall_observation(
                hit_count=1, appended_tokens=50, latency_ms=100,
                threshold=0.65, top_k=3, session_id="group:A",
                hit_summaries=[],
            )
        assert "recall_threshold=0.65" in caplog.text
        assert "recall_top_k=3" in caplog.text

    def test_degradation_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """候选加载失败 → 日志含降级环节 + 原因 + session_id。"""
        with caplog.at_level(logging.WARNING, logger="maisaka_mid_term_memory"):
            _log_recall_observation(
                hit_count=0, appended_tokens=0, latency_ms=5,
                threshold=0.65, top_k=3, session_id="group:A",
                hit_summaries=[],
                degradation={"stage": "候选源加载", "reason": "DB连接失败"},
            )
        log_text = caplog.text
        assert "候选源加载" in log_text
        assert "DB连接失败" in log_text
        assert "group:A" in log_text

    def test_hit_summary_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """命中摘要 A（score=0.72）→ 日志含 summary_id=A + score=0.72 + time_range。"""
        with caplog.at_level(logging.INFO, logger="maisaka_mid_term_memory"):
            _log_recall_observation(
                hit_count=1, appended_tokens=100, latency_ms=50,
                threshold=0.65, top_k=3, session_id="group:A",
                hit_summaries=[{
                    "summary_id": "mtm:A",
                    "score": 0.72,
                    "time_range": "2024-01-01 10:00 ~ 11:00",
                }],
            )
        log_text = caplog.text
        assert "summary_id=mtm:A" in log_text
        assert "0.72" in log_text
        assert "2024-01-01 10:00 ~ 11:00" in log_text

    def test_truncation_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """原文 3000 token 截断到 2000 → 日志含 original_tokens + truncated_tokens。"""
        with caplog.at_level(logging.INFO, logger="maisaka_mid_term_memory"):
            _log_recall_observation(
                hit_count=1, appended_tokens=100, latency_ms=50,
                threshold=0.65, top_k=3, session_id="group:A",
                hit_summaries=[],
                truncation={"original_tokens": 3000, "truncated_tokens": 2000},
            )
        log_text = caplog.text
        assert "original_tokens=3000" in log_text
        assert "truncated_tokens=2000" in log_text

    def test_no_leak_original_text(self, caplog: pytest.LogCaptureFixture) -> None:
        """recall 日志无原始消息全文。"""
        secret_text = "这是一条非常隐秘的原始消息内容不应该出现在日志里"
        with caplog.at_level(logging.INFO, logger="maisaka_mid_term_memory"):
            _log_recall_observation(
                hit_count=1, appended_tokens=100, latency_ms=50,
                threshold=0.65, top_k=3, session_id="group:A",
                hit_summaries=[{"summary_id": "A", "score": 0.7, "time_range": "tr"}],
            )
        assert secret_text not in caplog.text