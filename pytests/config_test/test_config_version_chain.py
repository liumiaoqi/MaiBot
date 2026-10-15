"""P1 配置迁移机制单测（判据门三对照：转换 / 保留 / 拒绝）。

契约：`.shared/decisions/phase3_config_plan.md` P1 节。
测试走**生产入口**（`load_config_from_file`），不自己拼装机制：

- ① 转换：旧结构 → 新结构，且与本迁移无关的字段**逐字段**对账（扁平路径 diff，不是"看起来一样"）
- ② 保留：带 `_migrations` 的文件可正常加载，且不重复迁移
- ③ 拒绝：不支持的版本跳跃 ⇒ 类型化异常 **且文件前后哈希一致**（原文件不动）
"""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import tomlkit

from src.config.config import Config, load_config_from_file, write_config_to_file
from src.config.config_upgrade_hooks import (
    BOT_CONFIG_UPGRADE_HOOKS,
    MIGRATIONS_KEY,
    ConfigMigrationRefusedError,
    ConfigUpgradeHook,
    ConfigVersionChainError,
    ConfigVersionParseError,
    apply_config_upgrade_hooks,
    archive_config_file,
    resolve_migrator,
)

BOT_CONFIG_NAME = "bot_config.toml"

# 8.14.19 这一级把 chat 的同级键拆进两个子段（迁移器 _split_chat_config_sections 的清单）
MOVED_TO_REPLY_TIMING = (
    "talk_value",
    "private_talk_value",
    "mentioned_bot_reply",
    "inevitable_at_reply",
    "reply_trigger_mode",
    "planner_interrupt_max_consecutive_count",
    "max_consecutive_wait_count",
    "enable_talk_value_rules",
    "talk_value_rules",
)
MOVED_TO_REPLY_STYLE = (
    "enable_reply_quote",
    "group_chat_prompt",
    "private_chat_prompts",
    "chat_prompts",
)


def _sha256_bytes(payload: bytes) -> str:
    """字节的 SHA256。"""
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    """文件字节的 SHA256 —— 拒绝用例靠它做前后对账。"""
    return _sha256_bytes(path.read_bytes())


def _write_bot_config(
    path: Path,
    version: str | None,
    body: dict[str, dict[str, Any]],
    migrations: list[dict[str, Any]] | None = None,
) -> str:
    """手写一份 bot_config.toml（版本戳可选、留档可选），返回落盘文本。"""
    document = tomlkit.document()
    if version is not None:
        inner_table = tomlkit.table()
        inner_table.add("version", version)
        document.add("inner", inner_table)
    if migrations:
        migrations_tables = tomlkit.aot()
        for record in migrations:
            record_table = tomlkit.table()
            for key, value in record.items():
                record_table.add(key, value)
            migrations_tables.append(record_table)
        document.add(MIGRATIONS_KEY, migrations_tables)
    for section_name, section_values in body.items():
        section_table = tomlkit.table()
        for key, value in section_values.items():
            section_table.add(key, value)
        document.add(section_name, section_table)

    text = tomlkit.dumps(document)
    path.write_text(text, encoding="utf-8")
    return text


def _flat_paths(node: Any, prefix: str = "") -> dict[str, Any]:
    """把嵌套 dict 摊成 {路径: 值}；列表整体当一个值（不拆元素，避免下标噪声）。"""
    if not isinstance(node, dict):
        return {prefix: node}

    flat: dict[str, Any] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        flat.update(_flat_paths(value, path))
    return flat


def _field_diff(before: Any, after: Any) -> tuple[set[str], set[str], set[str]]:
    """逐字段对账：返回 (被删路径, 新增路径, 值被改路径)。"""
    before_flat = _flat_paths(before)
    after_flat = _flat_paths(after)
    removed = {path for path in before_flat if path not in after_flat}
    added = {path for path in after_flat if path not in before_flat}
    changed = {path for path in before_flat if path in after_flat and before_flat[path] != after_flat[path]}
    return removed, added, changed


def _full_chat_section() -> dict[str, Any]:
    """8.14.19 之前的 chat 段：13 个待搬键 + 3 个与本次迁移无关的键。"""
    return {
        "talk_value": 0.4,
        "private_talk_value": 0.8,
        "mentioned_bot_reply": True,
        "inevitable_at_reply": False,
        "reply_trigger_mode": "frequency",
        "planner_interrupt_max_consecutive_count": 3,
        "max_consecutive_wait_count": 5,
        "enable_talk_value_rules": True,
        "talk_value_rules": [{"platform": "", "item_id": "", "rule_type": "group", "time": "*", "value": 0.5}],
        "enable_reply_quote": False,
        "group_chat_prompt": "旧群聊提示词",
        "private_chat_prompts": "旧私聊提示词",
        "chat_prompts": [{"platform": "qq", "item_id": "10001", "prompt": "额外提示"}],
        # 与 8.14.19 这一级无关：必须一字不变
        "max_context_size": 42,
        "enable_token_budget": True,
        "token_threshold_ratio": 0.75,
    }


