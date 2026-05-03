from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.services.memory_service import MemorySearchResult
from src.webui.dependencies import require_auth
from src.webui.routers import memory as memory_router_module
from src.webui.routers.memory import compat_router
from src.webui.routes import router as main_router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.dependency_overrides[require_auth] = lambda: "ok"
    app.include_router(main_router)
    app.include_router(compat_router)
    return TestClient(app)


def test_webui_memory_graph_route(client: TestClient, monkeypatch):
    async def fake_graph_admin(*, action: str, **kwargs):
        assert action == "get_graph"
        return {
            "success": True,
            "nodes": [],
            "edges": [
                {
                    "source": "alice",
                    "target": "map",
                    "weight": 1.5,
                    "relation_hashes": ["rel-1"],
                    "predicates": ["持有"],
                    "relation_count": 1,
                    "evidence_count": 2,
                    "label": "持有",
                }
            ],
            "total_nodes": 0,
            "limit": kwargs.get("limit"),
        }

    monkeypatch.setattr(memory_router_module.memory_service, "graph_admin", fake_graph_admin)

    response = client.get("/api/webui/memory/graph", params={"limit": 77})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["limit"] == 77
    assert response.json()["edges"][0]["predicates"] == ["持有"]
    assert response.json()["edges"][0]["relation_count"] == 1
    assert response.json()["edges"][0]["evidence_count"] == 2


def test_webui_memory_graph_search_route(client: TestClient, monkeypatch):
    async def fake_graph_admin(*, action: str, **kwargs):
        assert action == "search"
        assert kwargs["query"] == "Alice"
        assert kwargs["limit"] == 33
        return {
            "success": True,
            "query": kwargs["query"],
            "limit": kwargs["limit"],
            "count": 1,
            "items": [
                {
                    "type": "entity",
                    "title": "Alice",
                    "matched_field": "name",
                    "matched_value": "Alice",
                    "entity_name": "Alice",
                    "entity_hash": "entity-1",
                    "appearance_count": 3,
                }
            ],
        }

    monkeypatch.setattr(memory_router_module.memory_service, "graph_admin", fake_graph_admin)

    response = client.get("/api/webui/memory/graph/search", params={"query": "Alice", "limit": 33})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["query"] == "Alice"
    assert response.json()["limit"] == 33
    assert response.json()["items"][0]["type"] == "entity"


@pytest.mark.parametrize(
    "params",
    [
        {"query": "", "limit": 50},
        {"query": "Alice", "limit": 0},
        {"query": "Alice", "limit": 201},
    ],
)
def test_webui_memory_graph_search_route_validation(client: TestClient, params):
    response = client.get("/api/webui/memory/graph/search", params=params)

    assert response.status_code == 422


def test_webui_memory_graph_node_detail_route(client: TestClient, monkeypatch):
    async def fake_graph_admin(*, action: str, **kwargs):
        assert action == "node_detail"
        assert kwargs["node_id"] == "Alice"
        return {
            "success": True,
            "node": {"id": "Alice", "type": "entity", "content": "Alice", "appearance_count": 3},
            "relations": [{"hash": "rel-1", "subject": "Alice", "predicate": "持有", "object": "Map", "text": "Alice 持有 Map", "confidence": 0.9, "paragraph_count": 1, "paragraph_hashes": ["p-1"], "source_paragraph": "p-1"}],
            "paragraphs": [{"hash": "p-1", "content": "Alice 拿着地图。", "preview": "Alice 拿着地图。", "source": "demo", "entity_count": 2, "relation_count": 1, "entities": ["Alice", "Map"], "relations": ["Alice 持有 Map"]}],
            "evidence_graph": {
                "nodes": [{"id": "entity:Alice", "type": "entity", "content": "Alice"}],
                "edges": [],
                "focus_entities": ["Alice"],
            },
        }

    monkeypatch.setattr(memory_router_module.memory_service, "graph_admin", fake_graph_admin)

    response = client.get("/api/webui/memory/graph/node-detail", params={"node_id": "Alice"})

    assert response.status_code == 200
    assert response.json()["node"]["id"] == "Alice"
    assert response.json()["relations"][0]["predicate"] == "持有"
    assert response.json()["evidence_graph"]["focus_entities"] == ["Alice"]


