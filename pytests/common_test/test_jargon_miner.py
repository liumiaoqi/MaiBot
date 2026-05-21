"""测试黑话学习器的数据库读取行为。"""

from contextlib import contextmanager
from typing import Generator

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from src.learners.jargon_miner import JargonMiner
from src.common.database.database_model import Jargon, JargonCreatedBy


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
    import src.learners.jargon_miner as jargon_miner_module

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
    saved_count, updated_count = await jargon_miner.process_extracted_entries(
        [{"content": "VF8V4L", "raw_content": {"[2] second"}}],
    )

    with Session(jargon_miner_engine) as session:
        db_jargon = session.exec(select(Jargon).where(Jargon.content == "VF8V4L")).one()

    assert saved_count == 0
    assert updated_count == 1
    assert db_jargon.count == 1
    assert db_jargon.session_id_dict == '{"session-a": 2}'
    assert db_jargon.updated_timestamp >= db_jargon.created_timestamp
    assert sorted(db_jargon.raw_content and __import__("json").loads(db_jargon.raw_content)) == [
        "[1] first",
        "[2] second",
    ]


@pytest.mark.asyncio
async def test_process_extracted_entries_skips_manual_jargon(
    monkeypatch: pytest.MonkeyPatch,
    jargon_miner_engine,
) -> None:
    """AI 学习命中手动黑话时，不应更新计数、上下文或触发推断。"""
    import src.learners.jargon_miner as jargon_miner_module

    with Session(jargon_miner_engine) as session:
        session.add(
            Jargon(
                content="MANUAL_ONLY",
                raw_content='["[1] first"]',
                meaning="手动含义",
                session_id_dict='{"session-a": 1}',
                count=3,
                is_jargon=True,
                is_complete=False,
                is_global=False,
                last_inference_count=0,
                created_by=JargonCreatedBy.MANUAL,
            )
        )
        session.commit()

    @contextmanager
    def fake_get_db_session(auto_commit: bool = True) -> Generator[Session, None, None]:
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

    infer_called = False

    async def fake_infer_meaning_by_id(self, jargon_id: int) -> None:
        nonlocal infer_called
        del self, jargon_id
        infer_called = True

    monkeypatch.setattr(jargon_miner_module, "get_db_session", fake_get_db_session)
    monkeypatch.setattr(JargonMiner, "_infer_meaning_by_id", fake_infer_meaning_by_id)

    jargon_miner = JargonMiner(session_id="session-a", session_name="测试群")
    saved_count, updated_count = await jargon_miner.process_extracted_entries(
        [{"content": "MANUAL_ONLY", "raw_content": {"[2] second"}}],
    )

    with Session(jargon_miner_engine) as session:
        db_jargon = session.exec(select(Jargon).where(Jargon.content == "MANUAL_ONLY")).one()

    assert saved_count == 0
    assert updated_count == 0
    assert infer_called is False
    assert db_jargon.count == 3
    assert db_jargon.session_id_dict == '{"session-a": 1}'
    assert db_jargon.raw_content == '["[1] first"]'


@pytest.mark.parametrize(
    ("count", "last_inference_count", "is_complete", "expected"),
    [
        (3, 0, False, False),
        (4, 0, False, True),
        (7, 4, False, False),
        (8, 4, False, True),
        (24, 8, False, False),
        (25, 8, False, True),
        (99, 25, False, False),
        (100, 25, False, True),
        (101, 100, False, False),
        (100, 25, True, False),
    ],
)
def test_should_infer_meaning_uses_current_thresholds(
    count: int,
    last_inference_count: int,
    is_complete: bool,
    expected: bool,
) -> None:
    """黑话含义推断阈值应为 4、8、25、100。"""
    jargon_miner = JargonMiner(session_id="session-a", session_name="测试群")
    jargon = Jargon(
        content="VF8V4L",
        raw_content='["[1] first"]',
        meaning="",
        session_id_dict='{"session-a": 1}',
        count=count,
        is_complete=is_complete,
        last_inference_count=last_inference_count,
    )

    assert jargon_miner._should_infer_meaning(jargon) is expected


def test_should_infer_meaning_skips_manual_jargon() -> None:
    """手动黑话不应进入 AI 含义推断。"""
    jargon_miner = JargonMiner(session_id="session-a", session_name="测试群")
    jargon = Jargon(
        content="MANUAL_ONLY",
        raw_content='["[1] first"]',
        meaning="手动含义",
        session_id_dict='{"session-a": 1}',
        count=100,
        is_complete=False,
        last_inference_count=0,
        created_by=JargonCreatedBy.MANUAL,
    )

    assert jargon_miner._should_infer_meaning(jargon) is False
