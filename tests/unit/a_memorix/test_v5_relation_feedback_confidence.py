"""0004 真值回路 · **真数**（`confidence` 真的 ±0.1）与留痕（`memory_v5_operations` 0 → ≥1）。

红线与口径同 `test_v5_relation_feedback_db.py`：
· **只往 tmp 数据根写**（进程内 `monkeypatch.setenv("MAIBOT_DATA_DIR", …)`），**从不碰真库**；
· **临时新库**里表由 `connect()` 一次性建出；真库侧只做**只读**基线。

⚠️ **(甲) 为什么必须"先 lower 再 raise"**：`confidence` 有 `[0,1]` 夹紧
（`v5_memory.py:105` `MIN(1.0, MAX(0.0, …))`）⇒ 若种子取 `1.0`，`raise` 会**纹丝不动**，
于是用例会**误判成"没生效"**。这里种子取 `0.5` 且走向 `lower → raise` ⇒ 两个方向都真动、且都读得出。
⛔ 并**避开 `neutral`**：它 `delta=0`（`v5_memory.py:143 if delta:`）⇒ 只留痕、不动值，
拿它验"动没动"必然误判。
"""

from pathlib import Path

import pytest

from src.A_memorix.core.runtime.services.v5_memory import V5MemoryService
from src.A_memorix.core.storage.metadata_store import MetadataStore

LEDGER = "relation_feedback_events"
OPS = "memory_v5_operations"
DELTA = 0.1


@pytest.fixture()
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MAIBOT_DATA_DIR", str(tmp_path))
    yield tmp_path


def _store(data_root: Path) -> MetadataStore:
    store = MetadataStore(data_dir=data_root / "metadata")
    store.connect()
    return store


def _service(store: MetadataStore) -> V5MemoryService:
    return V5MemoryService(
        metadata_store=store,
        cfg=lambda key, default: default,
        resolve_relation_hashes=lambda target: [target] if target else [],
        resolve_deleted_relation_hashes=lambda target: [],
        rebuild_graph_from_metadata=lambda: {},
        persist_callback=lambda: None,
        last_maintenance_at_getter=lambda: None,
        last_maintenance_at_setter=lambda value: None,
    )


def _confidence(store: MetadataStore, hash_value: str) -> float:
    row = store.get_connection().execute(
        "SELECT confidence FROM relations WHERE hash = ?", (hash_value,)
    ).fetchone()
    return float(row[0])


def _count(store: MetadataStore, table: str) -> int:
    return int(store.get_connection().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_lower_then_raise_moves_confidence_by_delta(data_root: Path) -> None:
    """(甲) 真数：**一次 lower ⇒ −0.1 · 再一次 raise ⇒ +0.1**（避开 nan/夹紧造成的假"没生效"）。"""

    store = _store(data_root)
    conn = store.get_connection()
    # 种子行：`hash` + `confidence` 两列即可（其余列可空；UPDATE 里还有 COALESCE 兜底）
    # ⚠️ 此处**复刻了 schema**（`relations.subject` 是 NOT NULL）—— schema 变则需同步；
    # 若改用 store 的写入口（`metadata_store.add_relation`）可免此漂移。
    conn.execute(
        "INSERT INTO relations (hash, subject, predicate, object, confidence) VALUES (?, ?, ?, ?, ?)",
        ("h-a", "刘妙奇", "喜欢", "游戏", 0.5),
    )
    conn.commit()

    service = _service(store)

    service.record_relation_feedback(relation_hash="h-a", action="lower", actor="tester")
    after_lower = _confidence(store, "h-a")

    service.record_relation_feedback(relation_hash="h-a", action="raise", actor="tester")
    after_raise = _confidence(store, "h-a")

    assert after_lower == pytest.approx(0.5 - DELTA), f"lower 之后应 -0.1，实际 {after_lower}"
    assert after_raise == pytest.approx(0.5), f"再 raise 之后应回到 0.5，实际 {after_raise}"
    # 账本：两次动作 ⇒ 两行（neutral 一次都不算，因为本用例没用它）
    assert _count(store, LEDGER) == 2, "两次显式动作应当留两行账"


def test_neutral_leaves_confidence_untouched_but_still_logs(data_root: Path) -> None:
    """`neutral` 的性质：**只留痕、不动值**（`v5_memory.py:143 if delta:`）—— 这是 (甲) 要避开它的原因。"""

    store = _store(data_root)
    conn = store.get_connection()
    # ⚠️ 此处**复刻了 schema**（`relations.subject` 是 NOT NULL）—— schema 变则需同步；
    # 若改用 store 的写入口（`metadata_store.add_relation`）可免此漂移。
    conn.execute(
        "INSERT INTO relations (hash, subject, predicate, object, confidence) VALUES (?, ?, ?, ?, ?)",
        ("h-n", "刘妙奇", "喜欢", "游戏", 0.5),
    )
    conn.commit()

    _service(store).record_relation_feedback(relation_hash="h-n", action="neutral", actor="tester")

    assert _confidence(store, "h-n") == pytest.approx(0.5), "neutral 不该动 confidence"
    assert _count(store, LEDGER) == 1, "neutral 仍应留一行账"


def test_operation_ledger_goes_from_zero_to_one(data_root: Path) -> None:
    """(乙) 第二条：**`memory_v5_operations` 0 → ≥1**（这条正是前半那个 action 分支的留痕落点）。"""

    store = _store(data_root)
    assert _count(store, OPS) == 0, "临时新库里操作账本一开始应当是空的"

    store.record_v5_operation(
        action="relation_feedback",
        target="h-a",
        resolved_hashes=["h-a"],  # ⚠️ 必填形参（metadata_store.py:1311，无默认）
        result={"success": True},
    )

    assert _count(store, OPS) == 1, "一次动作应当在操作账本里留一行"
