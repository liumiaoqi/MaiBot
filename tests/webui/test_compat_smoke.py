"""T2.2 compat_router 冒烟测试 — R4 缓解

覆盖 compat_router 50+ 端点，验证至少返回 200 或合理 4xx（不出现 500/AttributeError）。
作为 service 下沉 / memory 拆分前后的回归基线。

A_memorix 依赖端点在 T2.3 db_isolation fixture 补全前标记 skip，
非依赖端点（config/agent/chat/query_aggregate/timeline）构成当前基线。
"""

import pytest

from tests.webui.conftest import assert_api_success


_AMEMORIX_REASON = "A_memorix 内核未初始化（配置管理器未注入），待 T2.3 db_isolation fixture 补全"


def _assert_not_500(response, label: str):
    """冒烟核心断言：不允许 500，允许 200/4xx"""
    assert response.status_code != 500, f"[{label}] 500 错误: {response.text}"
    assert "AttributeError" not in response.text, f"[{label}] AttributeError: {response.text}"


class TestCompatMemorySmoke:
    """memory.py compat_router 冒烟（prefix /api，60+ 端点）"""

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_graph_get(self, auth_client):
        r = auth_client.get("/api/graph")
        _assert_not_500(r, "GET /api/graph")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_source_list(self, auth_client):
        r = auth_client.get("/api/source/list")
        _assert_not_500(r, "GET /api/source/list")

    def test_query_aggregate(self, auth_client):
        r = auth_client.get("/api/query/aggregate")
        _assert_not_500(r, "GET /api/query/aggregate")

    def test_timeline(self, auth_client):
        r = auth_client.get("/api/timeline", params={"chat_id": "test"})
        _assert_not_500(r, "GET /api/timeline")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_episodes_list(self, auth_client):
        r = auth_client.get("/api/episodes")
        _assert_not_500(r, "GET /api/episodes")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_episodes_status(self, auth_client):
        r = auth_client.get("/api/episodes/status")
        _assert_not_500(r, "GET /api/episodes/status")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_episode_get_not_found(self, auth_client):
        r = auth_client.get("/api/episodes/nonexistent-episode-id")
        _assert_not_500(r, "GET /api/episodes/{id}")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_person_profile_query(self, auth_client):
        r = auth_client.get("/api/person_profile/query")
        _assert_not_500(r, "GET /api/person_profile/query")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_person_profile_list(self, auth_client):
        r = auth_client.get("/api/person_profile/list")
        _assert_not_500(r, "GET /api/person_profile/list")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_person_profile_search(self, auth_client):
        r = auth_client.get("/api/person_profile/search")
        _assert_not_500(r, "GET /api/person_profile/search")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_runtime_config(self, auth_client):
        r = auth_client.get("/api/config")
        _assert_not_500(r, "GET /api/config")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_runtime_self_check(self, auth_client):
        r = auth_client.get("/api/runtime/self_check")
        _assert_not_500(r, "GET /api/runtime/self_check")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_config_auto_save(self, auth_client):
        r = auth_client.get("/api/config/auto_save")
        _assert_not_500(r, "GET /api/config/auto_save")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_memory_recycle_bin(self, auth_client):
        r = auth_client.get("/api/memory/recycle_bin")
        _assert_not_500(r, "GET /api/memory/recycle_bin")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_import_settings(self, auth_client):
        r = auth_client.get("/api/import/settings")
        _assert_not_500(r, "GET /api/import/settings")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_import_path_aliases(self, auth_client):
        r = auth_client.get("/api/import/path_aliases")
        _assert_not_500(r, "GET /api/import/path_aliases")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_import_guide(self, auth_client):
        r = auth_client.get("/api/import/guide")
        _assert_not_500(r, "GET /api/import/guide")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_import_tasks_list(self, auth_client):
        r = auth_client.get("/api/import/tasks")
        _assert_not_500(r, "GET /api/import/tasks")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_import_task_get_not_found(self, auth_client):
        r = auth_client.get("/api/import/tasks/nonexistent-task-id")
        _assert_not_500(r, "GET /api/import/tasks/{id}")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_import_task_chunks_not_found(self, auth_client):
        r = auth_client.get("/api/import/tasks/nonexistent/chunks/nonexistent")
        _assert_not_500(r, "GET /api/import/tasks/{id}/chunks/{fid}")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_import_file_chunks_not_found(self, auth_client):
        r = auth_client.get("/api/import/tasks/nonexistent/files/nonexistent/chunks")
        _assert_not_500(r, "GET /api/import/tasks/{id}/files/{fid}/chunks")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_retrieval_tuning_settings(self, auth_client):
        r = auth_client.get("/api/retrieval_tuning/settings")
        _assert_not_500(r, "GET /api/retrieval_tuning/settings")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_retrieval_tuning_profile(self, auth_client):
        r = auth_client.get("/api/retrieval_tuning/profile")
        _assert_not_500(r, "GET /api/retrieval_tuning/profile")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_retrieval_tuning_profile_export(self, auth_client):
        r = auth_client.get("/api/retrieval_tuning/profile/export")
        _assert_not_500(r, "GET /api/retrieval_tuning/profile/export")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_retrieval_tuning_profile_export_toml(self, auth_client):
        r = auth_client.get("/api/retrieval_tuning/profile/export_toml")
        _assert_not_500(r, "GET /api/retrieval_tuning/profile/export_toml")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_retrieval_tuning_tasks_list(self, auth_client):
        r = auth_client.get("/api/retrieval_tuning/tasks")
        _assert_not_500(r, "GET /api/retrieval_tuning/tasks")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_retrieval_tuning_task_get_not_found(self, auth_client):
        r = auth_client.get("/api/retrieval_tuning/tasks/nonexistent-task-id")
        _assert_not_500(r, "GET /api/retrieval_tuning/tasks/{id}")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_retrieval_tuning_rounds_not_found(self, auth_client):
        r = auth_client.get("/api/retrieval_tuning/tasks/nonexistent/rounds")
        _assert_not_500(r, "GET /api/retrieval_tuning/tasks/{id}/rounds")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_retrieval_tuning_report_not_found(self, auth_client):
        r = auth_client.get("/api/retrieval_tuning/tasks/nonexistent/report")
        _assert_not_500(r, "GET /api/retrieval_tuning/tasks/{id}/report")


