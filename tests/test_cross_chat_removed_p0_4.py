"""P0-4 验收：CrossChatContextService 移除 grep 零残留测试。

对应 tasks.md 7.2：验证
1. src/maisaka/cross_chat/ 目录不存在
2. src/ 下无 `from src.maisaka.cross_chat` / `from .cross_chat` import 残留
3. src/ 下无 `CrossChatContextService` / `CrossChatContextInjector` 类名引用残留
4. fix_import_logging.py 的 B_CLASS 清单无 cross_chat 路径项
5. migration/coordinator.py 的 "cross-chat-context" 历史迁移语义保留（不误删）
"""

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
SRC_PATH = PROJECT_ROOT / "src"


def _rg_files(pattern: str, search_path: Path) -> list[str]:
    """rg 搜索返回命中文件列表。"""
    result = subprocess.run(
        ["rg", pattern, str(search_path), "-l"],
        capture_output=True,
        text=True,
    )
    return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]


def _rg_lines(pattern: str, search_path: Path) -> list[str]:
    """rg 搜索返回命中行内容。"""
    result = subprocess.run(
        ["rg", pattern, str(search_path), "-n"],
        capture_output=True,
        text=True,
    )
    return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]


class TestCrossChatRemoved:
    """P0-4: CrossChatContextService 整包移除零残留。"""

    def test_cross_chat_directory_removed(self) -> None:
        """src/maisaka/cross_chat/ 目录已删除。"""
        cross_chat_dir = PROJECT_ROOT / "src" / "maisaka" / "cross_chat"
        assert not cross_chat_dir.exists(), f"{cross_chat_dir} 仍存在"

    def test_no_cross_chat_import_in_src(self) -> None:
        """src/ 下无 `from src.maisaka.cross_chat` 或 `from .cross_chat` import。"""
        hits = _rg_files(r"from src\.maisaka\.cross_chat|from \.cross_chat", SRC_PATH)
        assert hits == [], f"src/ 下仍有 cross_chat import 残留: {hits}"

    def test_no_cross_chat_class_reference_in_src(self) -> None:
        """src/ 下无 CrossChatContextService / CrossChatContextInjector 类名引用。"""
        hits = _rg_files(
            r"CrossChatContextService|CrossChatContextInjector",
            SRC_PATH,
        )
        assert hits == [], f"src/ 下仍有 CrossChat 类名引用残留: {hits}"

    def test_fix_import_logging_no_cross_chat(self) -> None:
        """fix_import_logging.py 的 B_CLASS 清单无 cross_chat 路径项。"""
        fix_script = PROJECT_ROOT / "fix_import_logging.py"
        hits = _rg_lines(r"cross_chat/", fix_script)
        assert hits == [], f"fix_import_logging.py 仍有 cross_chat 路径项: {hits}"

    def test_migration_coordinator_keeps_historical_entry(self) -> None:
        """migration/coordinator.py 保留 "cross-chat-context" 历史迁移语义。"""
        coordinator = (
            PROJECT_ROOT
            / "src"
            / "maisaka"
            / "migration"
            / "coordinator.py"
        )
        content = coordinator.read_text(encoding="utf-8")
        assert "cross-chat-context" in content, (
            "migration/coordinator.py 应保留 'cross-chat-context' 历史迁移语义"
        )