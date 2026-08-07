"""T2.5 expression 写测试 — CRUD 端点覆盖

依赖 db_isolation fixture（内存 SQLite），测试结束数据自动清理。
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from tests.webui.conftest import assert_api_success


@pytest.fixture
def seed_chat_session(db_isolation):
    """在内存 SQLite 中预置一条 ChatSession，返回 session_id。"""
    from unittest.mock import patch

    from sqlmodel import Session

    from src.common.database.database_model import ChatSession

    with Session(db_isolation) as session:
        chat = ChatSession(
            session_id="test-chat-id",
            platform="aiocqhttp",
        )
        session.add(chat)
        session.commit()

    fake_info = SimpleNamespace(session_id="test-chat-id", session_name="测试聊天流")
    with patch("src.webui.routers.expression.get_existing_session_info", return_value=fake_info):
        yield "test-chat-id"


@pytest.fixture
def seed_expression(auth_client, db_isolation, seed_chat_session):
    """预置一条测试表达方式，返回创建的 ID。"""
    r = auth_client.post("/api/webui/expression/", json={
        "situation": "测试场景",
        "style": "测试风格",
        "chat_id": seed_chat_session,
    })
    if r.status_code == 200:
        data = r.json()
        return data.get("data", {}).get("id")
    return None


class TestExpressionWrite:
    """expression CRUD 写端点测试"""

    def test_create_expression(self, auth_client, db_isolation, seed_chat_session):
        """POST /expression/ — 创建表达方式"""
        r = auth_client.post("/api/webui/expression/", json={
            "situation": "创建测试场景",
            "style": "创建测试风格",
            "chat_id": seed_chat_session,
        })
        assert r.status_code == 200, f"创建失败: {r.text}"
        data = r.json()
        assert data["success"] is True
        assert data["data"]["id"] is not None

    def test_update_expression(self, auth_client, db_isolation, seed_expression):
        """PATCH /expression/{id} — 更新表达方式"""
        if seed_expression is None:
            pytest.skip("seed_expression 创建失败")

        r = auth_client.patch(f"/api/webui/expression/{seed_expression}", json={
            "situation": "更新后场景",
        })
        assert r.status_code == 200, f"更新失败: {r.text}"
        data = r.json()
        assert data["success"] is True

    def test_delete_expression(self, auth_client, db_isolation, seed_expression):
        """DELETE /expression/{id} — 删除表达方式"""
        if seed_expression is None:
            pytest.skip("seed_expression 创建失败")

        r = auth_client.delete(f"/api/webui/expression/{seed_expression}")
        assert r.status_code == 200, f"删除失败: {r.text}"
        data = r.json()
        assert data["success"] is True

    def test_batch_delete_expressions(self, auth_client, db_isolation, seed_expression):
        """POST /expression/batch/delete — 批量删除"""
        if seed_expression is None:
            pytest.skip("seed_expression 创建失败")

        r = auth_client.post("/api/webui/expression/batch/delete", json={
            "ids": [seed_expression],
        })
        assert r.status_code == 200, f"批量删除失败: {r.text}"
        data = r.json()
        assert data["success"] is True

    def test_create_expression_validation_error(self, auth_client, db_isolation):
        """POST /expression/ — 缺少必填字段应返回 422"""
        r = auth_client.post("/api/webui/expression/", json={
            "situation": "缺少 style 和 chat_id",
        })
        assert r.status_code == 422

    def test_create_expression_nonexistent_chat(self, auth_client, db_isolation):
        """POST /expression/ — 不存在的 chat_id 应返回 400"""
        r = auth_client.post("/api/webui/expression/", json={
            "situation": "测试场景",
            "style": "测试风格",
            "chat_id": "nonexistent-chat-id",
        })
        assert r.status_code == 400, f"应返回 400: {r.text}"
