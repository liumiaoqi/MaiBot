"""约束契约：凡带 pydantic 约束的字段，其约束必须出现在生成的 schema 里。

## 这是哪门子的契约（1 段 · schema 单源）

`src/webui/config_schema.py::ConfigSchemaGenerator._build_field_schema` 把 pydantic 字段约束
翻译成 WebUI 消费的 IR 键。这张翻译表就是"单一真源 → 派生"的接缝：**任何一条没被翻译的约束，
在 UI 上等于不存在**（用户能填出后端一定拒绝的值）。

本模块把这张翻译表写成断言，并把当前**未覆盖**的项逐条登记进 `KNOWN_UNMAPPED`（带理由）。
`test_known_unmapped_is_not_stale` 是防腐层：**2 段补上映射之后本测试会红**，逼你删掉豁免行 ——
豁免清单不会随时间静默变成谎言。

## 口径（与 `C:\\hub\\.scratch\\schema_constraint_audit.py` 同一张表）

「约束已覆盖」= 生成 schema 的**该字段节点**以**约定键**携带**同一个值**。
`CONTRACT` 的键名是 1 段的建议；2 段落地时若改名，**只改这一处**。

字段被 `AMEMORIX_*_FIELD_PATHS` 策略排除在 schema 之外时，"约束未进 schema"是**设计如此**，
不算缺口；但它的条数钉在 `EXPECTED_POLICY_EXCLUSIONS` 上当哨兵，策略一改就红。

## 两条边界（1 段实测，不是推测）

- `gt`/`lt` 映射到 `minValue`/`maxValue` 是**有损**的：前端只有这两个键，开区间语义表达不了
  （UI 会放行边界值、后端拒绝）。`CONTRACT` 按"至少把界值带出去"取值；要严格需新增
  `exclusiveMinValue`/`exclusiveMaxValue` 并由前端消费 —— 属 2 段的决策点。
- `model_post_init`（或 `@model_validator`）里的**跨字段**条件（"A 非空则 B 必填"之类）
  `Field(...)` 表达不了 ⇒ **这类约束不在本契约的覆盖范围**。
  注：`config_base.py` 已于 2026-10-16 放行 `@field_validator`/`@model_validator`
  （原先一刀切拒绝配置类里的任何方法），但**写了也不进 schema** ——
  `ConfigSchemaGenerator` 只读 `model_fields`，不读 validator。所以本契约只管
  `FieldInfo.metadata` 与 annotation 两类来源。
"""

import inspect
from enum import Enum
from types import UnionType
from typing import Any, Dict, List, Literal, NamedTuple, Optional, Sequence, Tuple, Union, get_args, get_origin

from pydantic_core import PydanticUndefined

from src.config.config import Config, ModelConfig
from src.config.config_base import ConfigBase
from src.webui.config_schema import ConfigSchemaGenerator

# ── 翻译契约：pydantic 约束种类 → 生成 schema 的键 ────────────────────────────────
CONTRACT: Dict[str, Optional[str]] = {
    "ge": "minValue",
    "le": "maxValue",
    "gt": "minValue",
    "lt": "maxValue",
    "min_length": "minLength",
    "max_length": "maxLength",
    "pattern": "pattern",
    "multiple_of": "multipleOf",
}

OPTIONS_KEY = "options"

# 生成器 `_build_field_schema` 自己算的键 —— `json_schema_extra` 带同名键就会**覆盖**它
_DERIVED_KEYS: Sequence[str] = ("name", "type", "description", "required", "default", "items", "options")

# 生成器跳过的不算字段（config_schema.py:271）
_HIDDEN_FIELDS = frozenset({"field_docs", "_validate_any", "suppress_any_warning"})

# a_memorix 可见性策略排除掉的**约束条目**条数（2026-10-16 实测）。
# ⚠️ 这是刻意的哨兵：策略变更（增删白名单/黑名单）会改这个数 —— 请同步本常量并说明原因，
#    别让它静默漂移（这种"静默放过"正是本契约要防的）。
EXPECTED_POLICY_EXCLUSIONS = 67