def _migration_record(record_id: str, from_version: str, to_version: str, at: str = "2026-10-15T12:00:00+08:00"):
    return {"id": record_id, "from": from_version, "to": to_version, "at": at}


# ════════════════════════════════════════════════════════════════════
# ① 转换：旧结构 → 新结构，无关字段逐字段对账
# ════════════════════════════════════════════════════════════════════


def test_migration_moves_only_expected_paths():
    """机制层逐字段对账：改动路径集合 = 恰好这 13 个键的搬迁，值一个都没变。"""
    original = {
        "chat": _full_chat_section(),
        "expression": {"max_expression_learner": 7},
        "webui": {"host": ["127.0.0.1"]},
    }

    result = apply_config_upgrade_hooks(
        original,
        BOT_CONFIG_NAME,
        "8.14.18",
        "8.14.19",
    )

    removed, added, changed = _field_diff(original, result.data)
    assert changed == set(), f"无关字段被改动: {sorted(changed)}"
    assert removed == {f"chat.{key}" for key in MOVED_TO_REPLY_TIMING + MOVED_TO_REPLY_STYLE}
    assert added == {
        f"chat.reply_timing.{key}" for key in MOVED_TO_REPLY_TIMING
    } | {f"chat.reply_style.{key}" for key in MOVED_TO_REPLY_STYLE}


def test_migration_preserves_moved_values():
    """搬迁的值必须原样落到新位置（含 list/dict 元素）。"""
    original = {"chat": _full_chat_section()}

    result = apply_config_upgrade_hooks(original, BOT_CONFIG_NAME, "8.14.18", "8.14.19")

    chat = result.data["chat"]
    assert chat["reply_timing"]["talk_value"] == 0.4
    assert chat["reply_timing"]["talk_value_rules"] == [
        {"platform": "", "item_id": "", "rule_type": "group", "time": "*", "value": 0.5}
    ]
    assert chat["reply_style"]["group_chat_prompt"] == "旧群聊提示词"
    assert chat["reply_style"]["chat_prompts"] == [{"platform": "qq", "item_id": "10001", "prompt": "额外提示"}]
    # 无关字段原地不动
    assert chat["max_context_size"] == 42
    assert chat["enable_token_budget"] is True
    assert chat["token_threshold_ratio"] == 0.75


def test_load_migrates_file_records_ledger_and_keeps_history(tmp_path: Path):
    """文件层：迁移写新版 + 追加留档 + 无关字段一字不变 + 旧文件字节留档。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_bot_config(config_path, "8.14.18", {"chat": _full_chat_section()})
    # 基准取**磁盘上的原始字节**（write_text 在 Windows 会做换行翻译，别拿写入前的字符串比）
    original_bytes = config_path.read_bytes()
    original_digest = _sha256_bytes(original_bytes)

    config, updated = load_config_from_file(Config, config_path, "8.14.19")

    assert updated is True
    assert config.chat.reply_timing.talk_value == 0.4

    document = tomlkit.loads(config_path.read_text(encoding="utf-8"))
    assert document["inner"]["version"] == "8.14.19"
    records = [dict(record) for record in document[MIGRATIONS_KEY]]
    assert len(records) == 1
    assert records[0]["id"] == "8.14.19"
    assert records[0]["from"] == "8.14.18"
    assert records[0]["to"] == "8.14.19"
    assert datetime.fromisoformat(records[0]["at"]).tzinfo is not None, "留档时间戳必须带时区"

    # 无关字段一字不变（在写出的文件里逐字段核对）
    assert document["chat"]["max_context_size"] == 42
    assert document["chat"]["enable_token_budget"] is True
    assert document["chat"]["token_threshold_ratio"] == 0.75
    # 搬迁后的结构：模型里旧键已不存在；文件里它会作为"未知键"留下
    # （P1.1a §七"不改写未知字段"的固有代价——见 test_config_write_preservation.py）
    assert document["chat"]["reply_style"]["group_chat_prompt"] == "旧群聊提示词"
    assert not hasattr(config.chat, "group_chat_prompt")

    # 不碰历史：old/ 下是**原始字节**的副本，SHA256 与载入前一致；新旧哈希不同（确认真写了新版）
    archives = sorted((tmp_path / "old").glob("*.toml"))
    assert len(archives) == 1
    assert _sha256_bytes(archives[0].read_bytes()) == original_digest
    assert archives[0].read_bytes() == original_bytes
    assert _sha256(config_path) != original_digest


def test_load_walks_every_registered_level_and_appends_contiguous_records(tmp_path: Path):
    """链式逐步：8.10.0 → 8.29.0 逐级走登记过的迁移器，留档首尾相接。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_bot_config(config_path, "8.10.0", {"chat": {"max_context_size": 30}})

    _, updated = load_config_from_file(Config, config_path, "8.29.0")

    assert updated is True
    document = tomlkit.loads(config_path.read_text(encoding="utf-8"))
    assert document["inner"]["version"] == "8.29.0"

    records = [dict(record) for record in document[MIGRATIONS_KEY]]
    old_parts, new_parts = (8, 10, 0), (8, 29, 0)
    expected_targets = [
        hook.target_version
        for hook in sorted(
            BOT_CONFIG_UPGRADE_HOOKS,
            key=lambda item: tuple(int(part) for part in item.target_version.split(".")),
        )
        if old_parts < tuple(int(part) for part in hook.target_version.split(".")) <= new_parts
    ]
    assert [record["id"] for record in records] == expected_targets
    assert [record["to"] for record in records] == expected_targets
    assert records[0]["from"] == "8.10.0"
    # 首尾相接：每条的 from 等于上一条的 to
    for previous, current in zip(records, records[1:], strict=False):
        assert current["from"] == previous["to"]
    # 无关字段没被这串迁移弄丢
    assert document["chat"]["max_context_size"] == 30