def test_webui_memory_graph_node_detail_route_returns_404(client: TestClient, monkeypatch):
    async def fake_graph_admin(*, action: str, **kwargs):
        assert action == "node_detail"
        return {"success": False, "error": "未找到节点: Missing"}

    monkeypatch.setattr(memory_router_module.memory_service, "graph_admin", fake_graph_admin)

    response = client.get("/api/webui/memory/graph/node-detail", params={"node_id": "Missing"})

    assert response.status_code == 404
    assert response.json()["detail"] == "未找到节点: Missing"


def test_webui_memory_graph_edge_detail_route(client: TestClient, monkeypatch):
    async def fake_graph_admin(*, action: str, **kwargs):
        assert action == "edge_detail"
        assert kwargs["source"] == "Alice"
        assert kwargs["target"] == "Map"
        return {
            "success": True,
            "edge": {
                "source": "Alice",
                "target": "Map",
                "weight": 1.5,
                "relation_hashes": ["rel-1"],
                "predicates": ["持有"],
                "relation_count": 1,
                "evidence_count": 1,
                "label": "持有",
            },
            "relations": [{"hash": "rel-1", "subject": "Alice", "predicate": "持有", "object": "Map", "text": "Alice 持有 Map", "confidence": 0.9, "paragraph_count": 1, "paragraph_hashes": ["p-1"], "source_paragraph": "p-1"}],
            "paragraphs": [{"hash": "p-1", "content": "Alice 拿着地图。", "preview": "Alice 拿着地图。", "source": "demo", "entity_count": 2, "relation_count": 1, "entities": ["Alice", "Map"], "relations": ["Alice 持有 Map"]}],
            "evidence_graph": {
                "nodes": [{"id": "relation:rel-1", "type": "relation", "content": "Alice 持有 Map"}],
                "edges": [{"source": "paragraph:p-1", "target": "relation:rel-1", "kind": "supports", "label": "支撑", "weight": 1.0}],
                "focus_entities": ["Alice", "Map"],
            },
        }

    monkeypatch.setattr(memory_router_module.memory_service, "graph_admin", fake_graph_admin)

    response = client.get("/api/webui/memory/graph/edge-detail", params={"source": "Alice", "target": "Map"})

    assert response.status_code == 200
    assert response.json()["edge"]["predicates"] == ["持有"]
    assert response.json()["paragraphs"][0]["source"] == "demo"
    assert response.json()["evidence_graph"]["edges"][0]["kind"] == "supports"


def test_webui_memory_graph_edge_detail_route_returns_404(client: TestClient, monkeypatch):
    async def fake_graph_admin(*, action: str, **kwargs):
        assert action == "edge_detail"
        return {"success": False, "error": "未找到边: Alice -> Missing"}

    monkeypatch.setattr(memory_router_module.memory_service, "graph_admin", fake_graph_admin)

    response = client.get("/api/webui/memory/graph/edge-detail", params={"source": "Alice", "target": "Missing"})

    assert response.status_code == 404
    assert response.json()["detail"] == "未找到边: Alice -> Missing"


def test_compat_aggregate_route(client: TestClient, monkeypatch):
    async def fake_search(query: str, **kwargs):
        assert kwargs["mode"] == "aggregate"
        assert kwargs["respect_filter"] is False
        return MemorySearchResult(summary=f"summary:{query}", hits=[])

    monkeypatch.setattr(memory_router_module.memory_service, "search", fake_search)

    response = client.get("/api/query/aggregate", params={"query": "mai"})

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "summary": "summary:mai",
        "hits": [],
        "filtered": False,
        "error": "",
    }


def test_auto_save_routes(client: TestClient, monkeypatch):
    async def fake_runtime_admin(*, action: str, **kwargs):
        if action == "get_config":
            return {"success": True, "auto_save": True}
        if action == "set_auto_save":
            return {"success": True, "auto_save": kwargs["enabled"]}
        raise AssertionError(action)

    monkeypatch.setattr(memory_router_module.memory_service, "runtime_admin", fake_runtime_admin)

    get_response = client.get("/api/config/auto_save")
    post_response = client.post("/api/config/auto_save", json={"enabled": False})

    assert get_response.status_code == 200
    assert get_response.json() == {"success": True, "auto_save": True}
    assert post_response.status_code == 200
    assert post_response.json() == {"success": True, "auto_save": False}