# ── 当前未覆盖项（②类交付：每条都指向 src/webui/config_schema.py 侧要补的映射） ──
KNOWN_UNMAPPED: Dict[Tuple[str, str], str] = {
    # G-1 · gt/lt 未映射（config_schema.py:389-395 只认 ge/le）—— `gt` 6 条
    ("a_memorix.memory.watermark.check_interval_sec", "gt"): "G-1 gt 无映射",
    ("mcp.servers[].http_timeout_seconds", "gt"): "G-1 gt 无映射",
    ("mcp.servers[].read_timeout_seconds", "gt"): "G-1 gt 无映射",
    ("plugin_runtime.render.startup_timeout_sec", "gt"): "G-1 gt 无映射",
    ("plugin_runtime.render.render_timeout_sec", "gt"): "G-1 gt 无映射",
    ("plugin_runtime.render.download_connection_timeout_sec", "gt"): "G-1 gt 无映射",
    # G-2 · min_length 未映射（1 段把散落校验搬进 Field 后新暴露）—— 5 条
    ("keyword_reaction.keyword_rules[].reaction", "min_length"): "G-2 min_length 无映射",
    ("keyword_reaction.regex_rules[].reaction", "min_length"): "G-2 min_length 无映射",
    ("models[].category", "min_length"): "G-2 min_length 无映射",
    ("models[].name", "min_length"): "G-2 min_length 无映射",
    ("models[].api_provider", "min_length"): "G-2 min_length 无映射",
    # G-3 · pattern 未映射（1 段把散落校验搬进 Field 后新暴露）—— 1 条
    ("mcp.servers[].name", "pattern"): "G-3 pattern 无映射",
}


class FieldRow(NamedTuple):
    """一次遍历产出的字段行。"""

    path: str
    defined_in: str
    annotation: Any
    metadata: Sequence[Any]
    extra: Dict[str, Any]
    has_default: bool
    included: bool
    exclude_reason: str


class Finding(NamedTuple):
    """一条"约束没进 schema"。"""

    path: str
    kind: str
    expected_key: Optional[str]
    detail: str


# ── annotation 工具 ────────────────────────────────────────────────────────────


def _strip_optional(annotation: Any) -> Any:
    """剥掉 `Optional[...]` 外壳（ConfigBase 只允许这一种 Union）。"""
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _literal_options(annotation: Any) -> Optional[List[str]]:
    inner = _strip_optional(annotation)
    if get_origin(inner) is Literal:
        return [str(value) for value in get_args(inner)]
    return None


def _enum_options(annotation: Any) -> Optional[List[str]]:
    inner = _strip_optional(annotation)
    if isinstance(inner, type) and issubclass(inner, Enum):
        return [str(member.value) for member in inner]
    return None


# ── 遍历：pydantic 侧 ──────────────────────────────────────────────────────────


def _nested_child(field_path: str, annotation: Any) -> Tuple[Optional[type], str]:
    """复刻 `_build_nested_schema` 的路径规则（`list[X]` → `path[]`）。"""
    origin = get_origin(annotation)
    args = get_args(annotation)
    if inspect.isclass(annotation) and issubclass(annotation, ConfigBase):
        return annotation, field_path
    if origin in {list, set, tuple} and args:
        first = args[0]
        if inspect.isclass(first) and issubclass(first, ConfigBase):
            return first, f"{field_path}[]"
    return None, ""


def _classify(field_path: str, annotation: Any) -> Tuple[bool, str]:
    """该字段会不会进 schema —— 直接复用生成器的真函数，保证口径同源。"""
    nested_schema = ConfigSchemaGenerator._build_nested_schema(annotation, field_path)
    visibility = ConfigSchemaGenerator._get_a_memorix_visibility(field_path)
    if visibility == "excluded":
        return False, "AMEMORIX_EXCLUDED_FIELD_PATHS"
    if nested_schema is not None and not ConfigSchemaGenerator._schema_has_visible_content(nested_schema):
        return False, "嵌套块无可见字段（子字段全被 a_memorix 策略排除）"
    if visibility is None and ConfigSchemaGenerator._is_a_memorix_path(field_path) and nested_schema is None:
        return False, "a_memorix 路径未登记于 basic/advanced 清单"
    return True, ""