# ════════════════════════════════════════════════════════════════════
# ② 保留：带 _migrations 的文件可加载且不重复迁移
# ════════════════════════════════════════════════════════════════════


def test_file_with_ledger_loads_without_rewrite(tmp_path: Path):
    """版本已是当前：带留档的文件正常加载，且**一个字节都不写**。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    ledger = [_migration_record("8.14.19", "8.14.18", "8.14.19")]
    _write_bot_config(config_path, "8.29.0", {"chat": {"max_context_size": 42}}, migrations=ledger)
    before_digest = _sha256(config_path)

    config, updated = load_config_from_file(Config, config_path, "8.29.0")

    assert updated is False, "版本相同不该触发重写"
    assert config.chat.max_context_size == 42
    assert _sha256(config_path) == before_digest
    document = tomlkit.loads(config_path.read_text(encoding="utf-8"))
    assert [dict(record) for record in document[MIGRATIONS_KEY]] == ledger


def test_second_load_does_not_migrate_again(tmp_path: Path):
    """不重复迁移：迁移后连读两次，留档不增、文件字节不变。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_bot_config(config_path, "8.14.18", {"chat": _full_chat_section()})

    _, first_updated = load_config_from_file(Config, config_path, "8.14.19")
    after_first_digest = _sha256(config_path)

    _, second_updated = load_config_from_file(Config, config_path, "8.14.19")

    assert first_updated is True
    assert second_updated is False
    assert _sha256(config_path) == after_first_digest
    document = tomlkit.loads(config_path.read_text(encoding="utf-8"))
    records = [dict(record) for record in document[MIGRATIONS_KEY]]
    assert [record["id"] for record in records] == ["8.14.19"]
    assert document["chat"]["reply_style"]["group_chat_prompt"] == "旧群聊提示词"
    assert document["chat"]["reply_timing"]["talk_value"] == 0.4


def test_walk_appends_nothing_when_no_level_in_range():
    """没有落在区间里的级 ⇒ 不追加留档（留档只在真的走过某级时增长）。"""
    ledger = [_migration_record("8.14.19", "8.14.18", "8.14.19")]

    result = apply_config_upgrade_hooks(
        {"chat": {"max_context_size": 42}},
        BOT_CONFIG_NAME,
        "8.28.2",
        "8.29.0",
        migrations=ledger,
    )

    assert result.migrated is False
    assert result.migrations == ledger


