"""心跳发起者：recall_with_intuition 访问即续命（tier touch）+ 1h 节流。

对应施工规格 §3 五用例（弱断言不认）：
1. 种行 → 触发 ⇒ 精确时间戳（B7 窗内 +1）；
2. 窗内再触发 ⇒ 行不变 + `_touch_skip_count` +1（B4 可观测）；
3. 窗外再触发 ⇒ 精确新时间戳（B7 再 +1）；
4. C6 反面：不种行 ⇒ 触发 ⇒ 库里没多出行（no-op 语义钉住）；
5. C2 反面：touch_* 抛 ⇒ recall 载荷本体不变 + 双通道具名记录。

U1（验收库路由）：`MemoryField(tmp_path)` 的 episode/saga 库 = `tmp_path/connectionist.db`
（`memory_field.py:60-61` + `lifecycle_manager.py:27-28` 同一个 store 对象）⇒ 种行与断言读行同库。
"""

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.A_memorix.core.connectionist.lifecycle.lifecycle_manager as lifecycle_manager_module
import src.A_memorix.core.connectionist.memory_field as memory_field_module
from src.A_memorix.core.connectionist.memory_field import MemoryField

AGENT = "agent-heartbeat"
# 命中关键词（episode 走 all_concepts，saga 走 title；两者都要求 >=2 字符）
KEYWORD = "雨夜"


class _LogRecorder:
    """记录本模块 logger 的调用（structlog 的 BoundLogger 被 cache_logger_on_first_use 缓存，
    caplog/capture_logs 收不到 ⇒ 直接替换模块级 logger 断言"具名记录"）。"""

    def __init__(self) -> None:
        self.warnings: list[tuple[str, tuple]] = []
        self.debugs: list[tuple[str, tuple]] = []

    def warning(self, event: str, *args: object, **kwargs: object) -> None:
        self.warnings.append((event, args))

    def debug(self, event: str, *args: object, **kwargs: object) -> None:
        self.debugs.append((event, args))


@pytest.fixture(autouse=True)
def _reset_touch_state(monkeypatch):
    """U3：`_touch_throttle_state` / `_touch_skip_count` 是模块全局，逐例重置（失败也能自愈）。"""
    monkeypatch.setattr(memory_field_module, "_touch_throttle_state", {})
    monkeypatch.setattr(memory_field_module, "_touch_skip_count", 0)


@pytest.fixture
def clock(monkeypatch):
    """U2：节流窗在 memory_field 里算，写库时间在 lifecycle_manager 里取 ⇒ 两处打同一个假时钟。"""
    state = {"now": 1000.0}
    fake = SimpleNamespace(time=lambda: state["now"])
    monkeypatch.setattr(memory_field_module, "time", fake)
    monkeypatch.setattr(lifecycle_manager_module, "time", fake)
    return state


def _build_field(tmp_path: Path) -> tuple[MemoryField, Path]:
    field = MemoryField(tmp_path)
    return field, tmp_path / "connectionist.db"


def _seed_episode(db_path: Path, last_accessed_at: float = 1000.0) -> int:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO episodes (agent_id, title, content, fragment_ids, all_concepts,
               status, last_accessed_at, timestamp)
               VALUES (?, ?, ?, '[]', ?, 'active', ?, ?)""",
            (AGENT, KEYWORD, "雨夜里的约定", '["雨夜"]', last_accessed_at, last_accessed_at),
        )
        conn.commit()
        return int(cursor.lastrowid)


def _seed_saga(db_path: Path, last_accessed_at: float = 1000.0) -> int:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO sagas (agent_id, title, description, episode_ids,
               status, last_accessed_at, timestamp)
               VALUES (?, ?, ?, '[]', 'active', ?, ?)""",
            (AGENT, KEYWORD, "雨夜里的长故事", last_accessed_at, last_accessed_at),
        )
        conn.commit()
        return int(cursor.lastrowid)


def _recall(field: MemoryField) -> dict:
    return field.recall_with_intuition(seeds=[], context_text=KEYWORD, agent_id=AGENT)


def _last_accessed(db_path: Path, table: str, row_id: int) -> float:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(f"SELECT last_accessed_at FROM {table} WHERE id=?", (row_id,)).fetchone()
    assert row is not None, f"{table} 第 {row_id} 行不见了"
    return float(row[0])


