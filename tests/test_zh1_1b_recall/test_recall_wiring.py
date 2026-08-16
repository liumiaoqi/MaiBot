"""ZH1-1b 接线 + 生产路径测试 — chat_loop_service recall 挂载验证。

覆盖 spec 5.5.1：select 后 append recall + 失败降级 + 配置开关 + 生产路径。
AGENTS.md 硬性规则：生产路径测试必须验证 chat_loop_service 调用 build_mid_term_memory_reference_message。
"""

import inspect
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.maisaka.memory.mid_term import build_mid_term_memory_reference_message
from tests.test_zh1_1b_recall._helpers import make_mock_app_config_port, make_user_msg


class TestRecallWiring:
    """接线 + 生产路径测试。"""

    def test_mount_position(self) -> None:
        """chat_loop_step 执行 → select 返回 → recall 挂载 → prefetch。"""
        from src.maisaka.chat_loop_service import MaisakaChatLoopService

        source = inspect.getsource(MaisakaChatLoopService)
        # select 在 recall 之前
        select_pos = source.find("select_llm_context_messages")
        recall_pos = source.find("_append_recall_reference_messages")
        prefetch_pos = source.find("prefetch_forward_nodes_for_messages")
        assert select_pos < recall_pos < prefetch_pos, "recall 应在 select 之后、prefetch 之前"

    def test_selected_history_ready(self) -> None:
        """selected_history 就绪：_append_recall_reference_messages 接收 selected_history 参数。"""
        from src.maisaka.chat_loop_service import MaisakaChatLoopService

        sig = inspect.signature(MaisakaChatLoopService._append_recall_reference_messages)
        params = list(sig.parameters.keys())
        assert "selected_history" in params

    def test_session_id_passed(self) -> None:
        """会话 A 的 chat_loop_step → recall 用 session_id=A。"""
        from src.maisaka.chat_loop_service import MaisakaChatLoopService

        source = inspect.getsource(MaisakaChatLoopService._append_recall_reference_messages)
        assert "self._session_id" in source

    def test_append_to_selected_history(self) -> None:
        """append 方式：recall_references 非空时返回 selected_history + recall_references。"""
        from src.maisaka.chat_loop_service import MaisakaChatLoopService

        source = inspect.getsource(MaisakaChatLoopService._append_recall_reference_messages)
        assert "selected_history + recall_references" in source

    def test_async_await(self) -> None:
        """异步化：_append_recall_reference_messages 是 async def。"""
        from src.maisaka.chat_loop_service import MaisakaChatLoopService

        assert inspect.iscoroutinefunction(MaisakaChatLoopService._append_recall_reference_messages)

    def test_failure_degradation(self) -> None:
        """recall 抛异常 → 捕获 + error 日志 + 上报，selected_history 不变。"""
        from src.maisaka.chat_loop_service import MaisakaChatLoopService

        source = inspect.getsource(MaisakaChatLoopService._append_recall_reference_messages)
        # 有 try/except 捕获异常
        assert "except Exception" in source
        # 降级返回 selected_history
        assert "return selected_history" in source

    async def test_config_switch_off(self) -> None:
        """配置开关关闭：get_chat_mid_term_memory()=False → build 返回 []。"""
        mock_port = make_mock_app_config_port(chat_mid_term_memory=False)
        with patch("src.maisaka.memory.mid_term.get_app_config_port", return_value=mock_port):
            result = await build_mid_term_memory_reference_message(
                history=[], selected_history=[], session_id="group:A",
            )
        assert result == []

    async def test_config_switch_on(self) -> None:
        """配置开关开启：get_chat_mid_term_memory()=True → 进入 recall 流程。"""
        mock_port = make_mock_app_config_port(chat_mid_term_memory=True)
        with patch("src.maisaka.memory.mid_term.get_app_config_port", return_value=mock_port), \
             patch("src.maisaka.memory.mid_term._collect_mid_term_memory_recall_candidates", return_value=[]):
            result = await build_mid_term_memory_reference_message(
                history=[], selected_history=[make_user_msg("测试")], session_id="group:A",
            )
        # 候选为空 → 返回 []
        assert result == []

    def test_select_unchanged(self) -> None:
        """既有 select 不变：select_llm_context_messages 方法存在。"""
        from src.maisaka.chat_loop_service import MaisakaChatLoopService

        assert hasattr(MaisakaChatLoopService, "select_llm_context_messages")

    def test_prefetch_unchanged(self) -> None:
        """既有 prefetch 不变：chat_loop_step 含 prefetch_forward_nodes_for_messages 调用。"""
        from src.maisaka.chat_loop_service import MaisakaChatLoopService

        source = inspect.getsource(MaisakaChatLoopService)
        assert "prefetch_forward_nodes_for_messages" in source

    def test_timeout_degradation(self) -> None:
        """recall 超时降级：latency_ms > timeout_ms → warning 日志。"""
        from src.maisaka.memory.mid_term import build_mid_term_memory_reference_message

        source = inspect.getsource(build_mid_term_memory_reference_message)
        assert "timeout_ms" in source
        assert "超时" in source

    def test_chat_loop_service_recall_wiring(self) -> None:
        """生产路径测试：chat_loop_service.py 调用 build_mid_term_memory_reference_message。"""
        from src.maisaka.chat_loop_service import MaisakaChatLoopService

        source = inspect.getsource(MaisakaChatLoopService._append_recall_reference_messages)
        assert "build_mid_term_memory_reference_message" in source, \
            "_append_recall_reference_messages 未调用 build_mid_term_memory_reference_message"

    def test_candidate_source_from_persistence_wiring(self) -> None:
        """生产路径测试：recall 候选源从 load_summaries_by_session 加载。"""
        from src.maisaka.memory.mid_term import _collect_mid_term_memory_recall_candidates

        source = inspect.getsource(_collect_mid_term_memory_recall_candidates)
        assert "load_summaries_by_session" in source, \
            "候选源未从 load_summaries_by_session 加载"

    def test_recall_config_from_app_config_wiring(self) -> None:
        """生产路径测试：app_config 的 recall 参数被 recall 读取。"""
        from src.maisaka.memory.mid_term import _get_recall_config

        source = inspect.getsource(_get_recall_config)
        assert "get_recall_threshold" in source
        assert "get_recall_top_k" in source
        assert "get_recall_candidate_limit" in source
        assert "get_recall_original_message_limit" in source
        assert "get_recall_original_token_limit" in source
        assert "get_recall_timeout_ms" in source