def test_rewrite_without_explicit_migrations_keeps_existing_ledger(tmp_path: Path):
    """写出路径的档②：不传留档时沿用磁盘上的那份，绝不在重写里把它抹掉。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    ledger = [_migration_record("8.10.11", "8.10.0", "8.10.11")]
    _write_bot_config(config_path, "8.29.0", {"chat": {"max_context_size": 42}}, migrations=ledger)

    write_config_to_file(Config(), config_path, "8.29.1")

    document = tomlkit.loads(config_path.read_text(encoding="utf-8"))
    assert document["inner"]["version"] == "8.29.1"
    assert [dict(record) for record in document[MIGRATIONS_KEY]] == ledger


def test_archive_never_overwrites_existing_backup(tmp_path: Path):
    """同一秒内二次落档：新副本另起名字，已有留档字节不动（留档只增不改）。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_bot_config(config_path, "8.29.0", {"chat": {"max_context_size": 42}})
    first = archive_config_file(config_path)
    assert first is not None
    first_digest = _sha256(first.backup_path)

    config_path.write_text(config_path.read_text(encoding="utf-8") + "\n# 第二次改写\n", encoding="utf-8")
    second = archive_config_file(config_path)

    assert second is not None
    assert second.backup_path != first.backup_path
    assert _sha256(first.backup_path) == first_digest, "已有留档被覆盖了"
    assert len(list((tmp_path / "old").glob("*.toml"))) == 2
    assert second.sha256 == _sha256(second.backup_path), "登记的 SHA256 必须与留档一致"


# ════════════════════════════════════════════════════════════════════
# ③ 拒绝：类型化异常 + 文件未改（前后哈希一致）
# ════════════════════════════════════════════════════════════════════


def test_refuses_broken_ledger_chain_and_leaves_file_untouched(tmp_path: Path):
    """留档断链（8.14.19 -> 8.14.19 是乱序/回退）⇒ 拒绝，且一个字节都没写。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_bot_config(
        config_path,
        "8.10.0",
        {"chat": {"max_context_size": 42}},
        migrations=[
            _migration_record("8.10.11", "8.10.0", "8.10.11"),
            _migration_record("8.14.19", "8.14.19", "8.14.19"),
        ],
    )
    before_digest = _sha256(config_path)

    with pytest.raises(ConfigVersionChainError) as excinfo:
        load_config_from_file(Config, config_path, "8.29.0")

    message = str(excinfo.value)
    assert BOT_CONFIG_NAME in message
    assert "8.10.0" in message and "8.29.0" in message
    assert _sha256(config_path) == before_digest
    assert not (tmp_path / "old").exists(), "拒绝路径不得产生留档（说明没走到写）"


def test_refuses_version_behind_its_own_ledger(tmp_path: Path):
    """版本与留档矛盾：声明版本早于留档链尾 ⇒ 拒绝，文件未改。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_bot_config(
        config_path,
        "8.10.0",
        {"chat": {"max_context_size": 42}},
        migrations=[_migration_record("8.28.1", "8.10.0", "8.28.1")],
    )
    before_digest = _sha256(config_path)

    with pytest.raises(ConfigVersionChainError):
        load_config_from_file(Config, config_path, "8.29.0")

    assert _sha256(config_path) == before_digest
    assert not (tmp_path / "old").exists()


def test_refuses_unparsable_version_and_leaves_file_untouched(tmp_path: Path):
    """版本串不可解析 ⇒ 类型化拒绝，文件未改。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_bot_config(config_path, "8.x.0", {"chat": {"max_context_size": 42}})
    before_digest = _sha256(config_path)

    with pytest.raises(ConfigVersionParseError) as excinfo:
        load_config_from_file(Config, config_path, "8.29.0")

    assert BOT_CONFIG_NAME in str(excinfo.value)
    assert _sha256(config_path) == before_digest


def test_refuses_ledger_without_version_stamp(tmp_path: Path):
    """留档在、版本戳丢了 ⇒ 矛盾状态，拒绝（不能当首启糊过去）。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_bot_config(
        config_path,
        None,
        {"chat": {"max_context_size": 42}},
        migrations=[_migration_record("8.10.11", "8.10.0", "8.10.11")],
    )
    before_digest = _sha256(config_path)

    with pytest.raises(ConfigVersionChainError):
        load_config_from_file(Config, config_path, "8.29.0")

    assert _sha256(config_path) == before_digest


def test_refuses_when_migrator_id_is_not_registered():
    """查表拒绝：未登记的 id ⇒ 类型化拒绝（不静默跳过）。

    ⚠️ 可达性如实说明：当前"迁移级"与"登记表"同源（都从 BOT_CONFIG_UPGRADE_HOOKS 派生），
    正常数据走不到这一支 ⇒ 走路里的查表是**防御性守卫**。它的行为由两条测试锁住：
    本测试（公共查表接口）+ `test_walk_refuses_when_registry_lacks_selected_level`（注入漂移走全链）。
    """
    with pytest.raises(ConfigMigrationRefusedError) as excinfo:
        resolve_migrator(BOT_CONFIG_NAME, "9.9.9", old_version="8.10.0", new_version="9.9.9")

    message = str(excinfo.value)
    assert "9.9.9" in message and BOT_CONFIG_NAME in message


