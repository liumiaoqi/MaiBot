"""P1.1 写路径测试：升级改写不吃未知字段（§七）+ 落盘原子性。

两件事都属**既有缺陷**（`git show HEAD:` 同样如此），修法对齐 `toml_utils.py:95-115` 的既有先例：
- P1.1a：改写走**就地更新**（读原 doc、只改已知键），模板里没有的键一律不动；
- P1.1b：落盘走 tmp + `os.replace`（要么旧文件、要么新文件，不留半截）。
"""

import hashlib
import os
from pathlib import Path
from typing import Any

import pytest
import tomlkit

from src.config.config import Config, load_config_from_file, write_config_to_file

BOT_CONFIG_NAME = "bot_config.toml"

# 旧形状配置：带自定义键、用户注释、旧版迁移留档
# ⚠️ TOML：根键必须写在第一个表头之前，所以 custom_scalar 放在文件最前
OLD_SHAPE_BOT = '''# 用户手写的文件头注释（改写后必须还在）
custom_scalar = 7

[inner]
version = "8.14.18"

[[_migrations]]
id = "8.10.11"
from = "8.10.0"
to = "8.10.11"
at = "2026-10-15T12:00:00+08:00"

[custom_unknown_table]
note = "别的程序写的键"

[chat]
max_context_size = 42 # 用户改过的值必须活下来
group_chat_prompt = "旧群聊提示词"
my_custom_knob = "用户自定义"
'''


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_old_shape_bot(path: Path) -> None:
    path.write_text(OLD_SHAPE_BOT, encoding="utf-8")


# ════════════════════════════════════════════════════════════════════
# P1.1a · 未知字段在升级改写后仍在
# ════════════════════════════════════════════════════════════════════


def test_upgrade_rewrite_keeps_unknown_fields_and_comments(tmp_path: Path):
    """升级改写：自定义表 / 自定义键 / 用户注释一字不动，同时该迁的确实迁了。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_old_shape_bot(config_path)

    _, updated = load_config_from_file(Config, config_path, "8.14.19")

    assert updated is True
    text = config_path.read_text(encoding="utf-8")
    document = tomlkit.loads(text)

    # 未知字段：顶层标量、未知表、已知段里的自定义键
    assert document["custom_scalar"] == 7
    assert document["custom_unknown_table"]["note"] == "别的程序写的键"
    assert document["chat"]["my_custom_knob"] == "用户自定义"

    # 用户手写的独立注释（文件头）活下来
    assert "用户手写的文件头注释" in text
    # 已知键的值保真（用户改过的 42 不被默认值 40 顶掉），且该键仍带字段说明注释
    assert "max_context_size = 42 #" in text

    # 该做的两件事仍然做了：版本戳更新 + 迁移留档保留
    assert document["inner"]["version"] == "8.14.19"
    records = [dict(record) for record in document["_migrations"]]
    assert [record["id"] for record in records] == ["8.10.11", "8.14.19"]
    assert document["chat"]["reply_style"]["group_chat_prompt"] == "旧群聊提示词"
    assert document["chat"]["max_context_size"] == 42


def test_upgrade_rewrite_keeps_legacy_keys_as_unknown(tmp_path: Path):
    """§七 的固有代价（如实锁定）：老版本被迁走的键在新程序眼里也是"未知键"，同样不被删。

    删它就得删 `custom_scalar` 那类用户自定义键——两者在新程序看来无法区分，
    所以"只增不删"是契约 §七 的直接推论，不是实现取舍。
    """
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_old_shape_bot(config_path)

    load_config_from_file(Config, config_path, "8.14.19")

    document = tomlkit.loads(config_path.read_text(encoding="utf-8"))
    assert document["chat"]["group_chat_prompt"] == "旧群聊提示词"
    # 但只要它还在文件里，下一次加载会把它如实报成"多余项"（不静默）
    from src.config.config_base import AttributeData

    attribute_data = AttributeData()
    Config.from_dict(attribute_data, tomlkit.loads(config_path.read_text(encoding="utf-8")).unwrap())
    assert "custom_scalar" in attribute_data.redundant_attributes


def test_first_boot_still_writes_full_commented_template(tmp_path: Path):
    """文件不存在 ⇒ 仍是完整注释模板（首启形态没被就地更新改坏）。"""
    config_path = tmp_path / BOT_CONFIG_NAME

    write_config_to_file(Config(), config_path, "8.29.0")

    text = config_path.read_text(encoding="utf-8")
    document = tomlkit.loads(text)
    assert document["inner"]["version"] == "8.29.0"
    assert "chat" in document
    # 首启模板带字段说明注释（就地更新路径不带新键注释，这里必须带）
    assert "#" in text
    assert text.index("[inner]") < text.index("[chat]")


# ════════════════════════════════════════════════════════════════════
# P1.1b · 落盘原子性
# ════════════════════════════════════════════════════════════════════


def test_write_goes_through_temp_file_then_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """落盘形态：先写 `*.tmp`，再 `os.replace` 到位（替换时临时文件已写完）。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    write_config_to_file(Config(), config_path, "8.29.0")

    calls: list[tuple[Path, Path, bool]] = []
    real_replace = os.replace

    def recording_replace(src: Any, dst: Any) -> None:
        calls.append((Path(src), Path(dst), Path(src).exists()))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", recording_replace)
    write_config_to_file(Config(), config_path, "8.29.1")

    assert len(calls) == 1
    temp_path, target_path, temp_existed = calls[0]
    assert temp_path.name == f"{BOT_CONFIG_NAME}.tmp"
    assert target_path == config_path
    assert temp_existed, "替换发生时临时文件必须已经写完"
    assert tomlkit.loads(config_path.read_text(encoding="utf-8"))["inner"]["version"] == "8.29.1"


def test_failed_write_keeps_original_file_intact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """落盘失败：原文件一个字节不改，半截临时文件不留在配置目录。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_old_shape_bot(config_path)
    original_digest = _sha256(config_path)

    def failing_dump(*args: Any, **kwargs: Any) -> None:
        raise OSError("模拟落盘失败")

    monkeypatch.setattr(tomlkit, "dump", failing_dump)

    with pytest.raises(OSError):
        load_config_from_file(Config, config_path, "8.14.19")

    assert _sha256(config_path) == original_digest, "写失败把原文件改了"
    assert not (tmp_path / f"{BOT_CONFIG_NAME}.tmp").exists(), "残留了半截临时文件"
    # 复制语义 + 先归档：写失败时旧字节仍有留档
    archives = sorted((tmp_path / "old").glob("*.toml"))
    assert len(archives) == 1
    assert _sha256(archives[0]) == original_digest
