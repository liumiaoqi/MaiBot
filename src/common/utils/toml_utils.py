"""
TOML 工具函数

提供 TOML 文件的格式化保存功能，确保数组等元素以美观的多行格式输出。
"""

import re
import tomllib
from collections.abc import Mapping
from typing import Any

import tomlkit
from tomlkit.items import AoT, Array, InlineTable, Table

from src.common.logger import get_logger

logger = get_logger("toml_utils")


def _to_toml_value(value: Any, *, inline: bool = False) -> Any:
    """把纯 Python 值转为 TOML 节点。

    ``inline=True`` 时只产出行内结构（InlineTable / Array），不会生成 Table 或 AoT。
    这是「按目标节点类型写入」的构造器：行内表里放 dict 时，必须是行内表而不是表段。
    """
    if isinstance(value, Mapping):
        if inline:
            table = tomlkit.inline_table()
            for key, item in value.items():
                table[key] = _to_toml_value(item, inline=True)
            return table
        return tomlkit.item(dict(value))

    if isinstance(value, list):
        array = tomlkit.array()
        for item in value:
            array.append(_to_toml_value(item, inline=True))
        return array

    return tomlkit.item(value)


def _format_toml_value(obj: Any, threshold: int, depth: int = 0) -> Any:
    """递归格式化 TOML 值，将数组转换为多行格式"""
    # 处理 AoT (Array of Tables) - 保持原样，递归处理内部
    if isinstance(obj, AoT):
        for item in obj:
            _format_toml_value(item, threshold, depth)
        return obj

    # 处理字典类型 (dict 或 Table)
    if isinstance(obj, (dict, Table)):
        for k, v in obj.items():
            obj[k] = _format_toml_value(v, threshold, depth)
        return obj

    # 处理列表类型 (list 或 Array)
    if isinstance(obj, (list, Array)):
        if isinstance(obj, list) and not isinstance(obj, Array) and obj and isinstance(obj[0], (dict, Table)):
            for i, item in enumerate(obj):
                obj[i] = _format_toml_value(item, threshold, depth)
            return obj

        should_multiline = depth == 0 and len(obj) > threshold

        if isinstance(obj, Array):
            obj.multiline(should_multiline)
            for i, item in enumerate(obj):
                obj[i] = _format_toml_value(item, threshold, depth + 1)
            return obj

        arr = tomlkit.array()
        arr.multiline(should_multiline)

        for item in obj:
            arr.append(_format_toml_value(item, threshold, depth + 1))
        return arr

    return obj


def _update_toml_doc(target: Any, source: Any, _prefix: str = "") -> None:
    """递归合并字典，按目标既有节点类型写入，保留注释与格式。

    判定顺序（先判具体类型，再判 Table/Array 的父类）：
    1. ``None`` → 跳过并记录键路径（保留磁盘现值）；
    2. 既有 InlineTable + Mapping → 递归；
    3. 既有 InlineTable + 非 Mapping → 行内构造；
    4. 既有 AoT → ``tomlkit.item``（保持表数组语义）；
    5. 既有 Array（非 AoT）→ 行内构造（数组元素是行内表）；
    6. 既有 Table + Mapping → 递归；
    7. 新键且父为 InlineTable → 行内构造；
    8. 新键且父为普通 Table → ``tomlkit.item``；
    9. 其他 → ``tomlkit.item``。
    """
    if isinstance(source, list) or not isinstance(source, dict) or not isinstance(target, dict):
        return

    for key, value in source.items():
        if key == "version":
            continue

        key_path = f"{_prefix}.{key}" if _prefix else key

        if value is None:
            logger.warning(f"配置合并跳过 None 值：{key_path}（保留磁盘现值）")
            continue

        if key not in target:
            if isinstance(target, InlineTable):
                target[key] = _to_toml_value(value, inline=True)
            else:
                target[key] = tomlkit.item(value)
            continue

        target_value = target[key]

        if isinstance(target_value, InlineTable):
            if isinstance(value, Mapping):
                _update_toml_doc(target_value, value, key_path)
            else:
                target[key] = _to_toml_value(value, inline=True)
            continue

        if isinstance(target_value, AoT):
            target[key] = tomlkit.item(value)
            continue

        if isinstance(target_value, Array):
            target[key] = _to_toml_value(value, inline=True)
            continue

        if isinstance(target_value, Table):
            if isinstance(value, Mapping):
                _update_toml_doc(target_value, value, key_path)
            else:
                target[key] = tomlkit.item(value)
            continue

        target[key] = tomlkit.item(value)


def save_toml_with_format(
    data: Any, file_path: str, multiline_threshold: int = 1, preserve_comments: bool = True
) -> None:
    """
    格式化 TOML 数据并保存到文件。

    Args:
        data: 要保存的数据（dict 或 tomlkit 文档）
        file_path: 保存路径
        multiline_threshold: 数组多行格式化阈值，-1 表示不格式化
        preserve_comments: 是否保留原文件的注释和格式
    """
    import os

    from tomlkit import TOMLDocument

    if preserve_comments and os.path.exists(file_path) and not isinstance(data, TOMLDocument):
        with open(file_path, "r", encoding="utf-8") as f:
            doc = tomlkit.load(f)
        _update_toml_doc(doc, data)
        data = doc

    formatted = _format_toml_value(data, multiline_threshold) if multiline_threshold >= 0 else data
    output = tomlkit.dumps(formatted)
    output = re.sub(r"\n{3,}", "\n\n", output)

    # ── 写盘前校验（2026-08-14 事故加固——configfs L5 提交式语义）──
    # 08-09 事故：bot_config.toml 被写坏（inner_voices 42 条拍平）→ 容器启动崩溃。
    # 三层防护：① 产物必须是合法 TOML（防调用方漏验证/格式化 bug）② 写前备份旧文件
    #（写坏可恢复）③ 原子写（tmp + replace——防写一半崩溃留下半文件）。
    try:
        tomlkit.loads(output)
    except Exception as e:
        logger.error(f"配置写入被拒绝：生成内容不是合法 TOML——{e}")
        raise ValueError(f"配置写入被拒绝：生成内容不是合法 TOML——{e}") from e

    try:
        tomllib.loads(output)
    except Exception as e:
        logger.error(f"配置写入被拒绝：tomllib 校验失败——{e}")
        raise ValueError(f"配置写入被拒绝：生成内容不是合法 TOML（tomllib）——{e}") from e

    import os

    if os.path.exists(file_path):
        try:
            # 备份旧配置（最多保留一份——每次覆盖——恢复用 .bak）
            import shutil

            shutil.copy2(file_path, file_path + ".bak")
        except OSError as backup_error:
            logger.warning(f"配置备份失败（继续写入）：{backup_error}")

    tmp_path = file_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(output)
    os.replace(tmp_path, file_path)  # 原子替换（Windows/Linux 均支持）
