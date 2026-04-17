"""测试表达方式学习器的数据库读取行为。"""

from contextlib import contextmanager
from typing import Generator

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from src.bw_learner.expression_learner import ExpressionLearner
from src.common.database.database_model import Expression


@pytest.fixture(name="expression_learner_engine")
def expression_learner_engine_fixture() -> Generator:
    """创建用于表达方式学习器测试的内存数据库引擎。

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


def test_find_similar_expression_uses_read_only_session_and_history_content(
    monkeypatch: pytest.MonkeyPatch,
    expression_learner_engine,
) -> None:
    """查找相似表达方式时，应能在离开会话后安全使用结果，并比较历史情景内容。"""
    import src.bw_learner.expression_learner as expression_learner_module

    with Session(expression_learner_engine) as session:
        session.add(
            Expression(
                situation="发送汗滴表情",
                style="发送💦表情符号",
                content_list='["表达情绪高涨或生理反应"]',
                count=1,
                session_id="session-a",
                checked=False,
                rejected=False,
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
        session = Session(expression_learner_engine)
        try:
            yield session
            if auto_commit:
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(expression_learner_module, "get_db_session", fake_get_db_session)

    learner = ExpressionLearner(session_id="session-a")
    result = learner._find_similar_expression("表达情绪高涨或生理反应")

    assert result is not None
    expression, similarity = result
    assert expression.item_id is not None
    assert expression.style == "发送💦表情符号"
    assert similarity == pytest.approx(1.0)