def test_walk_refuses_when_registry_lacks_selected_level(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """登记表漂移（**注入式**）：走路选中 8.14.19，登记表里却查不到 ⇒ 拒绝且原文件不动。

    ⚠️ 边界如实标注：这条路径**不会被自然数据触发**（级与登记表同源），本测试靠替换登记表
    构造器注入漂移来锁住"拒绝而不是静默跳过"的行为。自然可达的漂移形态是"同一级重复登记"
    （见 `test_refuses_duplicated_level_registration`）——两条一起才算把登记面盖全。
    """

    def drifted_registry(config_name: str, *, old_version: str, new_version: str) -> dict[str, Any]:
        return {
            hook.target_version: hook.migrate
            for hook in BOT_CONFIG_UPGRADE_HOOKS
            if config_name in hook.config_names and hook.target_version != "8.14.19"
        }

    monkeypatch.setattr("src.config.config_upgrade_hooks.build_migrator_registry", drifted_registry)
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_bot_config(config_path, "8.14.18", {"chat": _full_chat_section()})
    before_digest = _sha256(config_path)

    with pytest.raises(ConfigMigrationRefusedError) as excinfo:
        load_config_from_file(Config, config_path, "8.14.19")

    message = str(excinfo.value)
    assert "未登记" in message and "8.14.19" in message
    assert _sha256(config_path) == before_digest, "拒绝路径不得改写原文件"
    assert not (tmp_path / "old").exists()


def test_refuses_duplicated_level_registration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """同一级被登记两次（登记表漂移）⇒ 拒绝，且原文件不动。"""
    duplicated = BOT_CONFIG_UPGRADE_HOOKS + (
        ConfigUpgradeHook(
            target_version="8.14.19",
            config_names=(BOT_CONFIG_NAME,),
            migrate=lambda data: [],
        ),
    )
    monkeypatch.setattr("src.config.config_upgrade_hooks.BOT_CONFIG_UPGRADE_HOOKS", duplicated)
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_bot_config(config_path, "8.14.18", {"chat": _full_chat_section()})
    before_digest = _sha256(config_path)

    with pytest.raises(ConfigMigrationRefusedError):
        load_config_from_file(Config, config_path, "8.14.19")

    assert _sha256(config_path) == before_digest
    assert not (tmp_path / "old").exists()


# ════════════════════════════════════════════════════════════════════
# 首启 与 镜像回滚（两条不该拒绝的路）
# ════════════════════════════════════════════════════════════════════


def test_missing_version_stamp_is_first_boot(tmp_path: Path):
    """缺版本戳 ⇒ 视为首启：不迁移、不拒绝，也不改动文件。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_bot_config(config_path, None, {"chat": {"max_context_size": 42}})
    before_digest = _sha256(config_path)

    config, updated = load_config_from_file(Config, config_path, "8.29.0")

    assert updated is False
    assert config.chat.max_context_size == 42
    assert _sha256(config_path) == before_digest


def test_newer_config_file_is_not_refused(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    """文件版本高于程序版本（镜像回滚）⇒ 不迁移、不写、不拒绝，但警告必须报清"落后多少、哪份文件"。"""
    config_path = tmp_path / BOT_CONFIG_NAME
    _write_bot_config(config_path, "9.0.0", {"chat": {"max_context_size": 42}})
    before_digest = _sha256(config_path)

    with caplog.at_level("WARNING"):
        config, updated = load_config_from_file(Config, config_path, "8.29.0")

    assert updated is False
    assert config.chat.max_context_size == 42
    assert _sha256(config_path) == before_digest

    rollback_warnings = [record.getMessage() for record in caplog.records if "高于当前程序版本" in record.getMessage()]
    assert len(rollback_warnings) == 1, f"回滚警告只该有一条: {rollback_warnings}"
    # 本仓日志管道把事件包成 JSON 字符串（Windows 路径的反斜杠会被转义）⇒ 先还原再比
    warning = rollback_warnings[0].replace("\\\\", "\\")
    assert "9.0.0" in warning and "8.29.0" in warning, "警告必须写明两个版本号"
    assert config_path.name in warning, "警告必须写明是哪一份文件"
    assert str(config_path) in warning, "警告必须写明是哪一份文件（完整路径）"
