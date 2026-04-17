from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import logging
import os
import re

from .i18n import get_locale, t
from .i18n.loaders import DEFAULT_LOCALE, extract_placeholders, normalize_locale

logger = logging.getLogger("maibot.prompt_i18n")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_ROOT = (PROJECT_ROOT / "prompts").resolve()
PROMPT_EXTENSIONS = (".prompt",)
SAFE_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
STRICT_ENV_KEYS = ("MAIBOT_PROMPT_I18N_STRICT", "MAIBOT_I18N_STRICT")
STRICT_ENV_VALUES = {"1", "true", "yes", "on"}

extract_prompt_placeholders = extract_placeholders


def get_prompts_root(prompts_root: Path | None = None) -> Path:
    return (prompts_root or PROMPTS_ROOT).resolve()


def normalize_prompt_name(name: str) -> str:
    candidate_name = name.strip()
    for suffix in PROMPT_EXTENSIONS:
        if candidate_name.endswith(suffix):
            candidate_name = candidate_name[: -len(suffix)]
            break

    if candidate_name in {".", ".."} or not candidate_name or not SAFE_SEGMENT_PATTERN.fullmatch(candidate_name):
        raise ValueError(t("prompt.invalid_name", name=name))
    return candidate_name


def normalize_prompt_category(category: str | None) -> str | None:
    if category is None:
        return None

    category_parts = [part for part in category.strip().split("/") if part]
    if not category_parts:
        raise ValueError(t("prompt.invalid_category", category=category))

    for part in category_parts:
        if part in {".", ".."} or not SAFE_SEGMENT_PATTERN.fullmatch(part):
            raise ValueError(t("prompt.invalid_category", category=category))
    return "/".join(category_parts)


def is_strict_prompt_i18n_mode() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True

    return any(os.getenv(env_key, "").strip().lower() in STRICT_ENV_VALUES for env_key in STRICT_ENV_KEYS)


def discover_prompt_locales(prompts_root: Path | None = None) -> list[str]:
    resolved_prompts_root = get_prompts_root(prompts_root)
    if not resolved_prompts_root.exists():
        return []

    locale_names = [path.name for path in resolved_prompts_root.iterdir() if path.is_dir()]
    return sorted(locale_names)


def iter_prompt_files(directory: Path, recursive: bool = True) -> list[Path]:
    if not directory.exists():
        return []

    search = directory.rglob if recursive else directory.glob
    prompt_files: list[Path] = []
    for suffix in PROMPT_EXTENSIONS:
        prompt_files.extend(path for path in search(f"*{suffix}") if path.is_file())
    return sorted(set(prompt_files))


def _raise_duplicate_prompt_name(name: str, first_path: Path, second_path: Path, prompts_root: Path) -> None:
    raise ValueError(
        t(
            "prompt.duplicate_template_name",
            name=name,
            path_a=first_path.relative_to(prompts_root),
            path_b=second_path.relative_to(prompts_root),
        )
    )


def _scan_prompt_directory(directory: Path, prompts_root: Path) -> dict[str, Path]:
    prompt_paths: dict[str, Path] = {}
    for prompt_path in iter_prompt_files(directory):
        prompt_name = prompt_path.stem
        existing_path = prompt_paths.get(prompt_name)
        if existing_path is not None:
            _raise_duplicate_prompt_name(prompt_name, existing_path, prompt_path, prompts_root)
        prompt_paths[prompt_name] = prompt_path
    return prompt_paths


def _iter_prompt_template_layers(prompts_root: Path, requested_locale: str) -> list[Path]:
    prompt_layers: list[Path] = [prompts_root / DEFAULT_LOCALE]
    if requested_locale != DEFAULT_LOCALE:
        prompt_layers.append(prompts_root / requested_locale)
    return prompt_layers


def _iter_locale_candidates(requested_locale: str) -> list[str]:
    locale_candidates: list[str] = [requested_locale]
    if requested_locale != DEFAULT_LOCALE:
        locale_candidates.append(DEFAULT_LOCALE)
    return locale_candidates


def list_prompt_templates(locale: str | None = None, prompts_root: Path | None = None) -> dict[str, Path]:
    resolved_prompts_root = get_prompts_root(prompts_root)
    requested_locale = normalize_locale(locale or get_locale())

    prompt_paths: dict[str, Path] = {}
    for directory in _iter_prompt_template_layers(resolved_prompts_root, requested_locale):
        prompt_paths.update(_scan_prompt_directory(directory, resolved_prompts_root))

    return prompt_paths


def resolve_prompt_path(
    name: str, locale: str | None = None, category: str | None = None, prompts_root: Path | None = None
) -> Path:
    resolved_prompts_root = get_prompts_root(prompts_root)
    normalized_name = normalize_prompt_name(name)
    normalized_category = normalize_prompt_category(category)
    requested_locale = normalize_locale(locale or get_locale())

    if normalized_category is not None:
        for locale_candidate in _iter_locale_candidates(requested_locale):
            base_dir = resolved_prompts_root / locale_candidate
            for suffix in PROMPT_EXTENSIONS:
                candidate_path = (base_dir / normalized_category / f"{normalized_name}{suffix}").resolve()
                if candidate_path.is_file():
                    return candidate_path

                # 允许带 category 的调用继续复用 locale 根目录下的平铺模板。
                fallback_path = (base_dir / f"{normalized_name}{suffix}").resolve()
                if fallback_path.is_file():
                    return fallback_path
    else:
        prompt_paths = list_prompt_templates(locale=requested_locale, prompts_root=resolved_prompts_root)
        if normalized_name in prompt_paths:
            return prompt_paths[normalized_name]

    raise FileNotFoundError(t("prompt.template_not_found", locale=requested_locale, name=normalized_name))


@lru_cache(maxsize=None)
def _read_prompt_template(prompt_path: Path) -> str:
    return prompt_path.read_text(encoding="utf-8")


def _format_prompt_template(name: str, template: str, **kwargs: object) -> str:
    if not kwargs:
        return template

    try:
        return template.format(**kwargs)
    except KeyError as exc:
        missing_placeholder = exc.args[0]
        error = KeyError(t("prompt.missing_placeholder", name=name, placeholder=missing_placeholder))
        if is_strict_prompt_i18n_mode():
            raise error from exc
        logger.error(f"{error}")
        return template
    except Exception as exc:
        logger.error(t("prompt.format_failed", name=name, error=exc))
        if is_strict_prompt_i18n_mode():
            raise
        return template


def load_prompt(
    name: str,
    locale: str | None = None,
    category: str | None = None,
    prompts_root: Path | None = None,
    **kwargs: object,
) -> str:
    normalized_name = normalize_prompt_name(name)
    prompt_path = resolve_prompt_path(name=normalized_name, locale=locale, category=category, prompts_root=prompts_root)
    template = _read_prompt_template(prompt_path)
    return _format_prompt_template(normalized_name, template, **kwargs)


def clear_prompt_cache() -> None:
    _read_prompt_template.cache_clear()