def test_memory_config_routes(client: TestClient, monkeypatch):
    monkeypatch.setattr(
        memory_router_module.a_memorix_host_service,
        "get_config_schema",
        lambda: {"layout": {"type": "tabs"}, "sections": {"plugin": {"fields": {}}}},
    )
    monkeypatch.setattr(
        memory_router_module.a_memorix_host_service,
        "get_config_path",
        lambda: memory_router_module.Path("/tmp/config/bot_config.toml"),
    )
    monkeypatch.setattr(
        memory_router_module.a_memorix_host_service,
        "get_config",
        lambda: {"plugin": {"enabled": True}},
    )
    monkeypatch.setattr(
        memory_router_module.a_memorix_host_service,
        "get_raw_config",
        lambda: "[plugin]\nenabled = true\n",
    )
    monkeypatch.setattr(
        memory_router_module.a_memorix_host_service,
        "get_raw_config_with_meta",
        lambda: {
            "config": "[plugin]\nenabled = true\n",
            "exists": True,
            "using_default": False,
        },
    )

    schema_response = client.get("/api/webui/memory/config/schema")
    config_response = client.get("/api/webui/memory/config")
    raw_response = client.get("/api/webui/memory/config/raw")
    expected_path = memory_router_module.Path("/tmp/config/bot_config.toml").as_posix()

    assert schema_response.status_code == 200
    assert memory_router_module.Path(schema_response.json()["path"]).as_posix() == expected_path
    assert schema_response.json()["schema"]["layout"]["type"] == "tabs"

    assert config_response.status_code == 200
    assert config_response.json()["success"] is True
    assert config_response.json()["config"] == {"plugin": {"enabled": True}}
    assert memory_router_module.Path(config_response.json()["path"]).as_posix() == expected_path

    assert raw_response.status_code == 200
    assert raw_response.json()["success"] is True
    assert raw_response.json()["config"] == "[plugin]\nenabled = true\n"
    assert memory_router_module.Path(raw_response.json()["path"]).as_posix() == expected_path


def test_memory_config_raw_returns_default_template_when_file_missing(client: TestClient, monkeypatch):
    monkeypatch.setattr(
        memory_router_module.a_memorix_host_service,
        "get_config_path",
        lambda: memory_router_module.Path("/tmp/config/bot_config.toml"),
    )
    monkeypatch.setattr(
        memory_router_module.a_memorix_host_service,
        "get_raw_config_with_meta",
        lambda: {
            "config": "[plugin]\nenabled = true\n",
            "exists": False,
            "using_default": True,
        },
    )

    response = client.get("/api/webui/memory/config/raw")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["config"] == "[plugin]\nenabled = true\n"
    assert response.json()["exists"] is False
    assert response.json()["using_default"] is True


def test_memory_config_update_routes(client: TestClient, monkeypatch):
    async def fake_update_config(config):
        assert config == {"plugin": {"enabled": False}}
        return {"success": True, "config_path": "config/bot_config.toml"}

    async def fake_update_raw(raw_config):
        assert raw_config == "[plugin]\nenabled = false\n"
        return {"success": True, "config_path": "config/bot_config.toml"}

    monkeypatch.setattr(memory_router_module.a_memorix_host_service, "update_config", fake_update_config)
    monkeypatch.setattr(memory_router_module.a_memorix_host_service, "update_raw_config", fake_update_raw)

    config_response = client.put("/api/webui/memory/config", json={"config": {"plugin": {"enabled": False}}})
    raw_response = client.put("/api/webui/memory/config/raw", json={"config": "[plugin]\nenabled = false\n"})

    assert config_response.status_code == 200
    assert config_response.json() == {"success": True, "config_path": "config/bot_config.toml"}

    assert raw_response.status_code == 200
    assert raw_response.json() == {"success": True, "config_path": "config/bot_config.toml"}


def test_memory_config_raw_rejects_invalid_toml(client: TestClient):
    response = client.put("/api/webui/memory/config/raw", json={"config": "[plugin\nenabled = true"})

    assert response.status_code == 400
    assert "TOML 格式错误" in response.json()["detail"]


