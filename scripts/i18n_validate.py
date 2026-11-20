from __future__ import annotations

from pathlib import Path
from typing import Callable

import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.i18n.loaders import (  # noqa: E402
    DEFAULT_LOCALE,
    PLURAL_CATEGORIES,
    TranslationValue,
    discover_locales,
    get_locales_root,
    load_locale_catalog,
)
from src.common.i18n.loaders import extract_placeholders  # noqa: E402
from src.common.prompt_i18n import (  # noqa: E402
    discover_prompt_locales,
    extract_prompt_placeholders,
    get_prompts_root,
    iter_prompt_files,
)

HAN_CHARACTER_PATTERN = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")
I18NEXT_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^\s,}]+)(?:\s*,[^}]*)?\s*\}\}")


def contains_han_characters(text: str) -> bool:
    return HAN_CHARACTER_PATTERN.search(text) is not None


def extract_i18next_placeholders(template: str) -> set[str]:
    placeholders: set[str] = set()
    for match in I18NEXT_PLACEHOLDER_PATTERN.finditer(template):
        placeholder_name = match.group(1)
        placeholders.add(placeholder_name.split(".", maxsplit=1)[0].split("[", maxsplit=1)[0])
    return placeholders


def iter_translation_strings(value: TranslationValue) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [value[category] for category in sorted(value.keys())]


def iter_shared_translation_strings(
    source_value: TranslationValue, target_value: TranslationValue
) -> list[tuple[str, str]]:
    if isinstance(source_value, str) or isinstance(target_value, str):
        if isinstance(source_value, str) and isinstance(target_value, str):
            return [(source_value, target_value)]
        return []

    shared_categories = sorted(set(source_value.keys()) & set(target_value.keys()))
    return [(source_value[category], target_value[category]) for category in shared_categories]


def locale_requires_latin_only_validation(locale: str) -> bool:
    normalized_locale = locale.lower()
    return normalized_locale == "en" or normalized_locale.startswith("en-")


def validate_locale_content(
    key: str,
    source_value: TranslationValue,
    target_value: TranslationValue,
    locale: str,
    errors: list[str],
    locale_label: str | None = None,
) -> None:
    resolved_locale_label = locale_label or locale
    target_texts = iter_translation_strings(target_value)

    if any(
        source_text == target_text and contains_han_characters(source_text)
        for source_text, target_text in iter_shared_translation_strings(source_value, target_value)
    ):
        errors.append(
            f"[{resolved_locale_label}] key '{key}' 直接保留了包含中文字符的 source 文案（仓库级校验策略），请提供目标语言翻译"
        )

    if locale_requires_latin_only_validation(locale) and any(contains_han_characters(text) for text in target_texts):
        errors.append(f"[{resolved_locale_label}] key '{key}' 仍包含中文字符，请移除源语言残留后再提交")


def validate_translation_pair(
    key: str,
    source_value: TranslationValue,
    target_value: TranslationValue,
    locale: str,
    errors: list[str],
    placeholder_extractor: Callable[[str], set[str]] = extract_placeholders,
    locale_label: str | None = None,
) -> None:
    resolved_locale_label = locale_label or locale
    if isinstance(source_value, str):
        if not isinstance(target_value, str):
            errors.append(
                f"[{resolved_locale_label}] key '{key}' 与 source 的类型不一致：source=string, target=plural"
            )
            return
        if placeholder_extractor(source_value) != placeholder_extractor(target_value):
            errors.append(f"[{resolved_locale_label}] key '{key}' 的占位符集合与 source 不一致")
        return

    if not isinstance(target_value, dict):
        errors.append(f"[{resolved_locale_label}] key '{key}' 与 source 的类型不一致：source=plural, target=string")
        return

    source_categories = set(source_value.keys())
    target_categories = set(target_value.keys())
    if source_categories != target_categories:
        errors.append(
            f"[{resolved_locale_label}] key '{key}' 的 plural category 不一致："
            f"source={sorted(source_categories)}, target={sorted(target_categories)}"
        )

    for category in sorted(source_categories & target_categories):
        source_placeholders = placeholder_extractor(source_value[category])
        target_placeholders = placeholder_extractor(target_value[category])
        if source_placeholders != target_placeholders:
            errors.append(
                f"[{resolved_locale_label}] key '{key}' 的 plural category '{category}' 占位符集合与 source 不一致"
            )


def is_plural_translation_node(value: object) -> bool:
    if not isinstance(value, dict) or not value:
        return False

    return all(
        isinstance(category, str) and category in PLURAL_CATEGORIES and isinstance(category_value, str)
        for category, category_value in value.items()
    )


