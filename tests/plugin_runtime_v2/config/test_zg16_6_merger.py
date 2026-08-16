"""ZG16-6a: 配置合并算法测试——纯对象深合并 / 数组整体替换 / 未写键保留下层。

覆盖 design 4.1 全部 16 个场景，spec 8.1 实测验证项（10 项）。
"""

import time

import pytest

from src.plugin_runtime_v2.config.merger import (
    ProvenanceEntry,
    _validate_stream_id,
    merge_layers,
    merge_three_layers,
    merge_with_provenance,
    resolve_stream_override,
)


def test_pure_object_deep_merge():
    """纯对象深合并（spec 5.1.1 规则 2）。"""
    assert merge_layers({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}}) == {"a": {"b": 1, "c": 3}}


def test_array_whole_replace():
    """数组整体替换（spec 5.1.1 规则 3a）。"""
    assert merge_layers({"whitelist": ["a", "b"]}, {"whitelist": ["c"]}) == {"whitelist": ["c"]}


def test_array_empty_replace():
    """数组空替换（spec 5.1.1 规则 3b）。"""
    assert merge_layers({"list": [1, 2, 3]}, {"list": []}) == {"list": []}


def test_unwritten_key_keep_under():
    """未写键保留下层（spec 5.1.1 规则 5a）。"""
    assert merge_layers({"a": 1, "b": 2}, {"b": 20}) == {"a": 1, "b": 20}


def test_empty_override():
    """覆盖节为空（spec 5.1.1 规则 5b）。"""
    assert merge_layers({"a": 1}, {}) == {"a": 1}


def test_scalar_whole_replace():
    """标量整体替换（spec 5.1.1 规则 4）。"""
    assert merge_layers({"port": 3001}, {"port": 3002}) == {"port": 3002}


def test_three_layers_overlay():
    """三层叠加（spec 5.1.1 规则 1b）。"""
    assert merge_three_layers({"port": 3001}, {"port": 3002}, {"port": 3003}) == {"port": 3003}


def test_three_layers_partial_overlay():
    """三层叠加——部分键覆盖，未覆盖键保留 base。"""
    result = merge_three_layers({"port": 3001, "host": "a"}, {"port": 3002}, {})
    assert result == {"port": 3002, "host": "a"}


def test_per_stream_fallback_no_override():
    """per_stream fallback-无覆盖回退全局（spec 5.1.1 规则 6a）。"""
    assert resolve_stream_override("X", "group:123", {}) == {}


def test_per_stream_fallback_hit():
    """per_stream 命中返回对应覆盖。"""
    overrides = {"group:123": {"port": 9999}}
    assert resolve_stream_override("X", "group:123", overrides) == {"port": 9999}


def test_per_stream_invalid_id_fallback():
    """stream_id 格式非法 → 回退空 dict。"""
    assert resolve_stream_override("X", "invalid_id", {"invalid_id": {"port": 1}}) == {}


def test_per_stream_none_stream_id():
    """stream_id 为 None → 回退空 dict。"""
    assert resolve_stream_override("X", None, {"group:123": {"port": 1}}) == {}


def test_pure_function_no_mutation():
    """纯函数性——不修改输入（spec 5.1.1 规则 8）。"""
    base = {"a": 1}
    override = {"b": 2}
    merge_layers(base, override)
    assert base == {"a": 1} and override == {"b": 2}


def test_non_pure_object_whole_replace():
    """非纯对象整体替换（spec 5.1.1 规则 11）。"""
    assert merge_layers([[1, 2]], [[3]]) == [[3]]


def test_stream_id_validation():
    """stream_id 格式校验（spec 5.1.1 规则 7）。"""
    assert _validate_stream_id("group:123456") is True
    assert _validate_stream_id("user:789") is True
    assert _validate_stream_id("invalid_id") is False


def test_stream_id_validation_edge_cases():
    """stream_id 格式校验边界场景。"""
    assert _validate_stream_id("group:") is False  # 空 ID
    assert _validate_stream_id("user:") is False  # 空 ID
    assert _validate_stream_id("group:abc") is False  # 非数字
    assert _validate_stream_id("") is False  # 空字符串


def test_no_plugin_override_degradation():
    """无 plugin_override 退化（spec 5.6.1 规则 6）。"""
    assert merge_three_layers({"port": 3001}, {}, {}) == {"port": 3001}


def test_merge_with_provenance_base_layer():
    """merge_with_provenance 标注 base 层来源。"""
    merged, provenance = merge_with_provenance(
        {"port": 3001}, {}, {}, "plugin/config.toml", "config/bot_config.toml"
    )
    assert merged == {"port": 3001}
    assert provenance["port"].layer == "base"
    assert provenance["port"].file == "plugin/config.toml"


def test_merge_with_provenance_global_override():
    """merge_with_provenance 全局覆盖层标注。"""
    merged, provenance = merge_with_provenance(
        {"port": 3001}, {"port": 3002}, {}, "plugin/config.toml", "config/bot_config.toml"
    )
    assert merged == {"port": 3002}
    assert provenance["port"].layer == "global_override"
    assert provenance["port"].file == "config/bot_config.toml"


def test_merge_with_provenance_stream_override():
    """merge_with_provenance 聊天流覆盖层标注。"""
    merged, provenance = merge_with_provenance(
        {"port": 3001}, {"port": 3002}, {"port": 3003},
        "plugin/config.toml", "config/bot_config.toml",
    )
    assert merged == {"port": 3003}
    assert provenance["port"].layer == "stream_override"


def test_provenance_entry_frozen():
    """ProvenanceEntry 是 frozen dataclass。"""
    entry = ProvenanceEntry("base", "config.toml", 10)
    with pytest.raises(AttributeError):
        entry.layer = "override"  # type: ignore[misc]


@pytest.mark.parametrize("size", [10, 100, 500])
def test_merge_performance(size):
    """性能 < 10ms（spec 4.1.1）。"""
    base = {f"key_{i}": {"nested": i} for i in range(size)}
    override = {f"key_{i}": {"nested": i + 1} for i in range(size // 2)}
    start = time.perf_counter()
    merge_layers(base, override)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 10  # P99 < 10ms