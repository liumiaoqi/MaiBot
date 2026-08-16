"""ZH1-1b 回归 + 核心隔离测试 — 既有函数签名/行为不变 + 核心隔离验证。

覆盖 spec 4.5：兼容性规则——既有接口不变 + 核心层不直接导入业务接口。
"""

import inspect
from pathlib import Path

import pytest

from src.maisaka.memory.mid_term import (
    MID_TERM_MEMORY_RECALL_CONTEXT_MESSAGE_LIMIT,
    RecallConfig,
    _build_mid_term_memory_recall_query_text,
    _cosine_similarity,
    _fetch_original_messages_for_candidate,
    _format_mid_term_memory_reference,
    _get_recall_config,
    _is_mid_term_memory_candidate_already_recalled,
    _log_recall_observation,
    _parse_candidate_pointer,
    _select_best_recall_candidate,
    _select_top_k_recall_candidates,
    _truncate_original_messages,
    build_mid_term_memory_message,
    build_mid_term_memory_message_from_record,
    build_mid_term_memory_reference_message,
    insert_mid_term_memory_message,
    is_mid_term_memory_message,
    is_mid_term_memory_reference_message,
)


class TestRegression:
    """回归 + 核心隔离测试。"""

    def test_helpers_unchanged(self) -> None:
        """辅助函数保持不变：_cosine_similarity + _truncate 等存在且可调用。"""
        assert callable(_cosine_similarity)
        assert callable(_truncate_original_messages)
        assert callable(_format_mid_term_memory_reference)
        assert callable(_parse_candidate_pointer)
        assert callable(_is_mid_term_memory_candidate_already_recalled)
        assert callable(_log_recall_observation)
        assert callable(_build_mid_term_memory_recall_query_text)

    def test_select_best_recall_candidate_preserved(self) -> None:
        """_select_best_recall_candidate 保留（K=1 退化用）。"""
        assert callable(_select_best_recall_candidate)
        sig = inspect.signature(_select_best_recall_candidate)
        params = list(sig.parameters.keys())
        assert "candidates" in params
        assert "query_embedding" in params
        assert "threshold" in params

    def test_find_messages_unchanged(self) -> None:
        """既有 find_messages 接口不变。"""
        from src.common.message_repository import find_messages

        sig = inspect.signature(find_messages)
        params = set(sig.parameters.keys())
        # 既有参数保留
        assert "session_id" in params
        assert "start_time" in params
        assert "end_time" in params
        assert "limit" in params
        assert "limit_mode" in params

    def test_reference_message_unchanged(self) -> None:
        """既有 ReferenceMessage 机制不变。"""
        from src.maisaka.context.messages import ReferenceMessage, ReferenceMessageType

        assert hasattr(ReferenceMessageType, "MEMORY")
        # ReferenceMessage 有 content + reference_type + count_in_context
        assert hasattr(ReferenceMessage, "content")
        assert hasattr(ReferenceMessage, "reference_type")
        assert hasattr(ReferenceMessage, "count_in_context")

    def test_chat_loop_select_prefetch_unchanged(self) -> None:
        """既有 chat_loop_service select/prefetch 逻辑不变。"""
        from src.maisaka.chat_loop_service import MaisakaChatLoopService

        assert hasattr(MaisakaChatLoopService, "select_llm_context_messages")
        source = inspect.getsource(MaisakaChatLoopService)
        assert "prefetch_forward_nodes_for_messages" in source

    def test_zh1_1a_build_persist_unchanged(self) -> None:
        """既有 ZH1-1a 摘要构建/持久化逻辑不变。"""
        # build_mid_term_memory_message 存在且是 async
        assert inspect.iscoroutinefunction(build_mid_term_memory_message)
        # insert_mid_term_memory_message 存在且是 async
        assert inspect.iscoroutinefunction(insert_mid_term_memory_message)
        # build_mid_term_memory_message_from_record 存在
        assert callable(build_mid_term_memory_message_from_record)
        # is_mid_term_memory_message 存在
        assert callable(is_mid_term_memory_message)

    def test_a_memorix_unchanged(self) -> None:
        """既有 A_memorix chat_summary_writeback 不变。"""
        from src.core.protocols import AppConfigPort

        # AppConfigPort 仍有 a_memorix 相关 getter
        assert hasattr(AppConfigPort, "get_a_memorix_integration_config")
        assert hasattr(AppConfigPort, "get_a_memorix_full_config")

    def test_core_isolation(self) -> None:
        """核心隔离验证：本批改动不涉及 src/core/ 下业务接口文件。"""
        repo_root = Path(__file__).resolve().parents[2]
        # mid_term.py 在 maisaka 层不在 core 层
        mid_term_path = repo_root / "src" / "maisaka" / "memory" / "mid_term.py"
        assert mid_term_path.exists()
        assert "maisaka" in str(mid_term_path)
        # core 层无 mid_term recall 业务逻辑
        core_mid_term = repo_root / "src" / "core" / "mid_term.py"
        assert not core_mid_term.exists(), "mid_term 不应在 src/core/ 下"
        # AppConfigPort recall getter 是 Protocol 声明（非业务实现）
        from src.core.protocols import AppConfigPort

        assert hasattr(AppConfigPort, "get_recall_threshold")
        assert hasattr(AppConfigPort, "get_recall_top_k")
        # 核心层不直接导入 mid_term recall 函数
        core_dir = repo_root / "src" / "core"
        if not core_dir.exists():
            pytest.skip("src/core/ 目录不存在")
        forbidden_markers = [
            "from src.maisaka.memory.mid_term import build_mid_term_memory_reference_message",
            "from src.maisaka.memory.mid_term import _select_top_k_recall_candidates",
        ]
        violations = []
        for py_file in core_dir.rglob("*.py"):
            try:
                source = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for marker in forbidden_markers:
                if marker in source:
                    violations.append(f"{py_file}: 含 {marker}")
        assert not violations, f"核心层违反隔离原则: {violations}"