def test_recycle_bin_route(client: TestClient, monkeypatch):
    async def fake_get_recycle_bin(*, limit: int):
        return {"success": True, "items": [{"hash": "deadbeef"}], "count": 1, "limit": limit}

    monkeypatch.setattr(memory_router_module.memory_service, "get_recycle_bin", fake_get_recycle_bin)

    response = client.get("/api/memory/recycle_bin", params={"limit": 10})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["count"] == 1
    assert response.json()["limit"] == 10


def test_import_guide_route(client: TestClient, monkeypatch):
    async def fake_import_admin(*, action: str, **kwargs):
        assert kwargs == {}
        if action == "get_guide":
            return {"success": True}
        if action == "get_settings":
            return {"success": True, "settings": {"path_aliases": {"raw": "/tmp/raw"}}}
        raise AssertionError(action)

    monkeypatch.setattr(memory_router_module.memory_service, "import_admin", fake_import_admin)

    response = client.get("/api/webui/memory/import/guide")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["source"] == "local"
    assert "长期记忆导入说明" in response.json()["content"]


def test_import_upload_route(client: TestClient, monkeypatch, tmp_path):
    monkeypatch.setattr(memory_router_module, "STAGING_ROOT", tmp_path)

    async def fake_import_admin(*, action: str, **kwargs):
        assert action == "create_upload"
        staged_files = kwargs["staged_files"]
        assert len(staged_files) == 1
        assert staged_files[0]["filename"] == "demo.txt"
        assert memory_router_module.Path(staged_files[0]["staged_path"]).exists()
        return {"success": True, "task_id": "task-1"}

    monkeypatch.setattr(memory_router_module.memory_service, "import_admin", fake_import_admin)

    response = client.post(
        "/api/import/upload",
        data={"payload_json": "{\"source\": \"upload\"}"},
        files=[("files", ("demo.txt", b"hello world", "text/plain"))],
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "task_id": "task-1"}
    assert list(tmp_path.iterdir()) == []


