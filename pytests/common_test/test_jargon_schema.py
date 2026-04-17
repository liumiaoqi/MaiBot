"""测试黑话表结构和基础插入行为。"""

from typing import Generator

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from src.common.database.database_model import Jargon


@pytest.fixture(name="jargon_engine")
def jargon_engine_fixture() -> Generator:
    """创建仅用于黑话表测试的内存数据库引擎。

    Yields:
        Generator: 供测试使用的 SQLite 内存引擎。
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine


def test_jargon_insert_assigns_auto_increment_id(jargon_engine) -> None:
    """黑话表在新库中应能自动分配自增主键。"""
    with Session(jargon_engine) as session:
        jargon = Jargon(
            content="VF8V4L",
            raw_content='["[1] test"]',
            meaning="",
            session_id_dict='{"session-a": 1}',
            count=1,
            is_jargon=True,
            is_complete=False,
            is_global=True,
            last_inference_count=0,
        )
        session.add(jargon)
        session.commit()
        session.refresh(jargon)

    assert jargon.id is not None
    assert jargon.id > 0


def test_jargon_insert_allows_same_content_with_different_rows(jargon_engine) -> None:
    """黑话内容不应再被错误地绑成复合主键的一部分。"""
    with Session(jargon_engine) as session:
        first_jargon = Jargon(
            content="表情1",
            raw_content='["[1] first"]',
            meaning="",
            session_id_dict='{"session-a": 1}',
            count=1,
            is_jargon=True,
            is_complete=False,
            is_global=False,
            last_inference_count=0,
        )
        second_jargon = Jargon(
            content="表情1",
            raw_content='["[1] second"]',
            meaning="",
            session_id_dict='{"session-b": 1}',
            count=1,
            is_jargon=True,
            is_complete=False,
            is_global=False,
            last_inference_count=0,
        )

        session.add(first_jargon)
        session.add(second_jargon)
        session.commit()
        session.refresh(first_jargon)
        session.refresh(second_jargon)

    assert first_jargon.id is not None
    assert second_jargon.id is not None
    assert first_jargon.id != second_jargon.id
