"""ZG-25 升级测试：N5 surface 替换机制验证（spec 15.4）。

验证 compaction.py 委托 N5 SurfaceReplacer 做替换，
产生 tx_id 事务身份 + replace_generation 代数递增，
且替换非删除（不写回 _chat_history）。
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


from src.maisaka.context.compaction import compact_selected_history
from src.maisaka.context.messages import CompactionSummaryMessage

from .conftest import make_long_history, make_mock_llm_service


def _compaction_source() -> str:
    """读取 compaction.py 源码（grep 断言用）。"""
    return Path("src/maisaka/context/compaction.py").read_text(encoding="utf-8")


class TestSurfaceReplacement:
    """N5 surface 替换机制验证。"""

    async def test_tx_id_globally_unique(self, compaction_config) -> None:
        """用例1：两次压缩 → tx_id 全局唯一（不同）。"""
        history1 = make_long_history(count=20, text_size=200)
        history2 = make_long_history(count=20, text_size=200)
        llm_service = make_mock_llm_service(summary_text="摘要")

        result1 = await compact_selected_history(
            history1, context_window=1000, session_id="session-a",
            llm_service=llm_service, config=compaction_config,
        )
        result2 = await compact_selected_history(
            history2, context_window=1000, session_id="session-b",
            llm_service=llm_service, config=compaction_config,
        )

        tx_id1 = result1[0].tx_id
        tx_id2 = result2[0].tx_id
        assert tx_id1 != ""
        assert tx_id2 != ""
        assert tx_id1 != tx_id2

    async def test_replace_generation_monotonic(self, compaction_config) -> None:
        """用例2：连续两次压缩同一会话 → replace_generation 递增。"""
        history1 = make_long_history(count=20, text_size=200)
        history2 = make_long_history(count=20, text_size=200)
        llm_service = make_mock_llm_service(summary_text="摘要")

        result1 = await compact_selected_history(
            history1, context_window=1000, session_id="same-session",
            llm_service=llm_service, config=compaction_config,
        )
        gen1 = result1[0].replace_generation

        result2 = await compact_selected_history(
            history2, context_window=1000, session_id="same-session",
            llm_service=llm_service, config=compaction_config,
        )
        gen2 = result2[0].replace_generation

        assert gen2 > gen1

    async def test_surface_changed_aborts_compaction(self, compaction_config) -> None:
        """用例3：摘要生成期间 surface 已变 → 中止压缩，降级返回原 history。"""
        history = make_long_history(count=20, text_size=200)
        llm_service = make_mock_llm_service(summary_text="摘要")

        mock_replacer = MagicMock()
        mock_replacer.current_generation = AsyncMock(return_value=0)
        mock_replacer.assert_surface_unchanged = AsyncMock(return_value=False)
        mock_replacer.replace = AsyncMock()

        with patch(
            "src.maisaka.context.compaction.get_surface_replacer",
            return_value=mock_replacer,
        ):
            result = await compact_selected_history(
                history, context_window=1000, session_id="test",
                llm_service=llm_service, config=compaction_config,
            )

        assert result is history
        mock_replacer.replace.assert_not_called()

    async def test_compaction_does_not_mutate_input(self, compaction_config) -> None:
        """用例4：压缩触发 → 输入 history 列表不被修改（替换非删除）。"""
        history = make_long_history(count=20, text_size=200)
        original_len = len(history)
        original_ids = [id(msg) for msg in history]
        llm_service = make_mock_llm_service(summary_text="摘要")

        result = await compact_selected_history(
            history, context_window=1000, session_id="test",
            llm_service=llm_service, config=compaction_config,
        )

        assert isinstance(result[0], CompactionSummaryMessage)
        assert len(history) == original_len
        assert [id(msg) for msg in history] == original_ids

    def test_grep_imports_n5_surface_no_local_copy(self) -> None:
        """用例5：compaction 源码导入 N5 surface 模块，无本地替换语义复制。"""
        source = _compaction_source()
        assert "from src.A_memorix.core.runtime.services.compaction" in source
        assert "get_surface_replacer" in source
        assert "get_tool_pairing_balancer" in source
        assert "shadowed_seqs" not in source or "CompactionRange" in source