"""0004 真值回路（`record_relation_feedback`）· 全在**临时数据根**上跑。

⚠️ 红线（照 `tests/unit/a_memorix/test_social_rel_confidence_seam.py:13` 的既有口径）：
   用例**只往 tmp 数据根写**（`MAIBOT_DATA_DIR=<tmp>`，进程内 `monkeypatch.setenv`），
   **从不碰真数据根**、更不碰真库。真库侧只做**只读**基线（见本件回报里的两个数）。

⚠️ **一条口径必须分清**（不然会写成"永远测不了"的断言）：
   · **临时新库**：`MetadataStore.connect()` 会**一次性建全表** ⇒ `relation_feedback_events`
     **一开始就在** ⇒ 所以这里断言的是 **行数 `0 → 1`**，⛔ **不是"表从无到有"**。
   · **真库**那张表至今不存在，成因是**存量库**（`v5_memory.py:151`："存量库拿不到建库时的 DDL
     （`_create_all_tables` 只在新建库跑）⇒ 这里用到时确保存在"）—— 那是**现场事实**，
     而且**我们不许写真库** ⇒ 它**不能**当断言，只能当只读基线。
"""

from pathlib import Path

import pytest

from src.A_memorix.core.runtime.services.v5_memory import V5MemoryService
from src.A_memorix.core.storage.metadata_store import MetadataStore

LEDGER = "relation_feedback_events"
OPS = "memory_v5_operations"


@pytest.fixture()
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """只把数据根指到 tmp（进程结束即失）—— 照既有先例的红线口径。"""

    monkeypatch.setenv("MAIBOT_DATA_DIR", str(tmp_path))
    yield tmp_path


def _store(data_root: Path) -> MetadataStore:
    store = MetadataStore(data_dir=data_root / "metadata")
    store.connect()
    return store


def _service(store: MetadataStore) -> V5MemoryService:
    """九个依赖全用最小 lambda/stub 顶掉（均为关键字参数，无默认值）。"""

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


def _count(store: MetadataStore, table: str) -> int:
    return int(store.get_connection().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_ledger_row_appears_on_feedback(data_root: Path) -> None:
    """(乙) 第一条：账本**行数 0 → 1**（表本来就在 ⇒ 不断"表从无到有"，见模块 docstring）。"""

    store = _store(data_root)
    assert store.has_table(LEDGER), "临时新库里账本表应当已由 connect() 建出"

    before = _count(store, LEDGER)
    _service(store).record_relation_feedback(relation_hash="h-1", action="lower", actor="tester")
    after = _count(store, LEDGER)

    assert before == 0, f"临时新库的账本一开始应当是空的，实际 {before}"
    assert after == 1, f"一次显式动作应当恰好留一行账，实际 {after}"


def test_ledger_records_actor_and_note(data_root: Path) -> None:
    """(乙) 补：账本行里**能读出"谁按的按钮 + 备注"**（否则"留痕"只是行数好看）。"""

    store = _store(data_root)
    _service(store).record_relation_feedback(
        relation_hash="h-2", action="neutral", actor="刘妙奇", source_note="今晚聊得好"
    )

    row = store.get_connection().execute(
        f"SELECT relation_hash, actor, source_note FROM {LEDGER}"
    ).fetchone()

    assert row is not None, "动作之后账本里应当有一行"
    assert row[0] == "h-2", row
    assert row[1] == "刘妙奇", row
    assert row[2] == "今晚聊得好", row


def test_zero_matched_rows_is_currently_silent_and_should_flip(data_root: Path) -> None:
    """⚠️ **会翻的用例**（定时炸弹形态）：**零行匹配时现状是静默**。

    `adjust_relation_confidence`（`v5_memory.py:92-112`）全文**没有 `rowcount` 检查**、
    **没有"0 行受影响"的记号**、**没有拒绝** ⇒ `commit()` 照做、照样返回 ⇒
    调用方以为改了，系统里**一行都没变**（`#50` 族："没变却像成了"）。
    而 `record_relation_feedback` 读回时又把**不存在的行**静默当成 `0.0`（`v5_memory.py:149`）
    ⇒ **写静默 + 读静默** ⇒ 于是"原本就是 0"与"什么都没发生"**分辨不出来**。

    **期望行为：必须能分辨**（拒绝，或明确报"0 行受影响"）。
    ⇒ **本条在修好后应当翻**（那时下面的断言会红，提醒把它改成"必须能分辨"）。
    """

    store = _store(data_root)
    # 故意**不种种子行** —— 先撞静默、把现状钉在用例里（⛔ 不用种子行把症状盖掉）。
    assert _count(store, "relations") == 0, "本用例的前提是关系表为空（不种种子）"

    result = _service(store).record_relation_feedback(relation_hash="h-absent", action="lower")

    # 现状：不抛、不拒 —— 且没有任何"0 行受影响"的记号可从返回里分辨出来。
    assert isinstance(result, dict), result
    assert _count(store, "relations") == 0, "零行匹配时关系表当然还是空的（这行是现状快照）"
    assert result.get("success") is not False, (
        "⚠️ 现状：零行匹配并未被判为失败。"
        "**这是现状快照、不是期望** —— 期望是必须能分辨（拒绝或明确报 0 行受影响），"
        "修好后本断言应当翻。"
    )