def _count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_recall_touches_accessed_episode_and_saga(clock, tmp_path) -> None:
    """用例 1：种行（1000）· clock=2000 · 触发 ⇒ 精确 2000。"""
    field, db = _build_field(tmp_path)
    episode_id = _seed_episode(db)
    saga_id = _seed_saga(db)

    clock["now"] = 2000.0
    _recall(field)

    assert _last_accessed(db, "episodes", episode_id) == 2000.0
    assert _last_accessed(db, "sagas", saga_id) == 2000.0
    assert memory_field_module._touch_skip_count == 0


def test_recall_within_window_skips(clock, tmp_path, monkeypatch) -> None:
    """用例 2：clock=2001（窗内）· 再触发 ⇒ 行仍 2000 + `_touch_skip_count` +1（具名 debug）。"""
    field, db = _build_field(tmp_path)
    episode_id = _seed_episode(db)
    saga_id = _seed_saga(db)
    recorder = _LogRecorder()
    monkeypatch.setattr(memory_field_module, "logger", recorder)

    clock["now"] = 2000.0
    _recall(field)
    clock["now"] = 2001.0
    _recall(field)

    assert _last_accessed(db, "episodes", episode_id) == 2000.0
    assert _last_accessed(db, "sagas", saga_id) == 2000.0
    assert memory_field_module._touch_skip_count == 1
    assert len(recorder.debugs) == 1
    event, args = recorder.debugs[0]
    assert "跳过" in event
    assert AGENT in args and "tier" in args


def test_recall_after_window_touches_again(clock, tmp_path) -> None:
    """用例 3：窗外再触发 ⇒ 精确新时间戳（B7 再 +1）。

    ⚠️ 规格 §3 写的 clock=5000 与 B3 的 3600s 窗**算术矛盾**（5000-2000=3000 < 3600 ⇒ 仍在窗内）；
    机械门钉死 `_TOUCH_THROTTLE_SECONDS = 3600` ⇒ 这里取窗边界 5600（= 2000+3600，`<` 严格比较）。
    """
    field, db = _build_field(tmp_path)
    episode_id = _seed_episode(db)
    saga_id = _seed_saga(db)

    clock["now"] = 2000.0
    _recall(field)
    clock["now"] = 5600.0
    _recall(field)

    assert _last_accessed(db, "episodes", episode_id) == 5600.0
    assert _last_accessed(db, "sagas", saga_id) == 5600.0
    assert memory_field_module._touch_skip_count == 0


def test_missing_target_rows_are_not_created(clock, tmp_path) -> None:
    """用例 4（C6 反面）：不种行 ⇒ 触发 ⇒ 库里没多出 episode/saga 行、无异常。"""
    field, db = _build_field(tmp_path)

    clock["now"] = 2000.0
    result = _recall(field)

    assert _count(db, "episodes") == 0
    assert _count(db, "sagas") == 0
    assert result["intuition"]["triggered_episodes"] == []
    assert result["intuition"]["triggered_sagas"] == []
    # no-op 不占窗：什么都没命中时不该消耗节流窗
    assert memory_field_module._touch_throttle_state == {}


def test_touch_failure_keeps_recall_payload(tmp_path, monkeypatch) -> None:
    """用例 5（C2 反面）：touch_* 抛 ⇒ recall 载荷本体不变 + 双通道具名记录。"""
    from src.core.error_escalation_port_registry import (
        reset_error_escalation_port,
        set_error_escalation_port,
    )

    field, db = _build_field(tmp_path)
    episode_id = _seed_episode(db)
    _seed_saga(db)
    recorder = _LogRecorder()
    monkeypatch.setattr(memory_field_module, "logger", recorder)

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(field._episode_store, "update_episode_last_accessed", _boom)

    reported: list[tuple[tuple, dict]] = []
    port = SimpleNamespace(report=lambda *args, **kwargs: reported.append((args, kwargs)))
    set_error_escalation_port(port)
    try:
        result = _recall(field)
    finally:
        reset_error_escalation_port()

    # 载荷本体（断言内容，不是"没抛异常"）
    assert "recall_items" in result
    triggered = result["intuition"]["triggered_episodes"]
    assert [episode["id"] for episode in triggered] == [episode_id]
    assert triggered[0]["title"] == KEYWORD
    assert triggered[0]["content"] == "雨夜里的约定"

    # 双通道：日志 + escalation port，且具名（agent / 原因）
    assert len(recorder.warnings) == 1
    event, args = recorder.warnings[0]
    assert "续命失败" in event
    assert AGENT in args and "database is locked" in str(args)
    assert len(reported) == 1
    report_args, report_kwargs = reported[0]
    assert report_args[1] == "记忆 tier 续命失败"
    assert isinstance(report_kwargs["exception"], RuntimeError)
    # 失败不占窗：下次访问还要重试
    assert memory_field_module._touch_throttle_state == {}
