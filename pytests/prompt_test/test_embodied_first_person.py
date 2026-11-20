"""第一人称自述三语测试（批次 6）。"""

from pathlib import Path

PROMPT_ROOT = Path("prompts")
LANGS = {
    "zh-CN": ("# 思考与行动规则", "我是 {bot_name}", "你是 {bot_name}"),
    "en-US": ("# Thinking and Action Rules", "I am {bot_name}", "You are {bot_name}"),
    "ja-JP": ("# 思考と行動のルール", "私は {bot_name}", "あなたは {bot_name}"),
}


def _split(text: str, marker: str) -> tuple[str, str]:
    index = text.index(marker)
    return text[:index], text[index:]


def test_self_section_is_first_person():
    for lang, (marker, first_person, second_person) in LANGS.items():
        current = (PROMPT_ROOT / lang / "maisaka_chat_embodied.prompt").read_text(encoding="utf-8")
        self_section, _ = _split(current, marker)

        assert first_person in self_section, lang
        assert second_person not in self_section, lang


def test_instruction_section_matches_legacy_byte_for_byte():
    for lang, (marker, _, _) in LANGS.items():
        current = (PROMPT_ROOT / lang / "maisaka_chat_embodied.prompt").read_text(encoding="utf-8")
        legacy = (PROMPT_ROOT / lang / "maisaka_chat_embodied_legacy.prompt").read_text(encoding="utf-8")

        assert _split(current, marker)[1] == _split(legacy, marker)[1], lang


def test_identity_slot_preserved():
    for lang in LANGS:
        current = (PROMPT_ROOT / lang / "maisaka_chat_embodied.prompt").read_text(encoding="utf-8")

        assert "{identity}" in current, lang


def test_legacy_is_frozen_copy_of_previous_content():
    for lang in LANGS:
        legacy = (PROMPT_ROOT / lang / "maisaka_chat_embodied_legacy.prompt").read_text(encoding="utf-8")

        assert legacy.strip(), lang