"""ZG-29 T4: config_schema memory 段扩展测试。"""

import json
from pathlib import Path

import pytest


def _load_schema() -> dict:
    schema_path = Path(__file__).resolve().parents[2] / "src" / "A_memorix" / "config_schema.json"
    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_new_params_have_defaults() -> None:
    """新参数有默认值。"""
    schema = _load_schema()
    memory_fields = schema["sections"]["memory"]["fields"]
    assert "deleted_relations_retention_days" in memory_fields
    assert memory_fields["deleted_relations_retention_days"]["default"] == 30
    assert "purge_batch_size" in memory_fields
    assert memory_fields["purge_batch_size"]["default"] == 500
    assert "vector_compaction_interval_days" in memory_fields
    assert memory_fields["vector_compaction_interval_days"]["default"] == 7


def test_new_params_types() -> None:
    """新参数类型正确。"""
    schema = _load_schema()
    memory_fields = schema["sections"]["memory"]["fields"]
    assert memory_fields["deleted_relations_retention_days"]["type"] == "number"
    assert memory_fields["purge_batch_size"]["type"] == "integer"
    assert memory_fields["vector_compaction_interval_days"]["type"] == "number"


def test_existing_enabled_field_preserved() -> None:
    """既有 enabled 字段保留。"""
    schema = _load_schema()
    memory_fields = schema["sections"]["memory"]["fields"]
    assert "enabled" in memory_fields
    assert memory_fields["enabled"]["default"] is True