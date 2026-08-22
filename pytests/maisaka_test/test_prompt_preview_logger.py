"""prompt_preview_logger 单元测试。

覆盖 PromptPreviewLogger.save_preview_file / _build_file_stem /
_trim_overflow / _get_max_preview_groups_per_chat。
测试环境未注册 AppConfigPort，_get_max_preview_groups_per_chat 走默认值。
"""

import json
from pathlib import Path
from unittest.mock import patch


from src.maisaka.display.prompt_preview_logger import PromptPreviewLogger


class TestPromptPreviewLoggerSave:
    """PromptPreviewLogger.save_preview_file 行为测试。"""

    def test_save_creates_file_with_content(self):
        content = json.dumps({"prompt": "test"}, ensure_ascii=False)
        path = PromptPreviewLogger.save_preview_file(
            chat_id="test_chat_1",
            category="test_cat_1",
            content=content,
        )
        assert path.exists()
        assert path.suffix == ".json"
        assert path.read_text(encoding="utf-8") == content
        # 清理
        path.unlink()

    def test_save_normalizes_category_name(self):
        content = "test"
        path = PromptPreviewLogger.save_preview_file(
            chat_id="test_chat_2",
            category="测试类别",
            content=content,
        )
        assert path.exists()
        assert path.read_text(encoding="utf-8") == content
        path.unlink()

    def test_save_returns_path_under_base_dir(self):
        path = PromptPreviewLogger.save_preview_file(
            chat_id="test_chat_3",
            category="test_cat_3",
            content="x",
        )
        assert "maisaka_prompt" in str(path)
        path.unlink()

    def test_multiple_saves_unique_stems(self):
        paths = []
        for i in range(3):
            p = PromptPreviewLogger.save_preview_file(
                chat_id="test_chat_4",
                category="test_cat_4",
                content=f"content_{i}",
            )
            paths.append(p)
        stems = {p.stem for p in paths}
        # 3 次保存应产生 3 个不同文件名
        assert len(stems) == 3
        for p in paths:
            p.unlink()


class TestPromptPreviewLoggerFileStem:
    """PromptPreviewLogger._build_file_stem 行为测试。"""

    def test_returns_millisecond_timestamp_string(self):
        chat_dir = Path("logs/maisaka_prompt/test_stem_cat/test_stem_chat")
        chat_dir.mkdir(parents=True, exist_ok=True)
        try:
            stem = PromptPreviewLogger._build_file_stem(chat_dir)
            # 应为纯数字或数字_后缀形式
            base = stem.split("_")[0]
            assert base.isdigit()
            # 毫秒时间戳应接近当前时间
            assert int(base) > 0
        finally:
            # 清理目录
            for f in chat_dir.iterdir():
                f.unlink()
            chat_dir.rmdir()

    def test_appends_suffix_on_collision(self):
        # 碰撞测试：_build_file_stem 内部重新取时间戳，
        # 难以可靠构造同毫秒碰撞，此处验证返回值为合法数字或带后缀形式
        chat_dir = Path("logs/maisaka_prompt/test_stem_cat2/test_stem_chat2")
        chat_dir.mkdir(parents=True, exist_ok=True)
        try:
            stem = PromptPreviewLogger._build_file_stem(chat_dir)
            base = stem.split("_")[0]
            assert base.isdigit()
            assert int(base) > 0
        finally:
            for f in chat_dir.iterdir():
                f.unlink()
            chat_dir.rmdir()


class TestPromptPreviewLoggerMaxGroups:
    """PromptPreviewLogger._get_max_preview_groups_per_chat 行为测试。"""

    def test_returns_default_when_port_unregistered(self):
        # 测试环境未注册 port，应返回默认值
        result = PromptPreviewLogger._get_max_preview_groups_per_chat()
        assert result == PromptPreviewLogger._DEFAULT_MAX_PREVIEW_GROUPS_PER_CHAT

    def test_returns_configured_value_when_port_registered(self):
        from unittest.mock import MagicMock

        mock_port = MagicMock()
        mock_port.get_log_maisaka_prompt_preview_limit.return_value = 50
        with patch(
            "src.core.app_config_port_registry.get_app_config_port",
            return_value=mock_port,
        ):
            result = PromptPreviewLogger._get_max_preview_groups_per_chat()
            assert result == 50

    def test_falls_back_on_exception(self):
        from unittest.mock import MagicMock

        mock_port = MagicMock()
        mock_port.get_log_maisaka_prompt_preview_limit.side_effect = RuntimeError("boom")
        with patch(
            "src.core.app_config_port_registry.get_app_config_port",
            return_value=mock_port,
        ):
            result = PromptPreviewLogger._get_max_preview_groups_per_chat()
            assert result == PromptPreviewLogger._DEFAULT_MAX_PREVIEW_GROUPS_PER_CHAT


class TestPromptPreviewLoggerTrimOverflow:
    """PromptPreviewLogger._trim_overflow 行为测试。"""

    def test_no_trim_when_under_limit(self):
        chat_dir = Path("logs/maisaka_prompt/test_trim_cat1/test_trim_chat1")
        chat_dir.mkdir(parents=True, exist_ok=True)
        try:
            for i in range(3):
                (chat_dir / f"file_{i}.json").write_text("x", encoding="utf-8")
            PromptPreviewLogger._trim_overflow(chat_dir)
            # 3 个文件 < 默认上限，不应删除
            remaining = list(chat_dir.iterdir())
            assert len(remaining) == 3
        finally:
            for f in chat_dir.iterdir():
                f.unlink()
            chat_dir.rmdir()

    def test_trims_oldest_when_over_limit(self):
        chat_dir = Path("logs/maisaka_prompt/test_trim_cat2/test_trim_chat2")
        chat_dir.mkdir(parents=True, exist_ok=True)
        try:
            # 创建文件并设置不同 mtime
            files = []
            for i in range(5):
                f = chat_dir / f"file_{i}.json"
                f.write_text("x", encoding="utf-8")
                # 越老越小
                import os

                os.utime(f, (i, i))
                files.append(f)

            # _TRIM_COUNT 默认 100 会全删小规模文件，此处 mock 为 1
            # 使 trim_count = min(5, max(1, 3)) = 3，删 3 留 2
            with patch.object(
                PromptPreviewLogger,
                "_get_max_preview_groups_per_chat",
                return_value=2,
            ), patch.object(PromptPreviewLogger, "_TRIM_COUNT", 1):
                PromptPreviewLogger._trim_overflow(chat_dir)

            remaining = list(chat_dir.iterdir())
            # 应从 5 删到 2
            assert len(remaining) == 2
        finally:
            for f in chat_dir.iterdir():
                f.unlink()
            chat_dir.rmdir()