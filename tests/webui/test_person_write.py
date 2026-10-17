"""person 批量删除写端点测试

回归背景：router 的批删路由函数与 service 同名导入，遮蔽后体内调用变成"调自己"。
依赖 db_isolation fixture（内存 SQLite），测试结束数据自动清理。
"""

import pytest


@pytest.fixture
def seed_persons(db_isolation):
    """在内存 SQLite 中预置两条 PersonInfo，返回 person_id 列表。"""
    from sqlmodel import Session

    from src.common.database.database_model import PersonInfo

    person_ids = ["person-a", "person-b"]
    with Session(db_isolation) as session:
        for person_id in person_ids:
            session.add(
                PersonInfo(
                    person_id=person_id,
                    platform="aiocqhttp",
                    user_id=person_id,
                    user_nickname=person_id,
                )
            )
        session.commit()

    return person_ids


def test_batch_delete_persons_calls_service(auth_client, db_isolation, seed_persons):
    """POST /person/batch/delete — 批量删除走 service 真实落库（回归：曾调用到自己 ⇒ 500）"""
    r = auth_client.post("/api/webui/person/batch/delete", json={"person_ids": seed_persons})
    assert r.status_code == 200, f"批量删除失败: {r.text}"
    data = r.json()
    assert data["success"] is True
    assert data["deleted_count"] == len(seed_persons)
    assert data["failed_count"] == 0
    assert data["failed_ids"] == []

    from sqlmodel import Session, select

    from src.common.database.database_model import PersonInfo

    with Session(db_isolation) as session:
        assert session.exec(select(PersonInfo)).all() == []
