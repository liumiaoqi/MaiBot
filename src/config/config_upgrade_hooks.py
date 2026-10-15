"""配置迁移机制：版本链前置校验 · 链式逐步迁移 · 迁移留档 · 不支持就拒绝。

契约：`.shared/decisions/phase3_config_plan.md` P1 节（D2：留档载体 = 配置文件内的 `_migrations`）。
设计参照 dsh 的数据迁移制度（研究材料 `C:\\hub\\.scratch\\maibot-phase3-config-research.md` §四·补）：
相邻版本一条迁移边、任何历史版本沿链升到当前；迁移永不移动/覆盖已提交的一代；
不支持的迁移**显式拒绝**（档③：在**任何写入之前**拒绝，原文件字节保持不动）。
"""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from shutil import copy2
from typing import Any, Callable, Mapping, Sequence

import tomlkit

from src.common.i18n import t
from src.common.logger import get_logger

from .official_configs import ChatConfig

logger = get_logger("config.config_upgrade_hooks")

MIGRATIONS_KEY = "_migrations"
"""迁移留档在配置文件里的顶层键名（与 [inner] 并列，紧跟版本戳——两者同生共死）。"""

MIGRATIONS_COMMENT = "以下为配置迁移留档，由程序自动维护，请勿手工修改"

ConfigUpgradeHookCallable = Callable[[dict[str, Any]], list[str]]


@dataclass(frozen=True)
class ConfigUpgradeHook:
    """配置升级钩子，在跨过指定版本时执行一次。"""

    target_version: str
    config_names: tuple[str, ...]
    migrate: ConfigUpgradeHookCallable


@dataclass
class ConfigUpgradeHookResult:
    data: dict[str, Any]
    migrated: bool
    reason: str = ""
    migrations: list[dict[str, Any]] = field(default_factory=list)
    """写回配置文件的完整留档 = 历史条目（原样）+ 本次逐级新增的条目。"""


class ConfigVersionChainError(Exception):
    """配置版本链错误：档③「前置拒绝」——必须在任何写入之前抛出，原文件保持不动。

    消息里始终带**文件（调用方给完整路径，仓根 config/ 与 docker-config/mmc/ 两份真源靠它分辨）
    + 旧版本 + 新版本**（现场三要素，事后不用再猜是哪份文件哪个版本）。
    """

    def __init__(self, reason: str, *, file_name: str, old_version: str, new_version: str) -> None:
        self.reason: str = reason
        self.file_name: str = file_name
        self.old_version: str = old_version
        self.new_version: str = new_version
        super().__init__(f"配置文件 {file_name} 拒绝迁移（{old_version} -> {new_version}）：{reason}")


class ConfigVersionParseError(ConfigVersionChainError):
    """版本串不可解析：版本戳坏了，没法参与版本链比较。"""


class ConfigMigrationRefusedError(ConfigVersionChainError):
    """迁移被显式拒绝：迁移器 id 未登记 / 同一级重复登记 / 前置条件不满足。

    拒绝的含义是"我读不懂这份文件的来历"——此时**不猜、不跳过、不半写**。
    """


@dataclass(frozen=True)
class MigrationRecord:
    """一条迁移留档，写入配置文件的 `_migrations`（D2 固定形状 `{id, from, to, at}`）。"""

    id: str
    from_version: str
    to_version: str
    at: str

    def to_dict(self) -> dict[str, str]:
        """转成落盘形状（键名 `from` 是契约规定的，Python 侧只能叫 from_version）。"""
        return {"id": self.id, "from": self.from_version, "to": self.to_version, "at": self.at}


@dataclass(frozen=True)
class VersionChainPlan:
    """版本链前置校验的结论（进 `from_dict` 之前的现场快照）。"""

    old_version: str
    """本轮迁移的起点版本；首启时等于当前版本（没有可迁移的东西）。"""
    upgrade_needed: bool
    """是否需要升级：文件版本 < 当前版本。"""
    first_boot: bool
    """配置文件没有版本戳 ⇒ 视为首启。"""
    records: tuple[dict[str, Any], ...]
    """磁盘上已有的留档条目（原样保留，不解析、不改写）。"""


