"""ZH1-1a 回归测试 — 既有功能向后兼容性验证。

覆盖：
  - 辅助函数保持不变
  - build_mid_term_memory_reference_message 定义不变
  - 既有 post_processor 裁切逻辑不变
  - 既有 chat_loop_service 其他过滤逻辑不变
  - 既有 mai_messages 表结构不变
  - 既有 A_memorix ingest_summary 不变
"""

import inspect
from pathlib import Path

import pytest

from src.maisaka.memory.mid_term import (
    build_mid_term_memory_full_text,
    build_mid_term_memory_preview_text,
    build_mid_term_memory_reference_message,
    is_mid_term_memory_message,
)


class TestRegression:
    """既有功能回归验证。"""

    def test_helpers_unchanged(self) -> None:
        """辅助函数保持不变：is_mid_term_memory_message + preview/full text 存在且可调用。"""
        assert callable(is_mid_term_memory_message)
        assert callable(build_mid_term_memory_preview_text)
        assert callable(build_mid_term_memory_full_text)
        # preview_text 基本行为不变
        text = build_mid_term_memory_preview_text({
            "time_range": "2024-01-01 ~ 2024-01-02",
            "participants": ["alice"],
            "summary": "回归测试摘要",
        })
        assert "聊天回想" in text
        assert "回归测试摘要" in text

    def test_recall_function_unchanged(self) -> None:
        """build_mid_term_memory_reference_message 保持定义不变（async function）。"""
        assert inspect.iscoroutinefunction(build_mid_term_memory_reference_message)
        sig = inspect.signature(build_mid_term_memory_reference_message)
        # 既有参数：history, selected_history, session_id, log_prefix
        param_names = set(sig.parameters.keys())
        assert "history" in param_names
        assert "selected_history" in param_names
        assert "session_id" in param_names

    def test_post_processor_trim_unchanged(self) -> None:
        """既有 post_processor 裁切逻辑不变：process_chat_history_after_cycle + _trim 存在。"""
        from src.maisaka.context.post_processor import (
            _trim_history_to_context_target,
            process_chat_history_after_cycle,
        )

        assert callable(process_chat_history_after_cycle)
        assert callable(_trim_history_to_context_target)
        # 既有参数签名不变
        sig = inspect.signature(process_chat_history_after_cycle)
        param_names = set(sig.parameters.keys())
        assert "chat_history" in param_names
        assert "max_context_size" in param_names

    def test_chat_loop_service_other_filter_unchanged(self) -> None:
        """既有 chat_loop_service expression_selector 过滤逻辑不变。"""
        from src.maisaka.chat_loop_service import MaisakaChatLoopService
        from types import SimpleNamespace

        # expression_selector 仍过滤非 SessionBackedMessage
        plain = SimpleNamespace()
        result = MaisakaChatLoopService._filter_history_for_request_kind(
            [plain], request_kind="expression_selector",
        )
        assert plain not in result  # SimpleNamespace 非 SessionBackedMessage 被过滤

    def test_mai_messages_table_unchanged(self) -> None:
        """既有 mai_messages 表结构不变：Messages 表 __tablename__ == 'mai_messages'。"""
        from src.common.database.database_model import Messages

        assert Messages.__tablename__ == "mai_messages"
        # 既有字段不变
        assert hasattr(Messages, "message_id")
        assert hasattr(Messages, "timestamp")
        assert hasattr(Messages, "platform")

    def test_mid_term_summaries_table_new(self) -> None:
        """新增 MidTermMemorySummaries 表存在（ZH1-1a 新表）。"""
        from src.common.database.database_model import MidTermMemorySummaries

        assert MidTermMemorySummaries.__tablename__ == "mid_term_memory_summaries"
        assert hasattr(MidTermMemorySummaries, "summary_id")
        assert hasattr(MidTermMemorySummaries, "session_id")
        assert hasattr(MidTermMemorySummaries, "summary")
        assert hasattr(MidTermMemorySummaries, "recall_cues")
        assert hasattr(MidTermMemorySummaries, "timestamp")

    def test_a_memorix_unchanged(self) -> None:
        """既有 A_memorix ingest_summary 写回入口不变。"""
        # 用源码检查避免重 import
        kernel_path = Path(__file__).resolve().parents[2] / "src" / "A_memorix" / "core" / "runtime" / "sdk_memory_kernel.py"
        if kernel_path.exists():
            source = kernel_path.read_text(encoding="utf-8")
            assert "async def ingest_summary" in source, \
                "A_memorix sdk_memory_kernel.ingest_summary 写回入口不存在"
        else:
            pytest.skip("A_memorix sdk_memory_kernel.py 路径不存在")

    def test_napcat_timestamp_fix_unchanged(self) -> None:
        """既有 napcat 适配器 _resolve_napcat_timestamp 存在。"""
        codec_path = (
            Path(__file__).resolve().parents[2]
            / "plugins" / "maibot-team.napcat-adapter" / "codecs" / "inbound" / "message_codec.py"
        )
        if codec_path.exists():
            source = codec_path.read_text(encoding="utf-8")
            assert "def _resolve_napcat_timestamp" in source
        else:
            pytest.skip("napcat message_codec.py 路径不存在")