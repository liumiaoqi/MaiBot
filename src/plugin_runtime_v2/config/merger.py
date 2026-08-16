"""ZG16-6a: 配置合并算法——纯对象深度合并 / 数组整体替换 / 未写键保留下层。

设计参考：dsh mergeLayers `packages/settings/settings/src/index.ts:297-305`。
TOML 无 undefined，"未写键保留下层"对应"键不存在 → 保留下层"。
"""

import copy
from dataclasses import dataclass


def _is_plain_dict(obj) -> bool:
    """判断是否为纯对象（dict，非 list/标量/TOML 表数组）。"""
    return isinstance(obj, dict)


def merge_layers(under: dict, over: dict) -> dict:
    """纯对象深度递归合并。数组/标量/非纯对象整体替换。over 无键保留下层。

    设计参考：dsh mergeLayers `packages/settings/settings/src/index.ts:297-305`。
    TOML 无 undefined，"未写键保留下层"对应"键不存在 → 保留下层"。
    """
    # 非纯对象整体替换（数组/标量/TOML 表数组）
    if not _is_plain_dict(under) or not _is_plain_dict(over):
        return copy.deepcopy(over)
    # 纯对象深度递归合并
    merged = copy.deepcopy(under)
    for key, value in over.items():
        if key in merged:
            merged[key] = merge_layers(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def merge_three_layers(
    base: dict,
    global_override: dict,
    stream_override: dict,
) -> dict:
    """三层合并：base ← global_override ← stream_override。

    设计参考：dsh schema(mergeLayers(base, section)) `index.ts:696-710`。
    合并顺序：merge_layers(merge_layers(base, global_override), stream_override)。
    """
    merged = merge_layers(base, global_override)
    final = merge_layers(merged, stream_override)
    return final


@dataclass(frozen=True)
class ProvenanceEntry:
    """配置节来源标注。"""

    layer: str  # "base" | "global_override" | "stream_override"
    file: str  # 来源文件路径
    line: int | None  # 行号（可选）


def _validate_stream_id(stream_id: str) -> bool:
    """校验 stream_id 格式：group:{group_id} 或 user:{user_id}。"""
    return bool(
        (stream_id.startswith("group:") and stream_id[6:].isdigit())
        or (stream_id.startswith("user:") and stream_id[5:].isdigit())
    )


def resolve_stream_override(
    plugin_id: str,
    stream_id: str | None,
    per_stream_overrides: dict[str, dict],
) -> dict:
    """解析 per_stream 覆盖，不命中返回空 dict（回退全局 → base）。

    spec 5.1.1 规则 6：per_stream fallback 链
      聊天流覆盖 → 全局覆盖 → base（命中即返回，不继续回退）
    """
    if stream_id is None:
        return {}
    if not _validate_stream_id(stream_id):
        return {}  # 格式非法，回退全局 → base
    return per_stream_overrides.get(stream_id, {})


def merge_with_provenance(
    base: dict,
    global_override: dict,
    stream_override: dict,
    base_path: str,
    bot_config_path: str,
) -> tuple[dict, dict[str, ProvenanceEntry]]:
    """合并三层并跟踪每节来源层。返回 (合并后配置, provenance)。"""
    # 跟踪每节来源：遍历三层的键，标注来源层 + 文件路径
    provenance: dict[str, ProvenanceEntry] = {}
    # base 层标注
    for key in base:
        provenance[key] = ProvenanceEntry("base", base_path, None)
    # 全局覆盖层标注（覆盖 base）
    for key in global_override:
        provenance[key] = ProvenanceEntry("global_override", bot_config_path, None)
    # 聊天流覆盖层标注（覆盖全局 + base）
    for key in stream_override:
        provenance[key] = ProvenanceEntry("stream_override", bot_config_path, None)
    merged = merge_three_layers(base, global_override, stream_override)
    return merged, provenance