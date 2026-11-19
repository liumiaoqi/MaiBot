"""类型感知 TOML 合并的承重测试（全合成 fixture，不读真实配置）。

约束：
- 不出现 `docker-config` / `config/bot_config.toml` 字面量；
- fixture 值均不等于 schema 默认值；
- 承重项：既有 `InlineTable` 分支——漏掉它会让段头数暴涨（真机 76→132）。
"""

import hashlib
import re
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import tomlkit

import src.common.utils.toml_utils as toml_utils
from src.common.utils.toml_utils import _update_toml_doc

TYPED_MERGE_FIXTURE = '''[a_memorix.connectionist]
inner_voices = { welt = [
    { name = "规则甲", style = "direct", focus_concepts = ["概念甲"], weight_multiplier = 1.11 },
    { name = "规则乙", style = "soft", focus_concepts = ["概念乙"], weight_multiplier = 1.22 },
    { name = "规则丙", style = "playful", focus_concepts = ["概念丙"], weight_multiplier = 1.33 },
] }

[a_memorix.connectionist.personality]
bronya = { title = "合成角色", attention_tags = ["标签甲", "标签乙"], weight_multiplier = 1.55 }
'''

SECTION_ARRAY_FIXTURE = '''[chat.reply_timing]
talk_value_rules = [
    { name = "规则一", threshold = 0.41, weight = 1.21 },
    { name = "规则二", threshold = 0.62, weight = 1.42 },
]

[expression]
learning_list = [
    { id = "表达甲", phrase = "合成短语", weight = 1.13 },
]

[jargon]
learning_list = [
    { id = "黑话甲", phrase = "合成词一", weight = 1.24 },
    { id = "黑话乙", phrase = "合成词二", weight = 1.35 },
]
'''

AOT_FIXTURE = '''[[models]]
name = "模型甲"
api_provider = "提供商甲"

[[models]]
name = "模型乙"
api_provider = "提供商乙"

[[models]]
name = "模型丙"
api_provider = "提供商丙"

[[api_providers]]
name = "提供商甲"
base_url = "https://example.invalid/甲"

[[api_providers]]
name = "提供商乙"
base_url = "https://example.invalid/乙"
'''


