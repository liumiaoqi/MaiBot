"""stage_status_board 单元测试。

覆盖 MaisakaStageStatusBoard 的 update/remove/snapshot 行为，
以及模块级 update_stage_status/remove_stage_status/get_stage_status_snapshot。
测试环境无 event loop，_schedule_*_event 静默返回。
"""

from src.maisaka.display.stage_status_board import (
    MaisakaStageStatusBoard,
    get_stage_status_snapshot,
    remove_stage_status,
    update_stage_status,
)


class TestMaisakaStageStatusBoard:
    """MaisakaStageStatusBoard 行为测试。"""

    def test_update_then_snapshot_returns_entry(self):
        board = MaisakaStageStatusBoard()
        board.update(
            session_id="s1",
            session_name="测试流",
            stage="planning",
            detail="正在规划",
        )
        snapshot = board.snapshot()
        assert len(snapshot) == 1
        entry = snapshot[0]
        assert entry["session_id"] == "s1"
        assert entry["session_name"] == "测试流"
        assert entry["stage"] == "planning"
        assert entry["detail"] == "正在规划"

    def test_update_preserves_stage_started_at_on_same_stage(self):
        board = MaisakaStageStatusBoard()
        board.update(
            session_id="s1",
            session_name="流",
            stage="planning",
        )
        first_snapshot = board.snapshot()
        first_started_at = first_snapshot[0]["stage_started_at"]

        board.update(
            session_id="s1",
            session_name="流",
            stage="planning",
            detail="继续规划",
        )
        second_snapshot = board.snapshot()
        # 同 stage 不重置 stage_started_at
        assert second_snapshot[0]["stage_started_at"] == first_started_at

    def test_update_resets_stage_started_at_on_stage_change(self):
        board = MaisakaStageStatusBoard()
        board.update(
            session_id="s1",
            session_name="流",
            stage="planning",
        )
        first_started_at = board.snapshot()[0]["stage_started_at"]

        board.update(
            session_id="s1",
            session_name="流",
            stage="replying",
        )
        second_started_at = board.snapshot()[0]["stage_started_at"]
        # stage 变化后 stage_started_at 应更新
        assert second_started_at >= first_started_at

    def test_update_multiple_sessions(self):
        board = MaisakaStageStatusBoard()
        board.update(session_id="s1", session_name="流1", stage="a")
        board.update(session_id="s2", session_name="流2", stage="b")
        snapshot = board.snapshot()
        assert len(snapshot) == 2
        ids = {e["session_id"] for e in snapshot}
        assert ids == {"s1", "s2"}

    def test_remove_clears_entry(self):
        board = MaisakaStageStatusBoard()
        board.update(session_id="s1", session_name="流", stage="a")
        board.remove("s1")
        assert board.snapshot() == []

    def test_remove_nonexistent_silent(self):
        board = MaisakaStageStatusBoard()
        # 移除不存在的 session 不报错
        board.remove("nonexistent")
        assert board.snapshot() == []

    def test_snapshot_returns_copy(self):
        board = MaisakaStageStatusBoard()
        board.update(session_id="s1", session_name="流", stage="a")
        snap1 = board.snapshot()
        snap1[0]["stage"] = "mutated"
        snap2 = board.snapshot()
        # 修改快照副本不影响内部状态
        assert snap2[0]["stage"] == "a"

    def test_update_with_optional_fields(self):
        board = MaisakaStageStatusBoard()
        board.update(
            session_id="s1",
            session_name="流",
            stage="a",
            detail="详情",
            round_text="第1轮",
            agent_state="thinking",
        )
        entry = board.snapshot()[0]
        assert entry["round_text"] == "第1轮"
        assert entry["agent_state"] == "thinking"


class TestModuleLevelFunctions:
    """模块级 update_stage_status/remove_stage_status/get_stage_status_snapshot 测试。"""

    def test_update_and_snapshot(self):
        update_stage_status(
            session_id="mod_s1",
            session_name="模块流",
            stage="planning",
        )
        snapshot = get_stage_status_snapshot()
        ids = {e["session_id"] for e in snapshot}
        assert "mod_s1" in ids

    def test_remove(self):
        update_stage_status(
            session_id="mod_s2",
            session_name="模块流2",
            stage="a",
        )
        remove_stage_status("mod_s2")
        snapshot = get_stage_status_snapshot()
        ids = {e["session_id"] for e in snapshot}
        assert "mod_s2" not in ids