"""T2.5 memory 写测试 — delete/execute/restore 端点覆盖

依赖 db_isolation fixture。A_memorix 依赖端点标记 skip，待 A_memorix 初始化方案就绪。
"""

import pytest

_AMEMORIX_REASON = "A_memorix 内核未初始化（配置管理器未注入），待 A_memorix 初始化方案就绪"


class TestMemoryWrite:
    """memory 写端点测试"""

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_delete_episode(self, auth_client, db_isolation):
        """POST /memory/episodes/{id}/delete — 删除 episode（T4 改名后路径）"""
        r = auth_client.post("/api/memory/episodes/test-episode-id/delete", json={
            "mode": "single",
            "selector": "test-episode-id",
        })
        assert r.status_code != 500, f"500 错误: {r.text}"

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_restore_memory(self, auth_client, db_isolation):
        """POST /memory/memory/restore — 恢复记忆"""
        r = auth_client.post("/api/memory/memory/restore", json={
            "target_ids": ["test-memory-id"],
        })
        assert r.status_code != 500, f"500 错误: {r.text}"

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_purge_maintenance(self, auth_client, db_isolation):
        """POST /memory/maintenance/purge — 清理维护（T4 改名后路径）"""
        r = auth_client.post("/api/memory/maintenance/purge", json={
            "cascade": True,
        })
        assert r.status_code != 500, f"500 错误: {r.text}"

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_reinforce_memory(self, auth_client, db_isolation):
        """POST /memory/memory/reinforce — 强化记忆"""
        r = auth_client.post("/api/memory/memory/reinforce", json={
            "target_ids": ["test-memory-id"],
        })
        assert r.status_code != 500, f"500 错误: {r.text}"

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_freeze_memory(self, auth_client, db_isolation):
        """POST /memory/memory/freeze — 冻结记忆"""
        r = auth_client.post("/api/memory/memory/freeze", json={
            "target_ids": ["test-memory-id"],
        })
        assert r.status_code != 500, f"500 错误: {r.text}"

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_protect_memory(self, auth_client, db_isolation):
        """POST /memory/memory/protect — 保护记忆"""
        r = auth_client.post("/api/memory/memory/protect", json={
            "target_ids": ["test-memory-id"],
        })
        assert r.status_code != 500, f"500 错误: {r.text}"