def _write(tmp_path: Path, text: str, name: str = "synthetic.toml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return tomlkit.load(f)


def _dump(doc: Any) -> str:
    return tomlkit.dumps(doc)


def _count_comment_lines(text: str) -> int:
    return sum(1 for line in text.splitlines() if re.match(r"^\s*#", line))


def _count_section_headers(text: str) -> int:
    return sum(1 for line in text.splitlines() if re.match(r"^\s*\[\[?", line))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tomllib_plain(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _assert_inline_chain(doc: Any, role: str, rules_per_role: int) -> None:
    inner = doc["a_memorix"]["connectionist"]["inner_voices"]
    assert type(inner).__name__ == "InlineTable", f"inner_voices 类型={type(inner).__name__}"
    rules = inner[role]
    assert type(rules).__name__ == "Array", f"{role} 类型={type(rules).__name__}"
    assert len(rules) == rules_per_role
    for rule in rules:
        assert type(rule).__name__ == "InlineTable"


def _legacy_update_toml_doc(target: Any, source: Any) -> None:
    """修复前实现的逐行等价副本，仅用于 T11 反证 fixture 承重。"""
    if isinstance(source, list) or not isinstance(source, dict) or not isinstance(target, dict):
        return
    for key, value in source.items():
        if key == "version":
            continue
        if key in target:
            target_value = target[key]
            if isinstance(value, dict) and isinstance(target_value, dict):
                _legacy_update_toml_doc(target_value, value)
            else:
                try:
                    target[key] = tomlkit.item(value)
                except (TypeError, ValueError):
                    target[key] = value
        else:
            try:
                target[key] = tomlkit.item(value)
            except (TypeError, ValueError):
                target[key] = value


def _typed_payload() -> dict[str, Any]:
    return {
        "inner_voices": {
            "welt": [
                {"name": "新甲", "style": "x", "focus_concepts": ["新一"], "weight_multiplier": 2.11},
                {"name": "新乙", "style": "y", "focus_concepts": ["新二"], "weight_multiplier": 2.22},
                {"name": "新丙", "style": "z", "focus_concepts": ["新三"], "weight_multiplier": 2.33},
            ]
        }
    }


def test_t1_inline_table_keeps_inner_array(tmp_path: Path) -> None:
    doc = _load(_write(tmp_path, TYPED_MERGE_FIXTURE))
    _update_toml_doc(doc["a_memorix"]["connectionist"], _typed_payload())

    text = _dump(doc)
    tomlkit.loads(text)
    tomllib.loads(text)
    _assert_inline_chain(doc, "welt", 3)
    assert "welt = name =" not in text
    assert "[[a_memorix.connectionist.inner_voices" not in text


def test_t2_section_arrays_stay_arrays(tmp_path: Path) -> None:
    doc = _load(_write(tmp_path, SECTION_ARRAY_FIXTURE))
    _update_toml_doc(
        doc,
        {
            "chat": {"reply_timing": {"talk_value_rules": [{"name": "改写", "threshold": 0.77, "weight": 1.77}]}},
            "expression": {"learning_list": [{"id": "表达乙", "phrase": "改写短语", "weight": 1.44}]},
            "jargon": {"learning_list": [{"id": "黑话丙", "phrase": "改写词", "weight": 1.55}]},
        },
    )

    text = _dump(doc)
    tomlkit.loads(text)
    tomllib.loads(text)
    assert type(doc["chat"]["reply_timing"]["talk_value_rules"]).__name__ == "Array"
    assert type(doc["expression"]["learning_list"]).__name__ == "Array"
    assert type(doc["jargon"]["learning_list"]).__name__ == "Array"
    assert "[[chat.reply_timing.talk_value_rules]]" not in text
    assert "[[expression.learning_list]]" not in text


def test_t3_aot_unchanged(tmp_path: Path) -> None:
    path = _write(tmp_path, AOT_FIXTURE)
    before = _count_section_headers(path.read_text(encoding="utf-8"))
    doc = _load(path)
    _update_toml_doc(
        doc,
        {
            "api_providers": [
                {"name": "提供商乙", "base_url": "https://example.invalid/乙改"},
                {"name": "提供商丙", "base_url": "https://example.invalid/丙"},
            ]
        },
    )

    text = _dump(doc)
    tomllib.loads(text)
    assert len(doc["models"]) == 3
    assert len(doc["api_providers"]) == 2
    assert _count_section_headers(text) == before


def test_t4_new_keys_follow_parent_type(tmp_path: Path) -> None:
    doc = _load(_write(tmp_path, TYPED_MERGE_FIXTURE))
    _update_toml_doc(
        doc["a_memorix"]["connectionist"],
        {"inner_voices": {"silver_wolf": [{"name": "新增", "style": "s", "focus_concepts": ["新"], "weight_multiplier": 2.44}]}},
    )
    text = _dump(doc)
    tomlkit.loads(text)
    tomllib.loads(text)
    _assert_inline_chain(doc, "silver_wolf", 1)

    doc2 = _load(_write(tmp_path, SECTION_ARRAY_FIXTURE, "second.toml"))
    _update_toml_doc(doc2["expression"], {"new_table": {"a": 1}})
    text2 = _dump(doc2)
    tomllib.loads(text2)
    assert type(doc2["expression"]["new_table"]).__name__ == "Table"


def test_t11_legacy_implementation_breaks_fixture(tmp_path: Path) -> None:
    doc = _load(_write(tmp_path, TYPED_MERGE_FIXTURE))
    _legacy_update_toml_doc(doc["a_memorix"]["connectionist"], _typed_payload())

    broke = False
    try:
        text = _dump(doc)
        tomlkit.loads(text)
        broke = type(doc["a_memorix"]["connectionist"]["inner_voices"]["welt"]).__name__ == "AoT"
    except Exception:
        broke = True

    assert broke, "旧实现未触发缺陷：fixture 不承重"

def test_t5_none_skipped_with_warning(tmp_path: Path, monkeypatch) -> None:
    doc = _load(_write(tmp_path, TYPED_MERGE_FIXTURE))
    original = doc["a_memorix"]["connectionist"]["inner_voices"]["welt"]
    messages: list[str] = []
    monkeypatch.setattr(toml_utils.logger, "warning", lambda msg: messages.append(msg))

    _update_toml_doc(doc["a_memorix"]["connectionist"], {"inner_voices": {"welt": None}})

    assert doc["a_memorix"]["connectionist"]["inner_voices"]["welt"] is original
    assert any("跳过 None" in msg and "welt" in msg for msg in messages)


def test_gate_rejects_when_tomlkit_fails(tmp_path: Path, monkeypatch) -> None:
    path = _write(tmp_path, TYPED_MERGE_FIXTURE)
    before = path.read_bytes()

    def boom(_text):
        raise ValueError("tomlkit-boom")

    monkeypatch.setattr(toml_utils.tomlkit, "loads", boom)
    with pytest.raises(ValueError, match="配置写入被拒绝"):
        toml_utils.save_toml_with_format({"x": 1}, str(path))

    assert path.read_bytes() == before


def test_gate_rejects_when_tomllib_fails(tmp_path: Path, monkeypatch) -> None:
    path = _write(tmp_path, TYPED_MERGE_FIXTURE)
    before = path.read_bytes()

    def boom(_text):
        raise ValueError("tomllib-boom")

    monkeypatch.setattr(toml_utils, "tomllib", SimpleNamespace(loads=boom))
    with pytest.raises(ValueError, match="配置写入被拒绝"):
        toml_utils.save_toml_with_format({"x": 1}, str(path))

    assert path.read_bytes() == before