class TestCompatMemoryPostSmoke:
    """memory.py compat_router POST 端点冒烟（空 payload，期望 200 或 4xx）"""

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_import_paste(self, auth_client):
        r = auth_client.post("/api/import/paste", json={})
        _assert_not_500(r, "POST /api/import/paste")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_import_tasks_paste(self, auth_client):
        r = auth_client.post("/api/import/tasks/paste", json={})
        _assert_not_500(r, "POST /api/import/tasks/paste")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_import_raw_scan(self, auth_client):
        r = auth_client.post("/api/import/raw_scan", json={})
        _assert_not_500(r, "POST /api/import/raw_scan")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_import_tasks_raw_scan(self, auth_client):
        r = auth_client.post("/api/import/tasks/raw_scan", json={})
        _assert_not_500(r, "POST /api/import/tasks/raw_scan")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_import_resolve_path(self, auth_client):
        r = auth_client.post("/api/import/resolve_path", json={})
        _assert_not_500(r, "POST /api/import/resolve_path")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_import_task_cancel_not_found(self, auth_client):
        r = auth_client.post("/api/import/tasks/nonexistent/cancel")
        _assert_not_500(r, "POST /api/import/tasks/{id}/cancel")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_retrieval_tuning_rollback(self, auth_client):
        r = auth_client.post("/api/retrieval_tuning/profile/rollback")
        _assert_not_500(r, "POST /api/retrieval_tuning/profile/rollback")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_retrieval_tuning_create_task(self, auth_client):
        r = auth_client.post("/api/retrieval_tuning/tasks", json={})
        _assert_not_500(r, "POST /api/retrieval_tuning/tasks")

    @pytest.mark.skip(reason=_AMEMORIX_REASON)
    def test_retrieval_tuning_cancel_not_found(self, auth_client):
        r = auth_client.post("/api/retrieval_tuning/tasks/nonexistent/cancel")
        _assert_not_500(r, "POST /api/retrieval_tuning/tasks/{id}/cancel")


class TestCompatConfigSmoke:
    """config.py compat_router 冒烟（prefix /api/config，4 端点）"""

    def test_config_schema(self, auth_client):
        r = auth_client.get("/api/config/schema")
        _assert_not_500(r, "GET /api/config/schema")

    def test_config_schema_bot(self, auth_client):
        r = auth_client.get("/api/config/schema/bot")
        _assert_not_500(r, "GET /api/config/schema/bot")

    def test_config_raw_get(self, auth_client):
        r = auth_client.get("/api/config/raw")
        _assert_not_500(r, "GET /api/config/raw")


class TestCompatAgentSmoke:
    """agent.py compat_router 冒烟（prefix /api/webui，/agents→/agent 别名）"""

    def test_agent_list_compat(self, auth_client):
        r = auth_client.get("/api/webui/agent")
        _assert_not_500(r, "GET /api/webui/agent")


class TestCompatChatSmoke:
    """chat/routes.py compat_router 冒烟（/api/webui/chat→/api/chat 别名）"""

    def test_chat_sessions_compat(self, auth_client):
        r = auth_client.get("/api/chat/sessions")
        _assert_not_500(r, "GET /api/chat/sessions")