def _collect_rows(config_class: type, path_prefix: str = "", parent_reason: str = "") -> List[FieldRow]:
    rows: List[FieldRow] = []
    for field_name, field_info in config_class.model_fields.items():
        if field_name in _HIDDEN_FIELDS:
            continue
        path = f"{path_prefix}.{field_name}" if path_prefix else field_name
        included, reason = _classify(path, field_info.annotation)
        if parent_reason:
            included, reason = False, f"父块未进 schema（{parent_reason}）"
        extra = field_info.json_schema_extra if isinstance(field_info.json_schema_extra, dict) else {}
        rows.append(
            FieldRow(
                path=path,
                defined_in=config_class.__name__,
                annotation=field_info.annotation,
                metadata=field_info.metadata,
                extra=extra,
                has_default=field_info.default is not PydanticUndefined,
                included=included,
                exclude_reason=reason,
            )
        )
        child, child_prefix = _nested_child(path, field_info.annotation)
        if child is not None:
            rows.extend(_collect_rows(child, child_prefix, reason))
    return rows


# ── 遍历：生成 schema 侧 ───────────────────────────────────────────────────────


def _flatten_schema(schema: Dict[str, Any], prefix: str, out: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    for node in schema.get("fields", ()):
        out[f"{prefix}.{node['name']}" if prefix else node["name"]] = node
    for name, nested in (schema.get("nested") or {}).items():
        child_prefix = f"{prefix}.{name}" if prefix else name
        parent = out.get(child_prefix)
        if parent is not None and parent.get("type") == "array":
            child_prefix = f"{child_prefix}[]"
        _flatten_schema(nested, child_prefix, out)
    return out


def _generated_nodes(schema_name: str) -> Dict[str, Dict[str, Any]]:
    config_class = {"Config": Config, "ModelConfig": ModelConfig}[schema_name]
    # 关键：**不实例化**配置类（生成器本身也不实例化）——这样测的就是真实调用路径的状态
    return _flatten_schema(ConfigSchemaGenerator.generate_config_schema(config_class), "", {})


# ── 对账 ───────────────────────────────────────────────────────────────────────


def _field_constraints(row: FieldRow) -> List[Tuple[str, Any, Optional[str]]]:
    """(约束种类, pydantic 侧的值, 期望的 schema 键)。"""
    found: List[Tuple[str, Any, Optional[str]]] = []
    for item in row.metadata:
        for kind, key in CONTRACT.items():
            if not hasattr(item, kind):
                continue
            value = getattr(item, kind)
            if value is None:
                continue
            found.append((kind, value, key))
    for options in (_literal_options(row.annotation), _enum_options(row.annotation)):
        if options is not None:
            found.append(("literal", tuple(options), OPTIONS_KEY))
    return found


def _audit() -> Tuple[List[Finding], List[Tuple[str, str]], List[Tuple[str, Dict[str, Any]]], List[str]]:
    """→ (gaps, policy_excluded, shadowed, unrebuilt)"""
    gaps: List[Finding] = []
    policy_excluded: List[Tuple[str, str]] = []
    shadowed: List[Tuple[str, Dict[str, Any]]] = []
    unrebuilt: List[str] = []

    for schema_name in ("Config", "ModelConfig"):
        config_class = {"Config": Config, "ModelConfig": ModelConfig}[schema_name]
        nodes = _generated_nodes(schema_name)
        for row in _collect_rows(config_class):
            derived = _derived_keys(row)
            clash = {key: row.extra[key] for key in _DERIVED_KEYS if key in row.extra and key in derived}
            if clash:
                shadowed.append((row.path, clash))
            for kind, value, key in _field_constraints(row):
                node = nodes.get(row.path)
                if not row.included:
                    policy_excluded.append((row.path, kind))
                    continue
                if node is None:
                    gaps.append(Finding(row.path, kind, key, "字段不在生成 schema 中"))
                    continue
                if kind == "literal":
                    options = node.get(OPTIONS_KEY) or []
                    missing = [item for item in value if item not in options]
                    if missing:
                        gaps.append(Finding(row.path, kind, OPTIONS_KEY, f"{OPTIONS_KEY}={options} 缺 {missing}"))
                    continue
                if key is None or key not in node:
                    gaps.append(Finding(row.path, kind, key, f"约定键 {key} 不在字段节点（节点键 {sorted(node)}）"))
                    continue
                if node[key] != value:
                    gaps.append(Finding(row.path, kind, key, f"{key}={node[key]!r} ≠ pydantic {kind}={value!r}"))

    # 前向引用未补完 ⇒ 派生 schema 会**与调用顺序有关**地变形（nested 块丢失 + items.type 误报）
    for config_class in (Config, ModelConfig):
        for klass in _walk_classes(config_class):
            if getattr(klass, "__pydantic_complete__", True) is False:
                unrebuilt.append(klass.__name__)
    return gaps, policy_excluded, shadowed, sorted(set(unrebuilt))


def _walk_classes(config_class: type) -> List[type]:
    out: List[type] = [config_class]
    for row in _collect_rows(config_class):
        child, _ = _nested_child(row.path, row.annotation)
        if child is not None and child not in out:
            out.extend(_walk_classes(child))
    return out


def _derived_keys(row: FieldRow) -> set:
    """生成器在合并 `json_schema_extra` **之前**会算出来的键（`_build_field_schema` 的算法）。"""
    keys = {"name", "type", "label", "description", "required"}
    if row.has_default:
        keys.add("default")
    origin = get_origin(row.annotation)
    args = get_args(row.annotation)
    if origin in {list, set} and args:
        keys.add("items")
    if ConfigSchemaGenerator._extract_options(row.annotation) is not None:
        keys.add("options")
    return keys


def test_constraint_contract_green():
    """凡带 pydantic 约束的字段，其约束必须出现在生成 schema 里（未登记项 = 红线）。"""
    gaps, _policy, _shadowed, _unrebuilt = _audit()
    unexpected = [finding for finding in gaps if (finding.path, finding.kind) not in KNOWN_UNMAPPED]
    assert not unexpected, "以下约束没进生成 schema，且未登记进 KNOWN_UNMAPPED：\n" + "\n".join(
        f"  · {finding.path} · {finding.kind} · 期望键 {finding.expected_key} · {finding.detail}"
        for finding in unexpected
    )


def test_known_unmapped_is_not_stale():
    """豁免清单防腐：每条登记项**必须仍是缺口** —— 2 段补上映射后本测试会红，逼你删行。"""
    gaps, _policy, _shadowed, _unrebuilt = _audit()
    actual = {(finding.path, finding.kind) for finding in gaps}
    stale = sorted(key for key in KNOWN_UNMAPPED if key not in actual)
    assert not stale, (
        "以下豁免项已不再是缺口（映射已补上或字段已变），请从 KNOWN_UNMAPPED 删除：\n"
        + "\n".join(f"  · {path} · {kind}（登记理由：{KNOWN_UNMAPPED[(path, kind)]}）" for path, kind in stale)
    )


def test_exemption_manifest_matches_reality():
    """缺口集合与 a_memorix 策略排除条数都要与登记完全一致（任何漂移都出声）。"""
    gaps, policy_excluded, _shadowed, _unrebuilt = _audit()
    actual = {(finding.path, finding.kind) for finding in gaps}
    assert actual == set(KNOWN_UNMAPPED), (
        f"缺口集合与登记不一致：新增 {sorted(actual - set(KNOWN_UNMAPPED))} · "
        f"已消失 {sorted(set(KNOWN_UNMAPPED) - actual)}"
    )
    assert len(policy_excluded) == EXPECTED_POLICY_EXCLUSIONS, (
        f"a_memorix 策略排除掉的约束条目数变了：实际 {len(policy_excluded)}、登记 {EXPECTED_POLICY_EXCLUSIONS}。\n"
        "若确为可见性策略变更，请同步 EXPECTED_POLICY_EXCLUSIONS 并写清原因。"
    )


def test_json_schema_extra_never_shadows_derived_keys():
    """单源：`json_schema_extra` 不许带生成器自己会算的键（会覆盖派生值，形成第二真源）。"""
    _gaps, _policy, shadowed, _unrebuilt = _audit()
    assert not shadowed, "以下字段的 json_schema_extra 覆盖了派生键，请删除手写副本：\n" + "\n".join(
        f"  · {path} · {clash}" for path, clash in shadowed
    )


def test_every_config_model_is_rebuilt_for_schema_generation():
    """前向引用必须已补完：生成器不实例化，未补完的模型会让派生 schema 随调用顺序变形。"""
    _gaps, _policy, _shadowed, unrebuilt = _audit()
    assert not unrebuilt, (
        "以下模型 __pydantic_complete__ 为 False（前向引用未解析）⇒ 生成 schema 时 nested 块会丢失、"
        "items.type 会误报。请在元素类定义就位后 model_rebuild()：\n" + "\n".join(f"  · {name}" for name in unrebuilt)
    )