def validate_json_locales(locales_root: Path | None = None) -> list[str]:
    resolved_locales_root = get_locales_root(locales_root)
    locales = discover_locales(resolved_locales_root)
    errors: list[str] = []

    if DEFAULT_LOCALE not in locales:
        errors.append(f"缺少默认 locale 目录: {DEFAULT_LOCALE}")
        return errors

    catalogs: dict[str, dict[str, TranslationValue]] = {}
    for locale in locales:
        try:
            catalogs[locale] = load_locale_catalog(locale, resolved_locales_root)
        except Exception as exc:
            errors.append(f"[{locale}] 加载失败: {exc}")

    source_catalog = catalogs.get(DEFAULT_LOCALE)
    if source_catalog is None:
        return errors

    source_keys = set(source_catalog.keys())
    for locale, catalog in catalogs.items():
        if locale == DEFAULT_LOCALE:
            continue

        locale_keys = set(catalog.keys())
        for key in sorted(source_keys - locale_keys):
            errors.append(f"[{locale}] 缺少 key: {key}")
        for key in sorted(locale_keys - source_keys):
            errors.append(f"[{locale}] 存在多余 key: {key}")

        for key in sorted(source_keys & locale_keys):
            source_value = source_catalog[key]
            target_value = catalog[key]
            validate_translation_pair(key, source_value, target_value, locale, errors)
            if isinstance(source_value, str) == isinstance(target_value, str):
                validate_locale_content(key, source_value, target_value, locale, errors)

    return errors


def build_prompt_catalog(locale_dir: Path) -> dict[Path, Path]:
    return {path.relative_to(locale_dir): path for path in iter_prompt_files(locale_dir)}


def validate_prompt_templates(prompts_root: Path | None = None) -> tuple[list[str], list[str]]:
    resolved_prompts_root = get_prompts_root(prompts_root)
    prompt_locales = set(discover_prompt_locales(resolved_prompts_root))
    known_locales = [locale for locale in discover_locales(get_locales_root()) if locale != DEFAULT_LOCALE]
    errors: list[str] = []
    warnings: list[str] = []

    if DEFAULT_LOCALE not in prompt_locales:
        errors.append(f"缺少默认 Prompt locale 目录: {DEFAULT_LOCALE}")
        return errors, warnings

    source_dir = resolved_prompts_root / DEFAULT_LOCALE
    source_files = build_prompt_catalog(source_dir)
    source_relative_paths = set(source_files.keys())

    for locale in known_locales:
        locale_dir = resolved_prompts_root / locale
        if not locale_dir.exists():
            warnings.append(f"[prompt:{locale}] 缺少 locale 目录，运行时将回退到 {DEFAULT_LOCALE}")
            continue

        locale_files = build_prompt_catalog(locale_dir)
        locale_relative_paths = set(locale_files.keys())

        for relative_path in sorted(source_relative_paths - locale_relative_paths):
            warnings.append(f"[prompt:{locale}] 缺少模板: {relative_path.as_posix()}，运行时将回退到 {DEFAULT_LOCALE}")

        for relative_path in sorted(locale_relative_paths - source_relative_paths):
            warnings.append(f"[prompt:{locale}] 存在额外模板: {relative_path.as_posix()}")

        for relative_path in sorted(source_relative_paths & locale_relative_paths):
            source_text = source_files[relative_path].read_text(encoding="utf-8")
            locale_text = locale_files[relative_path].read_text(encoding="utf-8")

            source_placeholders = extract_prompt_placeholders(source_text)
            locale_placeholders = extract_prompt_placeholders(locale_text)
            if source_placeholders != locale_placeholders:
                errors.append(
                    "[prompt:{locale}] 模板 '{path}' 的占位符集合与 source 不一致："
                    "source={source_placeholders}, target={target_placeholders}".format(
                        locale=locale,
                        path=relative_path.as_posix(),
                        source_placeholders=sorted(source_placeholders),
                        target_placeholders=sorted(locale_placeholders),
                    )
                )

            if source_text == locale_text:
                warnings.append(f"[prompt:{locale}] 模板 '{relative_path.as_posix()}' 与 source 完全相同，可能尚未翻译")

    return errors, warnings


def _print_warnings(warnings: list[str]) -> None:
    if not warnings:
        return
    print(f"warnings ({len(warnings)}):")
    for warning in warnings[:10]:
        print(f"  - {warning}")
    if len(warnings) > 10:
        print(f"  - ... 另外还有 {len(warnings) - 10} 条 warning")


def main() -> int:
    errors = validate_json_locales()
    prompt_errors, prompt_warnings = validate_prompt_templates()
    errors.extend(prompt_errors)

    if errors:
        print("i18n validation failed:")
        for error in errors:
            print(f"  - {error}")
        _print_warnings(prompt_warnings)
        return 1

    print("i18n validation passed.")
    _print_warnings(prompt_warnings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
