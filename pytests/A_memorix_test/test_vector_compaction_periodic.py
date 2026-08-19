"""ZG-29 T5: 向量 compaction 周期化测试。"""

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from src.A_memorix.core.runtime.services.maintenance import MaintenanceService


def _make_maintenance(trigger_compaction: MagicMock | None = None, interval_days: float = 7.0) -> MaintenanceService:
    cfg_data = {
        "memory.vector_compaction_interval_days": interval_days,
    }

    def cfg(key: str, default=None):
        return cfg_data.get(key, default)

    return MaintenanceService(
        get_metadata_store=lambda: MagicMock(),
        get_graph_store=lambda: MagicMock(),
        cfg=cfg,
        persist=lambda: None,
        rebuild_graph_from_metadata=lambda: None,
        resolve_relation_hashes=lambda x: [],
        resolve_deleted_relation_hashes=lambda x: [],
        delete_vectors_by_type=lambda **kw: None,
        background_scheduler=MagicMock(),
        trigger_vector_compaction=trigger_compaction,
    )


def test_compaction_triggers_after_interval() -> None:
    """超过 interval 后触发一次 compaction。"""
    trigger = MagicMock(return_value=2)
    svc = _make_maintenance(trigger, interval_days=0.0)

    asyncio.run(svc._vector_compaction_phase())

    trigger.assert_called_once()
    assert svc._last_vector_compaction_at > 0


def test_compaction_skipped_within_interval() -> None:
    """周期内不重复触发。"""
    trigger = MagicMock(return_value=1)
    svc = _make_maintenance(trigger, interval_days=7.0)

    asyncio.run(svc._vector_compaction_phase())
    assert trigger.call_count == 1

    asyncio.run(svc._vector_compaction_phase())
    assert trigger.call_count == 1


def test_compaction_no_callback_skips() -> None:
    """无 trigger_vector_compaction 回调时跳过。"""
    svc = _make_maintenance(None)
    asyncio.run(svc._vector_compaction_phase())


def test_last_compaction_at_is_instance_attribute() -> None:
    """_last_vector_compaction_at 是实例属性。"""
    svc1 = _make_maintenance(MagicMock(return_value=0), interval_days=0.0)
    svc2 = _make_maintenance(MagicMock(return_value=0), interval_days=7.0)
    assert svc1._last_vector_compaction_at == 0.0
    assert svc2._last_vector_compaction_at == 0.0

    asyncio.run(svc1._vector_compaction_phase())
    assert svc1._last_vector_compaction_at > 0
    assert svc2._last_vector_compaction_at == 0.0