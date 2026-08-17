"""ZG-25 测试：生产路径集成——chat_loop_step 接线覆盖。

验证 AGENTS.md 硬性规则 3：单测必须覆盖生产路径初始化。
验证 compact_selected_history 在 chat_loop_service.py 有生产调用点。
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.maisaka.chat_loop_service import MaisakaChatLoopService


class TestProductionPathWiring:
    """验证 chat_loop_step 生产路径调用 compact_selected_history。"""

    def test_build_compaction_config_reads_app_config(self) -> None:
        """_build_compaction_config 从 app_config_port 读取 7 个参数。"""
        mock_port = MagicMock()
        mock_port.get_enable_b_layer_compaction.return_value = True
        mock_port.get_compaction_threshold_ratio.return_value = 0.8
        mock_port.get_compaction_retain_ratio.return_value = 0.3
        mock_port.get_compaction_min_segment_size.return_value = 8
        mock_port.get_compaction_min_segment_tokens.return_value = 600
        mock_port.get_compaction_timeout_ms.return_value = 5000
        mock_port.get_compaction_summary_max_tokens.return_value = 400

        with patch(
            "src.maisaka.chat_loop_service.get_app_config_port",
            return_value=mock_port,
        ):
            config = MaisakaChatLoopService._build_compaction_config()

        assert config.enable is True
        assert config.threshold_ratio == 0.8
        assert config.retain_ratio == 0.3
        assert config.min_segment_size == 8
        assert config.min_segment_tokens == 600
        assert config.timeout_ms == 5000
        assert config.summary_max_tokens == 400

    def test_compaction_imported_in_chat_loop_service(self) -> None:
        """compact_selected_history 已导入 chat_loop_service 模块。"""
        import src.maisaka.chat_loop_service as module

        assert hasattr(module, "compact_selected_history")
        assert hasattr(module, "CompactionConfig")

    def test_compaction_called_in_chat_loop_service_source(self) -> None:
        """compact_selected_history 在 chat_loop_service.py 有生产调用点。"""
        project_root = Path(__file__).parent.parent.parent
        chat_loop_service = project_root / "src" / "maisaka" / "chat_loop_service.py"
        result = subprocess.run(
            ["rg", "compact_selected_history", str(chat_loop_service)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            "compact_selected_history 未在 chat_loop_service.py 命中——接线缺失"
        )
        lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
        assert len(lines) >= 2, (
            f"compact_selected_history 在 chat_loop_service.py 仅命中 {len(lines)} 行，"
            "期望 ≥ 2 行（import + 调用点）"
        )

    def test_build_compaction_config_called_in_chat_loop_service(self) -> None:
        """_build_compaction_config 在 chat_loop_service.py 有生产调用点。"""
        project_root = Path(__file__).parent.parent.parent
        chat_loop_service = project_root / "src" / "maisaka" / "chat_loop_service.py"
        result = subprocess.run(
            ["rg", "_build_compaction_config", str(chat_loop_service)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            "_build_compaction_config 未在 chat_loop_service.py 命中——接线缺失"
        )
        lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
        assert len(lines) >= 2, (
            f"_build_compaction_config 在 chat_loop_service.py 仅命中 {len(lines)} 行，"
            "期望 ≥ 2 行（定义 + 调用点）"
        )