def test_v5_status_route(client: TestClient, monkeypatch):
    async def fake_v5_admin(*, action: str, **kwargs):
        assert action == "status"
        assert kwargs["target"] == "mai"
        return {"success": True, "active_count": 1, "inactive_count": 2, "deleted_count": 3}

    monkeypatch.setattr(memory_router_module.memory_service, "v5_admin", fake_v5_admin)

    response = client.get("/api/webui/memory/v5/status", params={"target": "mai"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["deleted_count"] == 3


def test_delete_preview_route(client: TestClient, monkeypatch):
    async def fake_delete_admin(*, action: str, **kwargs):
        assert action == "preview"
        assert kwargs["mode"] == "paragraph"
        assert kwargs["selector"] == {"query": "demo"}
        return {"success": True, "counts": {"paragraphs": 1}, "dry_run": True}

    monkeypatch.setattr(memory_router_module.memory_service, "delete_admin", fake_delete_admin)

    response = client.post(
        "/api/webui/memory/delete/preview",
        json={"mode": "paragraph", "selector": {"query": "demo"}},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "counts": {"paragraphs": 1}, "dry_run": True}


def test_delete_preview_route_supports_mixed_mode(client: TestClient, monkeypatch):
    async def fake_delete_admin(*, action: str, **kwargs):
        assert action == "preview"
        assert kwargs["mode"] == "mixed"
        assert kwargs["selector"] == {
            "entity_hashes": ["entity-1"],
            "paragraph_hashes": ["p-1"],
            "relation_hashes": ["rel-1"],
            "sources": ["demo"],
        }
        return {"success": True, "mode": "mixed", "counts": {"entities": 1, "paragraphs": 1, "relations": 1, "sources": 1}}

    monkeypatch.setattr(memory_router_module.memory_service, "delete_admin", fake_delete_admin)

    response = client.post(
        "/api/webui/memory/delete/preview",
        json={
            "mode": "mixed",
            "selector": {
                "entity_hashes": ["entity-1"],
                "paragraph_hashes": ["p-1"],
                "relation_hashes": ["rel-1"],
                "sources": ["demo"],
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "mixed"
    assert response.json()["counts"]["entities"] == 1


def test_delete_execute_route_supports_mixed_mode(client: TestClient, monkeypatch):
    async def fake_delete_admin(*, action: str, **kwargs):
        assert action == "execute"
        assert kwargs["mode"] == "mixed"
        assert kwargs["selector"] == {
            "entity_hashes": ["entity-1"],
            "paragraph_hashes": ["p-1"],
            "relation_hashes": ["rel-1"],
            "sources": ["demo"],
        }
        assert kwargs["reason"] == "knowledge_graph_delete_entity"
        assert kwargs["requested_by"] == "knowledge_graph"
        return {
            "success": True,
            "mode": "mixed",
            "operation_id": "op-mixed-1",
            "deleted_count": 4,
            "deleted_entity_count": 1,
            "deleted_relation_count": 1,
            "deleted_paragraph_count": 1,
            "deleted_source_count": 1,
            "counts": {"entities": 1, "paragraphs": 1, "relations": 1, "sources": 1},
        }

    monkeypatch.setattr(memory_router_module.memory_service, "delete_admin", fake_delete_admin)

    response = client.post(
        "/api/webui/memory/delete/execute",
        json={
            "mode": "mixed",
            "selector": {
                "entity_hashes": ["entity-1"],
                "paragraph_hashes": ["p-1"],
                "relation_hashes": ["rel-1"],
                "sources": ["demo"],
            },
            "reason": "knowledge_graph_delete_entity",
            "requested_by": "knowledge_graph",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["mode"] == "mixed"
    assert response.json()["operation_id"] == "op-mixed-1"


def test_episode_process_pending_route(client: TestClient, monkeypatch):
    async def fake_episode_admin(*, action: str, **kwargs):
        assert action == "process_pending"
        assert kwargs == {"limit": 7, "max_retry": 4}
        return {"success": True, "processed": 3}

    monkeypatch.setattr(memory_router_module.memory_service, "episode_admin", fake_episode_admin)

    response = client.post("/api/webui/memory/episodes/process-pending", json={"limit": 7, "max_retry": 4})

    assert response.status_code == 200
    assert response.json() == {"success": True, "processed": 3}


def test_import_list_route_includes_settings(client: TestClient, monkeypatch):
    calls = []

    async def fake_import_admin(*, action: str, **kwargs):
        calls.append((action, kwargs))
        if action == "list":
            return {"success": True, "items": [{"task_id": "task-1"}]}
        if action == "get_settings":
            return {"success": True, "settings": {"path_aliases": {"lpmm": "/tmp/lpmm"}}}
        raise AssertionError(action)

    monkeypatch.setattr(memory_router_module.memory_service, "import_admin", fake_import_admin)

    response = client.get("/api/webui/memory/import/tasks", params={"limit": 9})

    assert response.status_code == 200
    assert response.json()["items"] == [{"task_id": "task-1"}]
    assert response.json()["settings"] == {"path_aliases": {"lpmm": "/tmp/lpmm"}}
    assert calls == [("list", {"limit": 9}), ("get_settings", {})]


def test_tuning_profile_route_backfills_settings(client: TestClient, monkeypatch):
    calls = []

    async def fake_tuning_admin(*, action: str, **kwargs):
        calls.append((action, kwargs))
        if action == "get_profile":
            return {"success": True, "profile": {"retrieval": {"top_k": 8}}}
        if action == "get_settings":
            return {"success": True, "settings": {"profiles": ["default"]}}
        raise AssertionError(action)

    monkeypatch.setattr(memory_router_module.memory_service, "tuning_admin", fake_tuning_admin)

    response = client.get("/api/webui/memory/retrieval_tuning/profile")

    assert response.status_code == 200
    assert response.json()["profile"] == {"retrieval": {"top_k": 8}}
    assert response.json()["settings"] == {"profiles": ["default"]}
    assert calls == [("get_profile", {}), ("get_settings", {})]


def test_tuning_report_route_flattens_report_payload(client: TestClient, monkeypatch):
    async def fake_tuning_admin(*, action: str, **kwargs):
        assert action == "get_report"
        assert kwargs == {"task_id": "task-1", "format": "json"}
        return {
            "success": True,
            "report": {"format": "json", "content": "{\"ok\": true}", "path": "/tmp/report.json"},
        }

    monkeypatch.setattr(memory_router_module.memory_service, "tuning_admin", fake_tuning_admin)

    response = client.get("/api/webui/memory/retrieval_tuning/tasks/task-1/report", params={"format": "json"})

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "format": "json",
        "content": "{\"ok\": true}",
        "path": "/tmp/report.json",
        "error": "",
    }


def test_delete_execute_route(client: TestClient, monkeypatch):
    async def fake_delete_admin(*, action: str, **kwargs):
        assert action == "execute"
        assert kwargs["mode"] == "source"
        assert kwargs["selector"] == {"source": "chat_summary:stream-1"}
        assert kwargs["reason"] == "cleanup"
        assert kwargs["requested_by"] == "tester"
        return {"success": True, "operation_id": "del-1"}

    monkeypatch.setattr(memory_router_module.memory_service, "delete_admin", fake_delete_admin)

    response = client.post(
        "/api/webui/memory/delete/execute",
        json={
            "mode": "source",
            "selector": {"source": "chat_summary:stream-1"},
            "reason": "cleanup",
            "requested_by": "tester",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "operation_id": "del-1"}


def test_sources_route(client: TestClient, monkeypatch):
    async def fake_source_admin(*, action: str, **kwargs):
        assert action == "list"
        assert kwargs == {}
        return {"success": True, "items": [{"source": "demo", "paragraph_count": 2}], "count": 1}

    monkeypatch.setattr(memory_router_module.memory_service, "source_admin", fake_source_admin)

    response = client.get("/api/webui/memory/sources")

    assert response.status_code == 200
    assert response.json()["items"] == [{"source": "demo", "paragraph_count": 2}]


def test_delete_operation_routes(client: TestClient, monkeypatch):
    async def fake_delete_admin(*, action: str, **kwargs):
        if action == "list_operations":
            assert kwargs == {"limit": 5, "mode": "paragraph"}
            return {"success": True, "items": [{"operation_id": "del-1"}], "count": 1}
        if action == "get_operation":
            assert kwargs == {"operation_id": "del-1"}
            return {"success": True, "operation": {"operation_id": "del-1", "mode": "paragraph"}}
        raise AssertionError(action)

    monkeypatch.setattr(memory_router_module.memory_service, "delete_admin", fake_delete_admin)

    list_response = client.get("/api/webui/memory/delete/operations", params={"limit": 5, "mode": "paragraph"})
    get_response = client.get("/api/webui/memory/delete/operations/del-1")

    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1
    assert get_response.status_code == 200
    assert get_response.json()["operation"]["operation_id"] == "del-1"


def test_feedback_correction_routes(client: TestClient, monkeypatch):
    async def fake_feedback_admin(*, action: str, **kwargs):
        if action == "list":
            assert kwargs == {
                "limit": 7,
                "statuses": ["applied"],
                "rollback_statuses": ["none"],
                "query": "green",
            }
            return {"success": True, "items": [{"task_id": 11, "query_text": "what color"}], "count": 1}
        if action == "get":
            assert kwargs == {"task_id": 11}
            return {"success": True, "task": {"task_id": 11, "query_text": "what color", "action_logs": []}}
        if action == "rollback":
            assert kwargs == {"task_id": 11, "requested_by": "tester", "reason": "manual revert"}
            return {"success": True, "result": {"restored_relation_hashes": ["rel-1"]}}
        raise AssertionError(action)

    monkeypatch.setattr(memory_router_module.memory_service, "feedback_admin", fake_feedback_admin)

    list_response = client.get(
        "/api/webui/memory/feedback-corrections",
        params={"limit": 7, "status": "applied", "rollback_status": "none", "query": "green"},
    )
    get_response = client.get("/api/webui/memory/feedback-corrections/11")
    rollback_response = client.post(
        "/api/webui/memory/feedback-corrections/11/rollback",
        json={"requested_by": "tester", "reason": "manual revert"},
    )

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["task_id"] == 11
    assert get_response.status_code == 200
    assert get_response.json()["task"]["task_id"] == 11
    assert rollback_response.status_code == 200
    assert rollback_response.json()["result"]["restored_relation_hashes"] == ["rel-1"]
