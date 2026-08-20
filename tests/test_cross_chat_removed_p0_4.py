"""P0-4 验收：CrossChatContextService 移除零残留测试（零依赖实现）。

P1-R2-2: 改用 pathlib.rglob + re 零依赖实现（不依赖外部 rg 二进制）。
P2-R2-5: 扩展扫描范围到 src/pytests/tests/plugins 四目录（覆盖 monkeypatch 字符串引用）。

验证：
1. src/maisaka/cross_chat/ 目录不存在
2. 四目录无 `from src.maisaka.cross_chat` / `from .cross_chat` import 残留
3. 四目录无 `CrossChatContextService` / `CrossChatContextInjector` 类名引用残留
4. fix_import_logging.py 的 B_CLASS 清单无 cross_chat 路径项
5. migration/coordinator.py 的 "cross-chat-context" 历史迁移语义保留（不误删）
"""

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
SCAN_PATHS = [
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "pytests",
    PROJECT_ROOT / "tests",
    PROJECT_ROOT / "plugins",
]


def _scan_files(pattern: str, search_paths: list[Path]) -> list[Path]:
    """用 pathlib.rglob + re 零依赖扫描，返回命中文件列表。"""
    regex = re.compile(pattern)
    self_file = Path(__file__).resolve()
    hits: list[Path] = []
    for search_path in search_paths:
        if not search_path.exists():
            continue
        for py_file in search_path.rglob("*.py"):
            if py_file.resolve() == self_file:
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if regex.search(content):
                hits.append(py_file)
    return hits


def _scan_lines(pattern: str, file_path: Path) -> list[str]:
    """用 pathlib + re 零依赖扫描单文件，返回命中行内容。"""
    regex = re.compile(pattern)
    hits: list[str] = []
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return hits
    for i, line in enumerate(content.splitlines(), 1):
        if regex.search(line):
            hits.append(f"{file_path}:{i}:{line.strip()}")
    return hits


class TestCrossChatRemoved:
    """P0-4: CrossChatContextService 整包移除零残留（零依赖扫描）。"""

    def test_cross_chat_directory_removed(self) -> None:
        """src/maisaka/cross_chat/ 目录已删除。"""
        cross_chat_dir = PROJECT_ROOT / "src" / "maisaka" / "cross_chat"
        assert not cross_chat_dir.exists(), f"{cross_chat_dir} 仍存在"

    def test_no_cross_chat_import_anywhere(self) -> None:
        """四目录无 `from src.maisaka.cross_chat` 或 `from .cross_chat` import。"""
        hits = _scan_files(r"from\s+src\.maisaka\.cross_chat|from\s+\.cross_chat", SCAN_PATHS)
        assert hits == [], f"四目录下仍有 cross_chat import 残留: {hits}"

    def test_no_cross_chat_class_reference_anywhere(self) -> None:
        """四目录无 CrossChatContextService / CrossChatContextInjector 类名引用。"""
        hits = _scan_files(
            r"CrossChatContextService|CrossChatContextInjector",
            SCAN_PATHS,
        )
        assert hits == [], f"四目录下仍有 CrossChat 类名引用残留: {hits}"

    def test_fix_import_logging_no_cross_chat(self) -> None:
        """fix_import_logging.py 的 B_CLASS 清单无 cross_chat 路径项。"""
        fix_script = PROJECT_ROOT / "fix_import_logging.py"
        hits = _scan_lines(r"cross_chat/", fix_script)
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