@dataclass(frozen=True)
class ConfigArchive:
    """旧配置的留档（`old/` 下的字节级副本 + 校验和）。"""

    source_path: Path
    backup_path: Path
    sha256: str
    size_bytes: int


def _parse_version(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _version_in_upgrade_range(old_ver: str, target_ver: str, new_ver: str) -> bool:
    old_parts = _parse_version(old_ver)
    target_parts = _parse_version(target_ver)
    new_parts = _parse_version(new_ver)
    return old_parts < target_parts <= new_parts


# ───────────────────────── 版本链前置校验（档③：任何写之前） ─────────────────────────


def split_version(version: str) -> tuple[int, ...] | None:
    """把 "8.10.11" 拆成 (8, 10, 11)；不可解析返回 None（怎么报错由调用方决定）。"""
    parts = version.split(".")
    if any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def parse_config_version(version: str, *, file_name: str, old_version: str, new_version: str) -> tuple[int, ...]:
    """解析版本串；坏了直接抛 ConfigVersionParseError（不返哨兵值，免得调用方忘了判空）。"""
    parts = split_version(version)
    if parts is None:
        raise ConfigVersionParseError(
            f"版本串不可解析: {version!r}",
            file_name=file_name,
            old_version=old_version,
            new_version=new_version,
        )
    return parts


def parse_migration_records(raw: Any, *, file_name: str, old_version: str, new_version: str) -> list[dict[str, Any]]:
    """校验并取出已有留档条目，**原样保留**（含未知键——历史条目只增不改）。

    留档是"这份配置怎么变成现在这样的"唯一现场：读不懂就不该接着改它 ⇒ 形状非法即拒绝。
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigVersionChainError(
            f"{MIGRATIONS_KEY} 形状非法（期望数组，实际 {type(raw).__name__}）",
            file_name=file_name,
            old_version=old_version,
            new_version=new_version,
        )

    records: list[dict[str, Any]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, Mapping):
            raise ConfigVersionChainError(
                f"{MIGRATIONS_KEY}[{index}] 不是表（实际 {type(entry).__name__}）",
                file_name=file_name,
                old_version=old_version,
                new_version=new_version,
            )
        for key in ("id", "from", "to", "at"):
            if not isinstance(entry.get(key), str):
                raise ConfigVersionChainError(
                    f"{MIGRATIONS_KEY}[{index}].{key} 缺失或不是字符串",
                    file_name=file_name,
                    old_version=old_version,
                    new_version=new_version,
                )
        records.append(dict(entry))
    return records


def validate_version_chain(
    file_name: str, old_version: str, new_version: str, records: Sequence[Mapping[str, Any]]
) -> None:
    """版本链前置校验：进 `from_dict` 之前跑，且只在**确实需要升级**时跑。

    拒绝的三种情形（都在任何写入之前）：
      ① 版本串不可解析；
      ② 留档链乱序/回退/断链 —— 每条必须 `from < to`，且与前一条首尾相接；
      ③ 文件声明的版本落在自己留档的链尾之前 —— "版本说没迁过、留档说迁过了"。
         两者矛盾时不能猜：猜错就是在一个自己都没弄清的结构上再迁一次。

    文件版本高于当前（容器回滚到旧镜像）**不在这里拒绝**：那种情况不需要迁移、也不需要写，
    只读不写就没有损坏面（dsh 档②：忽略但保留，不承诺降级安全）。
    """
    old_parts = parse_config_version(old_version, file_name=file_name, old_version=old_version, new_version=new_version)
    parse_config_version(new_version, file_name=file_name, old_version=old_version, new_version=new_version)

    previous_to: tuple[int, ...] | None = None
    previous_raw_to: str = ""
    for index, record in enumerate(records):
        raw_from = record.get("from")
        raw_to = record.get("to")
        if not isinstance(raw_from, str) or not isinstance(raw_to, str):
            raise ConfigVersionChainError(
                f"{MIGRATIONS_KEY}[{index}] 缺少 from/to 版本串",
                file_name=file_name,
                old_version=old_version,
                new_version=new_version,
            )
        from_parts = parse_config_version(
            raw_from, file_name=file_name, old_version=old_version, new_version=new_version
        )
        to_parts = parse_config_version(raw_to, file_name=file_name, old_version=old_version, new_version=new_version)
        if from_parts >= to_parts:
            raise ConfigVersionChainError(
                f"{MIGRATIONS_KEY}[{index}] 乱序或回退: {raw_from} -> {raw_to}",
                file_name=file_name,
                old_version=old_version,
                new_version=new_version,
            )
        if previous_to is not None and from_parts != previous_to:
            raise ConfigVersionChainError(
                f"{MIGRATIONS_KEY}[{index}] 与前一条断链: {raw_from} 接不上 {previous_raw_to}",
                file_name=file_name,
                old_version=old_version,
                new_version=new_version,
            )
        previous_to = to_parts
        previous_raw_to = raw_to

    if previous_to is not None and old_parts < previous_to:
        raise ConfigVersionChainError(
            f"声明版本 {old_version} 早于留档链尾 {previous_raw_to} —— 版本与留档矛盾",
            file_name=file_name,
            old_version=old_version,
            new_version=new_version,
        )


def plan_version_chain(file_name: str, raw_version: Any, new_version: str, raw_migrations: Any) -> VersionChainPlan:
    """版本链前置校验的总入口（在 `from_dict` 之前调用，在**任何写入之前**出结论）。

    - 版本戳缺失/空 ⇒ **首启**：本轮没有可迁移的东西，不迁移也不拒绝（只留痕）；
      但若同时存在留档条目，则说明这不是首启而是版本戳丢了 ⇒ 拒绝（版本与留档矛盾）。
    - 版本戳在但不可解析（含类型不对）⇒ 拒绝。
    - 需要迁移（文件版本 < 当前版本）⇒ 校验留档链，乱序/回退/断链即拒绝。
    - 文件版本 ≥ 当前版本（镜像回滚）⇒ 不迁移、不校验、不写，只告警。
    """
    if raw_version is None or (isinstance(raw_version, str) and not raw_version.strip()):
        if raw_migrations:
            raise ConfigVersionChainError(
                "缺少版本戳但存在迁移留档 —— 版本与留档矛盾",
                file_name=file_name,
                old_version="(缺失)",
                new_version=new_version,
            )
        logger.warning(f"{t('config.missing_inner_version')}，按首次启动处理（本次不迁移）: {file_name}")
        return VersionChainPlan(old_version=new_version, upgrade_needed=False, first_boot=True, records=())

    if not isinstance(raw_version, str):
        raise ConfigVersionParseError(
            f"{t('config.invalid_inner_version')}（实际 {type(raw_version).__name__}）",
            file_name=file_name,
            old_version=str(raw_version),
            new_version=new_version,
        )

    old_version = raw_version
    old_parts = parse_config_version(old_version, file_name=file_name, old_version=old_version, new_version=new_version)
    new_parts = parse_config_version(new_version, file_name=file_name, old_version=old_version, new_version=new_version)

    if new_parts <= old_parts:
        if new_parts < old_parts:
            # 文件比程序新：容器回滚到旧镜像时会看到，属预期；不迁移、不写、不拒绝
            logger.warning(f"配置版本 {old_version} 高于当前程序版本 {new_version}，本次不迁移（镜像回滚时属预期）: {file_name}")
        return VersionChainPlan(old_version=old_version, upgrade_needed=False, first_boot=False, records=())

    records = parse_migration_records(
        raw_migrations, file_name=file_name, old_version=old_version, new_version=new_version
    )
    validate_version_chain(file_name, old_version, new_version, records)
    return VersionChainPlan(
        old_version=old_version, upgrade_needed=True, first_boot=False, records=tuple(records)
    )


# ───────────────────────────── 迁移器登记表（逐级走路用） ─────────────────────────────


def build_migrator_registry(
    config_name: str, *, old_version: str, new_version: str
) -> dict[str, ConfigUpgradeHookCallable]:
    """构建该配置文件的迁移器登记表：迁移级 id → 迁移器。

    迁移级 id = 该级的版本边界（`target_version`）。同一级重复登记即拒绝：
    两个迁移器争一个版本边界时"该跑哪个"没有正确答案，静默取一个就是静默跳过另一个。
    """
    registry: dict[str, ConfigUpgradeHookCallable] = {}
    for hook in BOT_CONFIG_UPGRADE_HOOKS + MODEL_CONFIG_UPGRADE_HOOKS:
        if config_name not in hook.config_names:
            continue
        if hook.target_version in registry:
            raise ConfigMigrationRefusedError(
                f"迁移器 id {hook.target_version} 重复登记（同一级只能有一个迁移器）",
                file_name=config_name,
                old_version=old_version,
                new_version=new_version,
            )
        registry[hook.target_version] = hook.migrate
    return registry


def resolve_migrator(
    config_name: str, migration_id: str, *, old_version: str, new_version: str
) -> ConfigUpgradeHookCallable:
    """按 id 取回登记过的迁移器；未登记即拒绝（不静默跳过、不装作没这一级）。

    ⚠️ **可达性如实说明**：当前"迁移级"与"登记表"同源（都由 BOT/MODEL_CONFIG_UPGRADE_HOOKS 派生），
    所以正常数据**走不出**"未登记"这一支——它是**防御性守卫**，靠替换登记表构造漂移才能触发
    （测试见 `pytests/config_test/test_config_version_chain.py`）；自然可达的登记漂移形态是
    "同一级重复登记"（见 `build_migrator_registry`），那条有独立测试。
    """
    migrator = build_migrator_registry(config_name, old_version=old_version, new_version=new_version).get(migration_id)
    if migrator is None:
        raise ConfigMigrationRefusedError(
            f"迁移器 id {migration_id} 未登记",
            file_name=config_name,
            old_version=old_version,
            new_version=new_version,
        )
    return migrator


def _levels_in_upgrade_range(config_name: str, old_ver: str, new_ver: str) -> list[ConfigUpgradeHook]:
    """该文件在 `(old, new]` 区间里登记过的迁移级，按版本升序 —— 链式迁移的行走顺序。"""
    levels = [
        hook
        for hook in BOT_CONFIG_UPGRADE_HOOKS + MODEL_CONFIG_UPGRADE_HOOKS
        if config_name in hook.config_names and _version_in_upgrade_range(old_ver, hook.target_version, new_ver)
    ]
    levels.sort(key=lambda hook: _parse_version(hook.target_version))
    return levels


# ───────────────────────────── 不碰历史：旧配置留档 ─────────────────────────────


def archive_config_file(config_path: Path) -> ConfigArchive | None:
    """把即将被改写的旧配置复制进 `old/`（`旧名_时间戳.toml`），并记录 SHA256。

    - **复制而不是移动**：写新版本失败时原文件还在原地（dsh 制度"迁移永不移动、覆盖或删除
      已提交的一代"——旧的 `replace` 一旦后面写失败，配置就只剩 old/ 里那一份了）；
    - **绝不覆盖已有留档**：同一秒内二次落档就追加序号——留档只增不改。
    """
    if not config_path.exists():
        return None

    backup_root = config_path.parent / "old"
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"{config_path.stem}_{timestamp}.toml"
    sequence = 2
    while backup_path.exists():
        backup_path = backup_root / f"{config_path.stem}_{timestamp}_{sequence}.toml"
        sequence += 1

    copy2(config_path, backup_path)
    digest = sha256(backup_path.read_bytes()).hexdigest()
    archive = ConfigArchive(
        source_path=config_path,
        backup_path=backup_path,
        sha256=digest,
        size_bytes=backup_path.stat().st_size,
    )
    logger.info(
        f"配置升级留档: {config_path.name} -> {archive.backup_path.name}"
        f"（sha256={digest}, {archive.size_bytes} 字节）"
    )
    return archive


def read_migrations_from_file(config_path: Path) -> list[dict[str, Any]]:
    """读出配置文件里已有的 `_migrations`，原样返回（不解析语义、不改写）。

    用途：重写配置时**保留**留档（dsh 档②"忽略但保留"）——写路径不认识它，也不能把它抹掉。
    文件读不了时按"无留档"处理并双通道上报，**不阻断写入**（留档是审计物，不是运行前提）。
    """
    if not config_path.exists():
        return []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            document = tomlkit.load(f)
        raw = document.get(MIGRATIONS_KEY)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port

        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "读取配置迁移留档失败，按无留档处理", exception=exc)
        logger.warning(f"读取配置迁移留档失败，按无留档处理: {config_path.name}: {exc}")
        return []

    if raw is None:
        return []
    if not isinstance(raw, list):
        logger.warning(f"{MIGRATIONS_KEY} 形状非法（实际 {type(raw).__name__}），本次重写不保留留档: {config_path.name}")
        return []
    return [dict(entry) for entry in raw if isinstance(entry, Mapping)]


def set_nested_config_value(data: dict[str, Any], path: tuple[str, ...], value: Any, force: bool = True) -> bool:
    """设置嵌套配置值，返回是否实际发生变化。"""

    if not path:
        return False

    current: dict[str, Any] = data
    for key in path[:-1]:
        next_value = current.get(key)
        if not isinstance(next_value, dict):
            next_value = {}
            current[key] = next_value
        current = next_value

    leaf_key = path[-1]
    if not force and leaf_key in current:
        return False
    if current.get(leaf_key) == value:
        return False

    current[leaf_key] = value
    return True


def _reset_group_chat_prompt_to_default(data: dict[str, Any]) -> list[str]:
    default_group_chat_prompt = ChatConfig().reply_style.group_chat_prompt
    changed = set_nested_config_value(data, ("chat", "reply_style", "group_chat_prompt"), default_group_chat_prompt)
    return ["chat.reply_style.group_chat_prompt"] if changed else []


def _as_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _as_list(value: Any) -> list[Any] | None:
    return value if isinstance(value, list) else None


def _parse_triplet_target(value: str) -> dict[str, str] | None:
    parts = value.split(":", 2)
    if len(parts) != 3:
        return None

    platform, item_id, rule_type = parts
    if rule_type not in ("group", "private"):
        return None
    return {"platform": platform, "item_id": item_id, "rule_type": rule_type}


def _parse_jargon_group_target(value: str) -> dict[str, str] | None:
    normalized_value = value.strip()
    if normalized_value == "*":
        return {"platform": "*", "item_id": "*", "rule_type": "group"}
    return _parse_triplet_target(normalized_value)


def _migrate_jargon_groups(jargon: dict[str, Any]) -> bool:
    raw_jargon_groups = jargon.get("jargon_groups")
    if isinstance(raw_jargon_groups, str):
        normalized_value = raw_jargon_groups.strip()
        if not normalized_value:
            jargon["jargon_groups"] = []
            return True

        parsed = _parse_jargon_group_target(normalized_value)
        if parsed is None:
            logger.warning(f"_migrate_jargon_groups 解析失败 return False: value={normalized_value!r}")
            return False

        jargon["jargon_groups"] = [{"jargon_groups": [parsed]}]
        return True

    jargon_groups = _as_list(raw_jargon_groups)
    if jargon_groups is None:
        logger.warning(f"_migrate_jargon_groups jargon_groups 非 list return False: raw={raw_jargon_groups!r}")
        return False
    if jargon_groups and all(isinstance(item, dict) for item in jargon_groups):
        return False

    migrated_groups: list[dict[str, Any]] = []
    for group in jargon_groups:
        group_items = _as_list(group)
        if group_items is None:
            logger.warning(f"_migrate_jargon_groups group 非 list return False: group={group!r}")
            return False

        targets: list[dict[str, str]] = []
        for item in group_items:
            parsed = _parse_jargon_group_target(str(item))
            if parsed is None:
                logger.warning(f"_migrate_jargon_groups item 解析失败 return False: item={item!r}")
                return False
            targets.append(parsed)

        migrated_groups.append({"jargon_groups": targets})

    jargon["jargon_groups"] = migrated_groups
    return True


def _split_jargon_config_from_expression(data: dict[str, Any]) -> list[str]:
    """
    8.10.18: 将黑话学习配置从 expression 拆到独立的 jargon 配置段。
    """
    expr = _as_dict(data.get("expression"))
    if expr is None:
        return []

    jargon = _as_dict(data.get("jargon"))
    if jargon is None:
        jargon = {}
        data["jargon"] = jargon

    reasons: list[str] = []
    if "learning_list" not in jargon:
        learning_list = _as_list(expr.get("learning_list")) or []
        jargon_learning_list: list[dict[str, Any]] = []
        for item in learning_list:
            item_dict = _as_dict(item)
            if item_dict is None or "enable_jargon_learning" not in item_dict:
                continue
            jargon_learning_list.append(
                {
                    "platform": item_dict.get("platform", ""),
                    "item_id": item_dict.get("item_id", ""),
                    "rule_type": item_dict.get("type", item_dict.get("rule_type", "group")),
                    "enable_learning": bool(item_dict.get("enable_jargon_learning")),
                }
            )

        if jargon_learning_list:
            jargon["learning_list"] = jargon_learning_list
            reasons.append("jargon.learning_list")

    learning_list = _as_list(expr.get("learning_list")) or []
    removed_jargon_flag = False
    for item in learning_list:
        item_dict = _as_dict(item)
        if item_dict is not None and "enable_jargon_learning" in item_dict:
            item_dict.pop("enable_jargon_learning", None)
            removed_jargon_flag = True
    if removed_jargon_flag:
        reasons.append("expression.learning_list.enable_jargon_learning")

    if expr.get("all_global_jargon") is True and "jargon_groups" not in jargon:
        jargon["jargon_groups"] = [{"jargon_groups": [{"platform": "*", "item_id": "*", "rule_type": "group"}]}]
        reasons.append("jargon.jargon_groups")

    if "all_global_jargon" in expr:
        expr.pop("all_global_jargon", None)
        reasons.append("expression.all_global_jargon")

    if _migrate_jargon_groups(jargon):
        reasons.append("jargon.jargon_groups")

    return reasons


def _normalize_learning_item_fields(data: dict[str, Any]) -> list[str]:
    """
    8.10.19: 统一 expression/jargon learning_list 字段为 platform/item_id/type/use/learn。
    """
    reasons: list[str] = []

    expression = _as_dict(data.get("expression"))
    if expression is not None and _normalize_learning_list_fields(
        expression,
        use_source_keys=("use_expression", "use"),
        learn_source_keys=("enable_learning", "learn"),
        default_use=True,
        default_learn=True,
    ):
        reasons.append("expression.learning_list")

    jargon = _as_dict(data.get("jargon"))
    if jargon is not None and _normalize_learning_list_fields(
        jargon,
        use_source_keys=("use",),
        learn_source_keys=("enable_learning", "learn"),
        default_use=True,
        default_learn=True,
    ):
        reasons.append("jargon.learning_list")

    return reasons


def _normalize_group_item_fields(data: dict[str, Any]) -> list[str]:
    """
    8.10.20: 统一 expression/jargon 共享组组内字段为 targets。
    """
    reasons: list[str] = []

    expression = _as_dict(data.get("expression"))
    if expression is not None and _normalize_group_list_fields(expression, "expression_groups", "expression_groups"):
        reasons.append("expression.expression_groups")

    jargon = _as_dict(data.get("jargon"))
    if jargon is not None and _normalize_group_list_fields(jargon, "jargon_groups", "jargon_groups"):
        reasons.append("jargon.jargon_groups")

    return reasons


def _upgrade_expression_learning_defaults(data: dict[str, Any]) -> list[str]:
    """
    8.12.1: 表达学习并发默认值调整为 3，并补齐默认开启的学习优化开关。
    """
    expression = _as_dict(data.get("expression"))
    if expression is None:
        expression = {}
        data["expression"] = expression

    reasons: list[str] = []
    if expression.get("max_expression_learner") in (None, 2):
        expression["max_expression_learner"] = 3
        reasons.append("expression.max_expression_learner")
    if "expression_self_reflect" not in expression:
        expression["expression_self_reflect"] = True
        reasons.append("expression.expression_self_reflect")

    return reasons


def _normalize_webui_host_to_list(data: dict[str, Any]) -> list[str]:
    """
    8.14.13: 将 WebUI host 从 str 转换为 list[str]。
    旧配置中 host 为单地址字符串（如 "127.0.0.1"），新配置为列表。
    """
    webui = _as_dict(data.get("webui"))
    if webui is None:
        return []

    host = webui.get("host")
    if isinstance(host, list):
        return []
    if isinstance(host, str):
        webui["host"] = [host]
        return ["webui.host"]

    return []


def _move_chat_config_key(chat: dict[str, Any], section_name: str, key: str) -> bool:
    if key not in chat:
        return False

    section = _as_dict(chat.get(section_name))
    if section is None:
        section = {}
        chat[section_name] = section

    if key not in section:
        section[key] = chat[key]
    chat.pop(key, None)
    return True


def _split_chat_config_sections(data: dict[str, Any]) -> list[str]:
    """
    8.14.19: 将 chat 中的回复时机/频率与回复方式拆到独立子配置段。
    """

    chat = _as_dict(data.get("chat"))
    if chat is None:
        return []

    moved_paths: list[str] = []
    timing_keys = (
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
    style_keys = (
        "enable_reply_quote",
        "group_chat_prompt",
        "private_chat_prompts",
        "chat_prompts",
    )

    for key in timing_keys:
        if _move_chat_config_key(chat, "reply_timing", key):
            moved_paths.append(f"chat.reply_timing.{key}")
    for key in style_keys:
        if _move_chat_config_key(chat, "reply_style", key):
            moved_paths.append(f"chat.reply_style.{key}")

    return moved_paths


def _normalize_group_list_fields(section: dict[str, Any], list_key: str, old_inner_key: str) -> bool:
    group_list = _as_list(section.get(list_key))
    if group_list is None:
        return False

    migrated = False
    for group in group_list:
        group_dict = _as_dict(group)
        if group_dict is None:
            continue

        if "targets" not in group_dict and old_inner_key in group_dict:
            group_dict["targets"] = group_dict.get(old_inner_key)
            migrated = True

        if old_inner_key in group_dict:
            group_dict.pop(old_inner_key, None)
            migrated = True

    return migrated


def _normalize_learning_list_fields(
    section: dict[str, Any],
    *,
    use_source_keys: tuple[str, ...],
    learn_source_keys: tuple[str, ...],
    default_use: bool,
    default_learn: bool,
) -> bool:
    learning_list = _as_list(section.get("learning_list"))
    if learning_list is None:
        return False

    migrated = False
    for item in learning_list:
        item_dict = _as_dict(item)
        if item_dict is None:
            continue

        normalized_type = item_dict.get("type", item_dict.get("rule_type", "group"))
        normalized_use = _first_existing_bool(item_dict, use_source_keys, default_use)
        normalized_learn = _first_existing_bool(item_dict, learn_source_keys, default_learn)

        for key in ("rule_type", "use_expression", "enable_learning"):
            if key in item_dict:
                item_dict.pop(key, None)
                migrated = True

        if item_dict.get("type") != normalized_type:
            item_dict["type"] = normalized_type
            migrated = True
        if item_dict.get("use") != normalized_use:
            item_dict["use"] = normalized_use
            migrated = True
        if item_dict.get("learn") != normalized_learn:
            item_dict["learn"] = normalized_learn
            migrated = True

    return migrated


def _first_existing_bool(item: dict[str, Any], keys: tuple[str, ...], default: bool) -> bool:
    for key in keys:
        if key in item:
            return bool(item.get(key))
    return default


def _add_agent_section_config(data: dict[str, Any]) -> list[str]:
    """8.15.0: 添加智能体配置段（agent section）。"""
    if "agent" in data:
        return []
    changed = set_nested_config_value(
        data,
        ("agent", "default_agent_id"),
        "silver_wolf",
        force=False,
    )
    changed |= set_nested_config_value(
        data,
        ("agent", "agents_dir"),
        "agents",
        force=False,
    )
    return ["agent"] if changed else []


def _add_token_budget_config(data: dict[str, Any]) -> list[str]:
    """8.28.1: 添加 token 预算配置项（ZG16-2）。"""
    changed = set_nested_config_value(
        data,
        ("chat", "enable_token_budget"),
        False,
        force=False,
    )
    changed |= set_nested_config_value(
        data,
        ("chat", "token_threshold_ratio"),
        0.8,
        force=False,
    )
    changed |= set_nested_config_value(
        data,
        ("chat", "token_retain_ratio"),
        0.16,
        force=False,
    )
    return ["chat.token_budget"] if changed else []


BOT_CONFIG_UPGRADE_HOOKS: tuple[ConfigUpgradeHook, ...] = (
    ConfigUpgradeHook(
        target_version="8.10.11",
        config_names=("bot_config.toml",),
        migrate=_reset_group_chat_prompt_to_default,
    ),
    ConfigUpgradeHook(
        target_version="8.10.18",
        config_names=("bot_config.toml",),
        migrate=_split_jargon_config_from_expression,
    ),
    ConfigUpgradeHook(
        target_version="8.10.19",
        config_names=("bot_config.toml",),
        migrate=_normalize_learning_item_fields,
    ),
    ConfigUpgradeHook(
        target_version="8.10.20",
        config_names=("bot_config.toml",),
        migrate=_normalize_group_item_fields,
    ),
    ConfigUpgradeHook(
        target_version="8.12.1",
        config_names=("bot_config.toml",),
        migrate=_upgrade_expression_learning_defaults,
    ),
    ConfigUpgradeHook(
        target_version="8.14.13",
        config_names=("bot_config.toml",),
        migrate=_normalize_webui_host_to_list,
    ),
    ConfigUpgradeHook(
        target_version="8.14.19",
        config_names=("bot_config.toml",),
        migrate=_split_chat_config_sections,
    ),
    ConfigUpgradeHook(
        target_version="8.15.0",
        config_names=("bot_config.toml",),
        migrate=_add_agent_section_config,
    ),
    ConfigUpgradeHook(
        target_version="8.28.1",
        config_names=("bot_config.toml",),
        migrate=_add_token_budget_config,
    ),
)
MODEL_CONFIG_UPGRADE_HOOKS: tuple[ConfigUpgradeHook, ...] = ()


def apply_config_upgrade_hooks(
    data: dict[str, Any],
    config_name: str,
    old_ver: str,
    new_ver: str,
    *,
    migrations: Sequence[Mapping[str, Any]] = (),
    file_name: str = "",
) -> ConfigUpgradeHookResult:
    """链式逐步迁移：`old_ver -> new_ver` 逐级走**登记过的**迁移器。

    - **逐级串行**：每级成功（迁移器不抛异常）即追加一条留档 `{id, from, to, at}`，
      游标推进到该级的版本边界；留档**只追加**，历史条目原样搬运（不删改）。
    - **每级都留档**（含"跑完没改任何字段"的级）：留档要回答的是"这段路走过没有"，
      不只是"路上改了什么"——正是"升级为什么没成"的事后现场。
    - **事务性**：迁移在数据的深拷贝上进行；任何一级抛异常 ⇒ 异常抛给调用方，
      `data` 与磁盘都不留半迁移状态。
    - 需要迁移时请先过 `plan_version_chain`（版本链前置校验）；这里不再重复校验留档链，
      职责是"走路 + 留档"。
    """
    display_name = file_name or config_name
    parse_config_version(old_ver, file_name=display_name, old_version=old_ver, new_version=new_ver)
    parse_config_version(new_ver, file_name=display_name, old_version=old_ver, new_version=new_ver)

    history: list[dict[str, Any]] = [dict(record) for record in migrations]
    working = deepcopy(data)
    migrated_reasons: list[str] = []
    new_records: list[dict[str, str]] = []
    cursor = old_ver

    for hook in _levels_in_upgrade_range(config_name, old_ver, new_ver):
        level_id = hook.target_version
        # 查登记表（防御性守卫）：今天"级"与"登记表"同源 ⇒ 正常数据构造不出未登记 id；
        # 留着这道闸是为了将来两条来源分叉时**拒绝**而不是静默跳过（有注入式测试锁行为）。
        migrator = resolve_migrator(config_name, level_id, old_version=old_ver, new_version=new_ver)

        hook_reasons = migrator(working)
        for reason in hook_reasons:
            migrated_reasons.append(f"{level_id}:{reason}")
        new_records.append(
            MigrationRecord(
                id=level_id,
                from_version=cursor,
                to_version=level_id,
                at=datetime.now().astimezone().isoformat(timespec="seconds"),
            ).to_dict()
        )
        cursor = level_id

    return ConfigUpgradeHookResult(
        data=working,
        migrated=bool(migrated_reasons),
        reason=",".join(migrated_reasons),
        migrations=history + new_records,
    )
