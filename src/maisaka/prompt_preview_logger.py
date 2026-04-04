"""Maisaka Prompt 预览落盘器。"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Dict
from uuid import uuid4

from src.config.config import global_config


class PromptPreviewLogger:
    """负责保存 Maisaka Prompt 预览文件并控制目录容量。"""

    _BASE_DIR = Path("logs") / "maisaka_prompt"
    _TRIM_COUNT = 100
    _SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")

    @classmethod
    def _get_max_per_chat(cls) -> int:
        """从配置中获取每个聊天流最大保存的预览数量。"""

        return getattr(global_config.chat, "plan_reply_log_max_per_chat", 1000)

    @classmethod
    def _normalize_chat_id(cls, chat_id: str) -> str:
        normalized_chat_id = cls._SAFE_NAME_PATTERN.sub("_", str(chat_id or "").strip()).strip("._")
        if normalized_chat_id:
            return normalized_chat_id
        return "unknown_chat"

    @classmethod
    def save_preview_files(
        cls,
        chat_id: str,
        category: str,
        files: Dict[str, str],
    ) -> Dict[str, Path]:
        """保存同一份 Prompt 预览的多个文件并执行超量清理。"""

        normalized_category = cls._normalize_chat_id(category)
        chat_dir = (cls._BASE_DIR / normalized_category / cls._normalize_chat_id(chat_id)).resolve()
        chat_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{int(time.time() * 1000)}_{uuid4().hex[:8]}"
        saved_paths: Dict[str, Path] = {}
        try:
            for suffix, content in files.items():
                normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
                file_path = chat_dir / f"{stem}{normalized_suffix}"
                file_path.write_text(content, encoding="utf-8")
                saved_paths[normalized_suffix] = file_path
        finally:
            cls._trim_overflow(chat_dir)
        return saved_paths

    @classmethod
    def _trim_overflow(cls, chat_dir: Path) -> None:
        """超过阈值时按批次删除最老的若干组预览文件。"""

        grouped_files: dict[str, list[Path]] = {}
        for file_path in chat_dir.iterdir():
            if not file_path.is_file():
                continue
            grouped_files.setdefault(file_path.stem, []).append(file_path)

        max_per_chat = cls._get_max_per_chat()
        if len(grouped_files) <= max_per_chat:
            return

        sorted_groups = sorted(
            grouped_files.items(),
            key=lambda item: min(path.stat().st_mtime for path in item[1]),
        )
        overflow_count = len(grouped_files) - max_per_chat
        trim_count = min(len(sorted_groups), max(cls._TRIM_COUNT, overflow_count))
        for _, file_group in sorted_groups[:trim_count]:
            for old_file in file_group:
                try:
                    old_file.unlink()
                except FileNotFoundError:
                    continue
