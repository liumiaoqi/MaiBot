"""配置字段生命周期：``deprecate → replace → remove``（4 段本体）。

契约：`.shared/decisions/phase3_new_config_roadmap.md` §五「4 · 迁移机制正式化」＋ 派发单
`.shared/handoff/2026-10/dsh2dsh_cfg_migration_1016.md` §②。

## 为什么要有这一层

旧行为是**静默丢弃**：`ConfigBase.from_dict` 把文件里"名字不在模型里"的键从数据里 ``pop`` 掉
（只记进 ``AttributeData.redundant_attributes``，而且只在"确实发生升级改写"时才由
``output_config_changes`` 打一行 INFO）。后果是配置里的字段被删除之后：

- 升到新版本的**当天**看起来一切正常（那行 INFO 埋在几百行日志里）；
- 用户照着**旧文档**改那个键时，程序不报错、也不生效——**改动被吃掉了**。

这一层把"字段名消失"变成一件**显式**的事：改名有据可查（``deprecate`` 出声），
删除是拒绝而不是沉默（``remove`` 报错并指明替代者）。

## 生命周期（依据 arXiv:2605.24397 的强度谱裁剪：软警告 < 硬警告 < brownout < 移除）

| 状态 | 对配置的含义 | 本模块的动作 |
|---|---|---|
| ``CURRENT`` | 字段在模型中、且没有任何"要走了"的声明 | 不检查 |
| ``DEPRECATED`` | 字段**还在**、还可能生效，但已有替代者 | 出现即 ``logger.warning``（**不报错**）——弃用期只出声 |
| ``REMOVED`` | 字段**已不在**模型中，程序不再读它 | 出现即抛 ``ConfigFieldRefusedError``：**拒绝加载**，消息带字段路径 + 替代者 |

⚠️ **只声明"确实要走了"的字段**：把还在被生产代码读的字段标成 ``DEPRECATED`` 会天天刷警告，
把噪声当制度——那比不声明更糟。每条 ``DEPRECATED`` 都要求"替代者已经就位、读者已经没了"
（本次入表的字段都在 `_DECLARATIONS` 上方标了证据）。

## 判据与边界

- **判据（谁是真源）**：模型类 —— 字段在 ``model_fields`` 里就是还在，不在就是没了。
  本模块检查的是"**文件里出现了**一个不在模型里的 **且被声明为 REMOVED**"的键；
  没声明的未知键仍走老路（记 ``redundant_attributes``、被丢弃），**本段不改变那个行为**
  （把"一切未知键都报错"是另一件事：用户自定义表、别的程序写的键都会中招，见 `load_config_from_file`
  的"忽略但保留"契约）。
- **边界①**：``dict[str, X]`` 型字段（如 ``a_memorix.connectionist.personality`` 的键是 agent_id）
  下面**不下钻**——它们的键由数据决定、不在 schema 里，本模块没有可比的真源，硬查会误报。
- **边界②**：``REMOVED`` 的拒绝发生在**任何写入之前**（与版本链拒绝同一个位置），
  ⇒ 被拒时原文件字节不动。
- **边界③**：拒绝只针对"模型里没有这条路径"的情况吗？**不是**——声明表是真源，
  即使模型里还留着同名字段（例如"字段还在但语义已废、必须清掉"），声明为 ``REMOVED`` 就仍然拒绝。
  这保证了"声明表能压过 schema 残留"，也让本模块能表达"强制清场"。

## 与 `AGENTS.md §五` 红线的关系（**必须报 lead，不许自行突破**）

`§五` 写的是"只改模板+新增版本号，**不改动 legacy_migration**，不擅自新增 ``ConfigUpgradeHook``"。
本模块：

- **不改** ``legacy_migration``（该文件在本 fork 里不存在，本模块也不引入它）；
- **不新增** ``ConfigUpgradeHook``：本模块**不迁移、不写数据**（弃用只出声；删除只拒绝），
  与"迁移器 = 把旧结构改成新结构"是两件事；
- 但它**确实改变了加载行为**（以前静默丢，现在拒绝）⇒ 与"只改模板 + 新增版本号"的字面口径
  有张力，**已在回执中报 lead 定夺**；若判为越界，删掉 `load_config_from_file` 里的那一次调用即可
  （本模块可独立存在、可单独测试）。
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.common.logger import get_logger

logger = get_logger("config.config_lifecycle")


class FieldLifecycleState(str, Enum):
    """字段的生命周期阶段（强度递增）。"""

    CURRENT = "current"
    """正常字段：没有"要走了"的声明。"""

    DEPRECATED = "deprecated"
    """弃用中：字段还在、还可能生效，但已有替代者 ⇒ 出现即出声，**不报错**。"""

    REMOVED = "removed"
    """已移除：程序不再读它 ⇒ 文件里出现即**拒绝加载**（不静默丢弃）。"""


@dataclass(frozen=True)
class FieldLifecycle:
    """一条字段级生命周期声明。

    Attributes:
        config_name: 配置文件身份的**类名**（``"Config"`` / ``"ModelConfig"``）——按类声明而不是按文件名，
            否则仓根 ``config/``（测试夹具）与 ``docker-config/mmc/``（运行真值）得写两遍。
            ⚠️ 用类名而不是类对象：``Config`` 定义在 ``config.py`` 里，而 ``config.py`` 要 import
            本模块（接线点在那里）⇒ 直接引用类对象会**成环**（实测 ``NameError``）。类名是字符串，
            且与 pydantic 的 ``model_fields``（运行时真源）在调用点天然对得上。
        path: 点分字段路径（如 ``chat.reply_timing.talk_value``），与 TOML 的节结构一一对应。
        state: 生命周期阶段。
        replacement: 替代者（字段路径，或 ``None``＝"没有替代者，直接不要了"）。
        reason: 为什么走这一步（一句话，进日志与异常消息——排障时不用回来翻代码）。
    """

    config_name: str
    path: str
    state: FieldLifecycleState
    replacement: str | None = None
    reason: str = ""


class ConfigFieldRefusedError(Exception):
    """字段级显式拒绝：文件里出现了**已移除**的字段。

    与版本链那一族（``ConfigVersionChainError`` / ``ConfigMigrationRefusedError``）同构：
    **类型化**、消息带**字段路径 + 替代者 + 文件**、且在**任何写入之前**抛出（原文件不动）。

    为什么不是"迁移掉它"：迁移器需要知道"这个旧值该映射成什么"，而字段被移除的典型场景是
    "语义没了"（不是"换了名字"）——那种情况没有正确答案，猜一个就是把用户配置改错。
    改名场景请用 ``DEPRECATED``（弃用期只出声、原值照旧生效）。
    """

    def __init__(
        self,
        *,
        file_name: str,
        path: str,
        replacement: str | None,
        reason: str = "",
    ) -> None:
        self.file_name: str = file_name
        self.path: str = path
        self.replacement: str | None = replacement
        self.reason: str = reason
        replacement_text = f"；替代者：{replacement}" if replacement else "；本字段没有替代者"
        reason_text = f"（{reason}）" if reason else ""
        super().__init__(
            f"配置文件 {file_name} 含已移除的字段 {path}{reason_text}——"
            f"程序不再读取它，继续放着只会让改动看起来生效其实被忽略{replacement_text}。"
            f"请按替代者改写（若确实不再需要，删掉这一项）"
        )


# ───────────────────────── 声明表（唯一真源·按类） ─────────────────────────
#
# ⚠️ 入表纪律：每条都要能回答"替代者是谁 / 读者还在不在"。
# 判据不是"注释里写了 DEPRECATED"——是"生产代码里已经没有读它的地方"（grep 可核）。
#
# `_DECLARATIONS` 只放**已核实**的条目；空表也是合法状态（机制先立、账慢慢对齐）。
# 下面这段注释是**已经查过但决定不入表**的候选，留着免得后人重复调研：

# · `chat.reply_timing.*`（talk_value / private_talk_value / mentioned_bot_reply / inevitable_at_reply /
#   reply_trigger_mode / max_consecutive_wait_count / enable_talk_value_rules / talk_value_rules）：
#   源码里都带 `# DEPRECATED:` 注释，**但生产代码仍在读**（`src/maisaka/runtime.py`、
#   `src/core/message_utils.py`、`src/maisaka/mode_policy.py`、`src/core/types.py`）⇒
#   替代者（vitality / 管家规则 / ThinkingOrgan MAX_CYCLES）**尚未接管**。
#   现在标弃用只会天天刷警告，把噪声当制度。⇒ **等替代者接线完成再入表**。
# · `a_memorix.connectionist.phase`（注释写"迁移阶段已完成"）：`src/A_memorix/host_service.py:610`
#   仍在读它设置迁移阶段 ⇒ 同上，不入表。
# · `a_memorix.connectionist.inner_voices`：`host_service.py:607` 在读 ⇒ 不入表。

_DECLARATIONS: tuple[FieldLifecycle, ...] = (
    # ── `a_memorix.integration.fuzzy_modify_*`：schema 还在、**读者已经没了** ──
    #
    # 证据链（三条都可 grep 复核）：
    #   ① `official_configs.py:1850` 自己写着"本类原先有一组 model_post_init 手工范围校验
    #      （fuzzy_modify_* / feedback_correction_* 共 10 条）"⇒ 这组字段的校验已被撤掉；
    #   ② `src/core/adapters/app_config_port.py:208-228` 组装 `AMemorixIntegrationSnapshot` 时
    #      **没有**拷贝 fuzzy_modify_* ⇒ 运行时的配置快照里根本没有它们；
    #   ③ 全仓 grep（src / pytests / tests，排除 `official_configs.py` 本身与 WebUI schema）
    #      对 `fuzzy_modify_enabled` 等 0 命中 ⇒ 没有任何生产读者。
    # ⇒ 文件里改这些键**改了也不生效**，正是"静默被吃掉"的形态 ⇒ 出声。
    #
    # 为什么是 deprecate 而不是 remove：字段**还在模型里**（用户配置照常加载、值照常保留），
    # 走 remove 会让今天正常的配置**加载失败**——那是行为破坏，不是"正式化"。
    # 下一步（真正的 remove）需要先删 schema 字段 + 一个版本号跃升，属另一批动作。
    FieldLifecycle(
        config_name="Config",
        path="a_memorix.integration.fuzzy_modify_enabled",
        state=FieldLifecycleState.DEPRECATED,
        replacement=None,
        reason="记忆修正（fuzzy_modify）配置组已无生产读者：运行时快照不拷贝它、全仓无读取点",
    ),
    FieldLifecycle(
        config_name="Config",
        path="a_memorix.integration.fuzzy_modify_auto_execute_enabled",
        state=FieldLifecycleState.DEPRECATED,
        replacement=None,
        reason="同上：记忆修正配置组已无生产读者",
    ),
    FieldLifecycle(
        config_name="Config",
        path="a_memorix.integration.fuzzy_modify_confirm_threshold",
        state=FieldLifecycleState.DEPRECATED,
        replacement=None,
        reason="同上：记忆修正配置组已无生产读者",
    ),
    FieldLifecycle(
        config_name="Config",
        path="a_memorix.integration.fuzzy_modify_candidate_limit",
        state=FieldLifecycleState.DEPRECATED,
        replacement=None,
        reason="同上：记忆修正配置组已无生产读者",
    ),
    FieldLifecycle(
        config_name="Config",
        path="a_memorix.integration.fuzzy_modify_max_targets",
        state=FieldLifecycleState.DEPRECATED,
        replacement=None,
        reason="同上：记忆修正配置组已无生产读者",
    ),
    FieldLifecycle(
        config_name="Config",
        path="a_memorix.integration.fuzzy_modify_allow_global_scope",
        state=FieldLifecycleState.DEPRECATED,
        replacement=None,
        reason="同上：记忆修正配置组已无生产读者",
    ),
    # 待办（下一批，**本次不入表**，理由写在这里免得后人重复调研）：
    # `a_memorix.integration.feedback_correction_*`（12 个字段）与 fuzzy_modify_* 同源同病
    # （`official_configs.py:1850` 那句把两组一起点名、快照同样不拷贝），但字段数量多、
    # 逐个复核读者要一轮完整 grep ⇒ 与 fuzzy 组**分开入表**，避免"一次报 18 行警告"这种噪声。
)


def declarations_for(config_name: type) -> tuple[FieldLifecycle, ...]:
    """取某个配置类的全部生命周期声明（顺序＝声明顺序，便于用例逐条对账）。

    Args:
        config_name: 配置类（``Config`` / ``ModelConfig``）；内部按 ``__name__`` 对表。
    """
    name = getattr(config_name, "__name__", str(config_name))
    return tuple(item for item in _DECLARATIONS if item.config_name == name)


def lifecycle_of(config_name: type, path: str) -> FieldLifecycle | None:
    """取某条路径的声明（没有声明返回 ``None``——**没声明 ≠ 正常**，只是没被检查）。"""
    for item in declarations_for(config_name):
        if item.path == path:
            return item
    return None


# ───────────────────────── 遍历：文件里出现了哪些被声明的路径 ─────────────────────────


def _walk_declared_paths(
    data: Mapping[str, Any],
    model_cls: type,
    declaration_by_path: Mapping[str, FieldLifecycle],
    *,
    prefix: str,
    file_name: str,
    hits: list[tuple[FieldLifecycle, Any]],
) -> None:
    """在**文件数据**上按 schema 结构逐层下钻，收集命中的声明路径。

    下钻规则与 `ConfigBase.from_dict` 的递归规则保持一致（``ConfigBase`` 子类字段 +
    ``list[ConfigBase]`` + ``dict[str, ConfigBase]`` 的**值**），这样"文件里的路径"
    与"schema 里的路径"是同一套坐标系。

    ``list[ConfigBase]`` 下钻时路径**不带下标**（``[[api_providers]]`` 每一项都是
    ``api_providers.<字段>``）——声明也是这么写的，两边一致即可。
    """
    for key, value in data.items():
        key_text = str(key)
        path = f"{prefix}.{key_text}" if prefix else key_text

        declaration = declaration_by_path.get(path)
        if declaration is not None:
            hits.append((declaration, value))
            # 命中的路径**不再下钻**：整棵子树已经由这条声明负责表态，
            # 再往下走只会对同一件事重复报一遍。
            continue

        field_info = model_cls.model_fields.get(key_text) if _is_schema_model(model_cls) else None
        if field_info is None:
            continue  # 未知键：不归本模块管（老路见模块 docstring 的边界说明）
        _walk_value(value, field_info.annotation, declaration_by_path, path=path, file_name=file_name, hits=hits)


def _walk_value(
    value: Any,
    annotation: Any,
    declaration_by_path: Mapping[str, FieldLifecycle],
    *,
    path: str,
    file_name: str,
    hits: list[tuple[FieldLifecycle, Any]],
) -> None:
    """按字段的**注解**决定怎么继续下钻（``list[X]`` / ``dict[str, X]`` / ``X``）。"""
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())

    if origin is list and args:
        element = args[0]
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                if isinstance(item, Mapping):
                    _walk_declared_paths(
                        item, element, declaration_by_path, prefix=path, file_name=file_name, hits=hits
                    )
        return

    if origin is dict and args:
        value_model = args[-1]
        if isinstance(value, Mapping):
            for item in value.values():
                if isinstance(item, Mapping):
                    _walk_declared_paths(
                        item, value_model, declaration_by_path, prefix=path, file_name=file_name, hits=hits
                    )
        return

    if _is_schema_model(annotation) and isinstance(value, Mapping):
        _walk_declared_paths(value, annotation, declaration_by_path, prefix=path, file_name=file_name, hits=hits)


def _is_schema_model(candidate: Any) -> bool:
    """``candidate`` 是不是一个配置模型类（而不是 Annotation / 标量类）。"""
    from .config_base import ConfigBase

    return isinstance(candidate, type) and issubclass(candidate, ConfigBase)


def _iter_removed_paths(model_cls: type, data: Mapping[str, Any], *, prefix: str = "") -> Iterable[str]:
    """列出文件里"**不在模型里**"且**也没有被声明**的键路径（诊断用，不进判据）。

    用途：把"静默丢弃"的现场逐个点名，供"要不要为它加一条 REMOVED 声明"的判断——
    这是本模块留给后人**对齐账目**的入口，不是加载路径的一部分。
    """
    if not isinstance(data, Mapping):
        return
    for key, value in data.items():
        key_text = str(key)
        path = f"{prefix}.{key_text}" if prefix else key_text
        field_info = model_cls.model_fields.get(key_text) if _is_schema_model(model_cls) else None
        if field_info is None:
            yield path
            continue
        annotation = field_info.annotation
        origin = getattr(annotation, "__origin__", None)
        args = getattr(annotation, "__args__", ())
        if origin is list and args and isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                if isinstance(item, Mapping):
                    yield from _iter_removed_paths(args[0], item, prefix=path)
        elif origin is dict and args and isinstance(value, Mapping):
            for item in value.values():
                if isinstance(item, Mapping):
                    yield from _iter_removed_paths(args[-1], item, prefix=path)
        elif _is_schema_model(annotation) and isinstance(value, Mapping):
            yield from _iter_removed_paths(annotation, value, prefix=path)


# ───────────────────────── 判据入口 ─────────────────────────


def check_field_lifecycle(
    config_name: type,
    data: Mapping[str, Any],
    *,
    file_name: str,
    generated_paths: frozenset[str] | None = None,
) -> list[str]:
    """检查文件数据里出现的**被声明字段**：弃用出声、移除拒绝。

    调用点：`load_config_from_file` 里"版本链前置校验之后、任何写入之前"——与版本链拒绝
    同一个位置，所以被拒时原文件字节不动。

    Args:
        config_name: 配置文件身份（``Config`` / ``ModelConfig`` 类对象）。
        data: 从文件读出的配置数据（已 ``unwrap()`` 的纯结构；``_migrations`` 已摘出）。
        file_name: 出错时进消息的文件标识（调用方给完整路径，别只给文件名）。
        generated_paths: **程序自己生成的默认值路径**集合（由同目录 `.template` 基线导出，
            见 `collect_generated_paths`）。这些路径上的弃用键是**我们写进用户配置的**，
            不是用户的选择 ⇒ **不出声**。
            ⚠️ 它不是"宽容开关"：``REMOVED`` 的拒绝**不受它影响**——"文件里有已移除字段"
            就是拒绝加载，与这键出自谁手无关（否则"危险键恰好也在默认值里"＝一键白名单）。

    Returns:
        本次命中的**弃用**字段路径列表（**去重、保序**）。粒度是**字段路径**而不是"表项×字段"：
        ``[[api_providers]]`` 里有 3 项都带同一个弃用键 ⇒ 返回 1 条路径，但**日志按表项各出一条**
        （现场需要知道是哪一个表项；返回值是给判据/调用方用的，重复项没有信息量）。

    Raises:
        ConfigFieldRefusedError: 文件里出现了声明为 ``REMOVED`` 的字段（**在写之前**）。
    """
    declarations = declarations_for(config_name)
    if not declarations:
        return []  # 没声明就没有可检查的东西——不做任何遍历，加载路径零额外开销

    suppression = generated_paths or frozenset()
    declaration_by_path = {item.path: item for item in declarations}
    hits: list[tuple[FieldLifecycle, Any]] = []
    _walk_declared_paths(data, config_name, declaration_by_path, prefix="", file_name=file_name, hits=hits)

    refused: list[FieldLifecycle] = []
    deprecated_paths: list[str] = []
    suppressed: list[str] = []
    for declaration, value in hits:
        if declaration.state is FieldLifecycleState.REMOVED:
            refused.append(declaration)
            continue
        if declaration.state is FieldLifecycleState.DEPRECATED:
            if declaration.path not in deprecated_paths:
                deprecated_paths.append(declaration.path)
            if declaration.path in suppression:
                suppressed.append(declaration.path)
                continue
            replacement_text = f"，请改用 {declaration.replacement}" if declaration.replacement else ""
            logger.warning(
                f"[配置弃用] {file_name} 里的 {declaration.path} 已弃用"
                f"{f'（{declaration.reason}）' if declaration.reason else ''}{replacement_text}；"
                f"当前值 {value!r} 仍然生效，但请尽快迁移"
            )

    if refused:
        first = refused[0]
        _report_field_refusal(first, file_name=file_name, refused_count=len(refused))
        raise ConfigFieldRefusedError(
            file_name=file_name,
            path=first.path,
            replacement=first.replacement,
            reason=first.reason,
        )

    if suppressed:
        # 出声的判据要能解释"为什么这次没响"——否则下一个人只会看到"警告时有时无"
        logger.debug(
            "%s 里 %d 个弃用字段取自程序生成的默认值（不是用户显式保留的选择），本次不出声：%s",
            file_name,
            len(suppressed),
            ", ".join(dict.fromkeys(suppressed)),
        )

    return deprecated_paths


def _declared_paths_in(data: Mapping[str, Any], config_name: type) -> frozenset[str]:
    """在**同一份声明表**的坐标系下，列出 ``data`` 里出现的被声明路径（不管什么状态）。

    给"程序生成的默认值"当基线用：把生成的配置走一遍**同一个**遍历，得到的集合与
    `check_field_lifecycle` 的命中判据必然同口径——两处若各写一套遍历，抑制集迟早与命中集
    错位，而错位的表现是"警告时有时无"，属最难查的那种。
    """
    declarations = declarations_for(config_name)
    if not declarations:
        return frozenset()
    declaration_by_path = {item.path: item for item in declarations}
    hits: list[tuple[FieldLifecycle, Any]] = []
    _walk_declared_paths(data, config_name, declaration_by_path, prefix="", file_name="", hits=hits)
    return frozenset(declaration.path for declaration, _value in hits)


def collect_generated_paths(config_name: type, generated_data: Mapping[str, Any]) -> frozenset[str]:
    """导出"程序生成的默认值"里的被声明路径集合（`check_field_lifecycle` 的抑制集）。

    ## 为什么需要它（实测出来的必要，不是设计洁癖）

    `generate_new_config_file` 落盘的默认 `bot_config.toml` **自己就带着那 6 个弃用字段**
    （模板逐字段写全）。没有抑制集时，用户**什么都没改**也会在每次启动看到 6 条弃用警告
    ⇒ 把"提示"变成"背景噪声"，而噪声会把真正的弃用信号一起埋掉。

    ⇒ 口径定为：**弃用只对"用户显式保留的选择"出声**。

    - 键在文件里、但**不在**程序的默认值里（＝用户自己写/自己留下的）⇒ 出声；
    - 键只在程序的默认值里（用户没动过它）⇒ 不出声（debug 留一行解释，不静默）。

    这也顺手解决了模板更新的场景：程序哪天不再写这些键，用户文件里那份就**不再是**默认值形态
    （用户配置是模板的超集）⇒ 从那一刻起警告会正常响起来。

    ⚠️ 与"拒绝"分道扬镳：``REMOVED`` 的拒绝**不看**抑制集——"文件里有已移除字段"就拒绝加载，
    与这键出自谁手无关（否则"危险键恰好也在默认值里"＝一键白名单）。

    Args:
        config_name: 配置文件身份。
        generated_data: 程序生成的默认配置（已 ``unwrap()`` 的纯结构）。
    """
    return _declared_paths_in(generated_data, config_name)


def _report_field_refusal(declaration: FieldLifecycle, *, file_name: str, refused_count: int) -> None:
    """字段级拒绝的双通道上报（债务原则：异常不得单通道 —— logger + 上报 port）。

    与 `_report_version_chain_refusal` 同构：只上报，**不写盘、不兜底**——拒绝语义的
    关键是"原文件不动"，任何"顺手修一下"都会把这份文件变成不可审计的中间态。
    """
    from src.core.error_escalation.types import ErrorLevel
    from src.core.error_escalation_port_registry import get_error_escalation_port

    port = get_error_escalation_port()
    if port is not None:
        port.report(ErrorLevel.ERROR, "配置含已移除字段，拒绝迁移（原文件未改动）")
    logger.error(
        f"配置字段级拒绝：{file_name} 含已移除字段 {declaration.path}"
        f"（共 {refused_count} 个未列出），原文件未改动；替代者：{declaration.replacement or '无'}"
    )


def removed_field_paths(config_name: type, data: Mapping[str, Any]) -> list[str]:
    """诊断入口：列出文件里所有"模型不认"的键路径（含未被声明的）。

    给"账目对齐"用——判断某个静默丢弃的键值不值得升级成一条 ``REMOVED`` 声明。
    返回的路径是**扁平的点分路径**（数组不下标），与声明表写法一致。

    Args:
        config_name: 配置文件身份。
        data: 从文件读出的配置数据。
    """
    return sorted(_iter_removed_paths(config_name, data))


def refusal_message_for(path: str, *, file_name: str, replacement: str | None, reason: str = "") -> str:
    """按同一套口径拼一条拒绝消息（给需要预演/文档化的调用方，避免两处措辞漂移）。"""
    return str(
        ConfigFieldRefusedError(file_name=file_name, path=path, replacement=replacement, reason=reason)
    )


def declaration_source_path(config_name: type) -> Path | None:
    """本模块源码路径（诊断/文档用：声明写在哪一份文件里，报错时能一句话说清）。"""
    if not declarations_for(config_name):
        return None
    return Path(__file__)
