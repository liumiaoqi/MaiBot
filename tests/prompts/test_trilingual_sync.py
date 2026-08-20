"""三语模板同步校验（zh-CN / en-US / ja-JP）。

防止某语言模板字段名遗漏或关键指令行数大幅漂移导致回归。
"""

import re
from pathlib import Path

import pytest

_PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"
_LANGUAGES = ("zh-CN", "en-US", "ja-JP")
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_LINE_COUNT_TOLERANCE = 0.5


def _prompt_files(lang: str) -> set[str]:
    lang_dir = _PROMPTS_ROOT / lang
    if not lang_dir.is_dir():
        return set()
    return {f.name for f in lang_dir.glob("*.prompt")}


def _read_prompt(lang: str, filename: str) -> str:
    return (_PROMPTS_ROOT / lang / filename).read_text(encoding="utf-8")


def _extract_placeholders(text: str) -> set[str]:
    return set(_PLACEHOLDER_RE.findall(text))


@pytest.fixture
def _expected_files() -> set[str]:
    return _prompt_files("zh-CN")


class TestTrilingualFileSet:
    """三语目录应包含同一组 .prompt 文件。"""

    def test_all_languages_have_same_file_set(self):
        file_sets = {lang: _prompt_files(lang) for lang in _LANGUAGES}
        zh = file_sets["zh-CN"]
        for lang in _LANGUAGES:
            assert file_sets[lang] == zh, (
                f"模板文件集合不一致: zh-CN 独有 {zh - file_sets[lang]}, "
                f"{lang} 独有 {file_sets[lang] - zh}"
            )


class TestTrilingualPlaceholders:
    """三语模板的占位符字段名应完全一致。"""

    @pytest.fixture(params=list(_prompt_files("zh-CN")))
    def _prompt_filename(self, request) -> str:
        return request.param

    def test_placeholders_match_across_languages(self, _prompt_filename: str):
        zh_text = _read_prompt("zh-CN", _prompt_filename)
        zh_fields = _extract_placeholders(zh_text)
        for lang in ("en-US", "ja-JP"):
            lang_text = _read_prompt(lang, _prompt_filename)
            lang_fields = _extract_placeholders(lang_text)
            assert lang_fields == zh_fields, (
                f"{_prompt_filename}: 占位符不一致, "
                f"zh-CN 独有 {zh_fields - lang_fields}, "
                f"{lang} 独有 {lang_fields - zh_fields}"
            )


class TestTrilingualLineCount:
    """三语模板行数应在合理容差范围内（防翻译大幅漂移）。"""

    @pytest.fixture(params=list(_prompt_files("zh-CN")))
    def _prompt_filename(self, request) -> str:
        return request.param

    def test_line_count_within_tolerance(self, _prompt_filename: str):
        zh_lines = len(_read_prompt("zh-CN", _prompt_filename).strip().splitlines())
        for lang in ("en-US", "ja-JP"):
            lang_lines = len(_read_prompt(lang, _prompt_filename).strip().splitlines())
            if zh_lines == 0:
                assert lang_lines == 0, f"{_prompt_filename}: zh-CN 空但 {lang} 非空"
                continue
            ratio = abs(lang_lines - zh_lines) / zh_lines
            assert ratio <= _LINE_COUNT_TOLERANCE, (
                f"{_prompt_filename}: 行数漂移过大, "
                f"zh-CN={zh_lines}行, {lang}={lang_lines}行, "
                f"偏差={ratio:.0%} > 容差={_LINE_COUNT_TOLERANCE:.0%}"
            )