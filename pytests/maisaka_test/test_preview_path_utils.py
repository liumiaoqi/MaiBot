"""preview_path_utils 单元测试。

覆盖 normalize_preview_name / normalize_platform_name /
build_preview_chat_dir_name / build_display_path / build_file_uri。
测试环境未注册 SessionInfoPort，build_preview_chat_dir_name 走 fallback 路径。
"""

from pathlib import Path

from src.maisaka.display.preview_path_utils import (
    REPO_ROOT,
    build_display_path,
    build_file_uri,
    build_preview_chat_dir_name,
    normalize_platform_name,
    normalize_preview_name,
)


class TestNormalizePreviewName:
    """normalize_preview_name 行为测试。"""

    def test_plain_ascii_unchanged(self):
        assert normalize_preview_name("abc123") == "abc123"

    def test_chinese_replaced_with_underscore(self):
        # 纯中文被替换为下划线后 strip 为空，返回 unknown
        result = normalize_preview_name("测试名称")
        assert result == "unknown"

    def test_mixed_chinese_and_ascii(self):
        # 中英混合：中文变 _，尾部下划线被 strip 去掉
        result = normalize_preview_name("abc测试")
        assert result == "abc"

    def test_chinese_between_ascii(self):
        # 中文夹在 ASCII 中间时保留中间下划线
        result = normalize_preview_name("a测b")
        assert result == "a_b"

    def test_special_chars_replaced(self):
        result = normalize_preview_name("a/b\\c:d")
        assert "/" not in result
        assert "\\" not in result
        assert ":" not in result

    def test_empty_returns_unknown(self):
        assert normalize_preview_name("") == "unknown"

    def test_none_returns_unknown(self):
        assert normalize_preview_name(None) == "unknown"

    def test_only_invalid_chars_returns_unknown(self):
        # 全是非法字符归一化后为空，返回 unknown
        assert normalize_preview_name("///") == "unknown"

    def test_strips_leading_trailing_dots(self):
        result = normalize_preview_name("..abc..")
        assert result == "abc"

    def test_preserves_dash_and_dot(self):
        assert normalize_preview_name("a-b.c") == "a-b.c"


class TestNormalizePlatformName:
    """normalize_platform_name 行为测试。"""

    def test_telegram_alias_to_tg(self):
        assert normalize_platform_name("telegram") == "tg"

    def test_telegram_case_insensitive(self):
        assert normalize_platform_name("Telegram") == "tg"

    def test_qq_unchanged(self):
        assert normalize_platform_name("qq") == "qq"

    def test_empty_returns_unknown(self):
        assert normalize_platform_name("") == "unknown"

    def test_none_returns_unknown(self):
        assert normalize_platform_name(None) == "unknown"


class TestBuildPreviewChatDirName:
    """build_preview_chat_dir_name 行为测试。

    测试环境未注册 SessionInfoPort，get_session_info 返回 None，
    走 fallback 路径。
    """

    def test_normal_chat_id(self):
        result = build_preview_chat_dir_name("123456")
        assert result == "123456"

    def test_chinese_chat_id_normalized(self):
        # 纯中文归一化为空，返回 unknown_chat
        result = build_preview_chat_dir_name("测试群")
        assert result == "unknown_chat"

    def test_mixed_chat_id(self):
        # 中英混合保留 ASCII 部分
        result = build_preview_chat_dir_name("123测试")
        assert result == "123"

    def test_empty_chat_id_returns_unknown_chat(self):
        # 空字符串归一化为 unknown，再走 unknown_chat 分支
        assert build_preview_chat_dir_name("") == "unknown_chat"

    def test_none_chat_id_returns_unknown_chat(self):
        assert build_preview_chat_dir_name(None) == "unknown_chat"


class TestBuildDisplayPath:
    """build_display_path 行为测试。"""

    def test_path_inside_repo_returns_relative(self):
        file_path = REPO_ROOT / "src" / "maisaka" / "display" / "display_utils.py"
        result = build_display_path(file_path)
        assert result == "src/maisaka/display/display_utils.py"

    def test_path_outside_repo_returns_absolute(self):
        # 构造一个不在 repo 内的路径
        external_path = Path("Z:/some/external/path.txt")
        result = build_display_path(external_path)
        assert result.endswith("path.txt")


class TestBuildFileUri:
    """build_file_uri 行为测试。"""

    def test_returns_file_uri_scheme(self):
        file_path = REPO_ROOT / "test.txt"
        result = build_file_uri(file_path)
        assert result.startswith("file:///")

    def test_uri_contains_encoded_path(self):
        file_path = REPO_ROOT / "data" / "test.json"
        result = build_file_uri(file_path)
        assert "test.json" in result