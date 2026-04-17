"""测试黑话学习器的数据库读取行为。"""

from contextlib import contextmanager
from typing import Generator

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from src.bw_learner.jargon_miner import JargonMiner
from src.common.database.database_model import Jargon


@pytest.fixture(name="jargon_miner_engine")
def jargon_miner_engine_fixture() -> Generator:
    """创建用于黑话学习器测试的内存数据库引擎。

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


@pytest.mark.asyncio
async def test_process_extracted_entries_updates_existing_jargon_without_detached_session(
    monkeypatch: pytest.MonkeyPatch,
    jargon_miner_engine,
) -> None:
    """更新已有黑话时，不应因会话关闭导致 ORM 实例失效。"""
    import src.bw_learner.jargon_miner as jargon_miner_module

    with Session(jargon_miner_engine) as session:
        session.add(
            Jargon(
                content="VF8V4L",
                raw_content='["[1] first"]',
                meaning="",
                session_id_dict='{"session-a": 1}',
                count=0,
                is_jargon=True,
                is_complete=False,
                is_global=False,
                last_inference_count=0,
            )
        )
        session.commit()

    @contextmanager
    def fake_get_db_session(auto_commit: bool = True) -> Generator[Session, None, None]:
        """构造带自动提交语义的测试会话工厂。

        Args:
            auto_commit: 退出上下文时是否自动提交。

        Yields:
            Generator[Session, None, None]: SQLModel 会话对象。
        """
        session = Session(jargon_miner_engine)
        try:
            yield session
            if auto_commit:
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(jargon_miner_module, "get_db_session", fake_get_db_session)

    jargon_miner = JargonMiner(session_id="session-a", session_name="测试群")
    await jargon_miner.process_extracted_entries(
        [{"content": "VF8V4L", "raw_content": {"[2] second"}}],
    )

    with Session(jargon_miner_engine) as session:
        db_jargon = session.exec(select(Jargon).where(Jargon.content == "VF8V4L")).one()

    assert db_jargon.count == 1
    assert db_jargon.session_id_dict == '{"session-a": 2}'
    assert sorted(db_jargon.raw_content and __import__("json").loads(db_jargon.raw_content)) == [
        "[1] first",
        "[2] second",
    ]
