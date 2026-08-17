"""ZG-24 测试：grep 验证死代码已消除。

验证 spec 8.1 验证项 + AGENTS.md 硬性规则：
process_chat_history_after_cycle 和 _trigger_trimmed_history_learning 都有生产调用点。
"""

import subprocess
import sys
from pathlib import Path


def _grep_count(pattern: str, search_path: Path) -> int:
    """在 src/ 下 grep 指定模式，返回命中行数。"""
    result = subprocess.run(
        [sys.executable, "-c", f"import subprocess; r = subprocess.run(['rg', '{pattern}', '{search_path}', '-l'], capture_output=True, text=True); print(r.stdout)"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent,
    )
    files = [f for f in result.stdout.strip().split("\n") if f.strip()]
    return len(files)


class TestGrepNoDeadCode:
    """验证 process_chat_history_after_cycle 和 _trigger_trimmed_history_learning 有生产调用点。"""

    def test_process_chat_history_after_cycle_has_caller(self) -> None:
        """process_chat_history_after_cycle 在 src/ 下命中 ≥ 2 文件（定义 + 调用点）。"""
        project_root = Path(__file__).parent.parent.parent
        src_path = project_root / "src"
        result = subprocess.run(
            ["rg", "process_chat_history_after_cycle", str(src_path), "-l"],
            capture_output=True,
            text=True,
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        assert len(files) >= 2, (
            f"process_chat_history_after_cycle 仅在 {files} 命中，期望 ≥ 2 文件（定义 + 调用点）"
        )

    def test_trigger_trimmed_history_learning_has_caller(self) -> None:
        """_trigger_trimmed_history_learning 在 src/ 下命中 ≥ 2 文件（定义 + 调用点）。"""
        project_root = Path(__file__).parent.parent.parent
        src_path = project_root / "src"
        result = subprocess.run(
            ["rg", "_trigger_trimmed_history_learning", str(src_path), "-l"],
            capture_output=True,
            text=True,
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        assert len(files) >= 2, (
            f"_trigger_trimmed_history_learning 仅在 {files} 命中，期望 ≥ 2 文件（定义 + 调用点）"
        )

    def test_process_chat_history_after_cycle_called_in_thinking_organ(self) -> None:
        """process_chat_history_after_cycle 在 thinking_organ.py 有生产调用点。"""
        project_root = Path(__file__).parent.parent.parent
        thinking_organ = project_root / "src" / "maisaka" / "agent_autonomy" / "thinking_organ.py"
        result = subprocess.run(
            ["rg", "process_chat_history_after_cycle", str(thinking_organ)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            "process_chat_history_after_cycle 未在 thinking_organ.py 命中——死代码未接线"
        )