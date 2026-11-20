"""发送者身份两列的 schema、迁移与查询测试（批次 3）。"""

from datetime import datetime

import msgpack
import pytest

from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from src.common.database.database import engine, get_db_session
from src.common.database.database_model import Messages
from src.common.database.migrations.models import MigrationExecutionContext
from src.common.database.migrations.v40_to_v41 import (
    _add_sender_identity_columns,
    migrate_v40_to_v41,
)
from src.common.message_repository import find_messages


SESSION_ID = "session-sender-identity"


@pytest.fixture(autouse=True)
def clean_sender_rows():
    with get_db_session() as session:
        session.query(Messages).filter_by(session_id=SESSION_ID).delete()
    yield


def _make_context(connection) -> MigrationExecutionContext:
    return MigrationExecutionContext(
        connection=connection,
        current_version=40,
        target_version=41,
        step_index=1,
        step_name="v40_to_v41",
        total_steps=1,
    )


def test_migration_adds_columns_twice_idempotent():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with test_engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE mai_messages (id INTEGER PRIMARY KEY, message_id VARCHAR(255), reply_frequency FLOAT)"
        )
        first = _add_sender_identity_columns(connection)
        second = _add_sender_identity_columns(connection)
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(mai_messages)")}

    assert first == 2
    assert second == 0
    assert {"sender_type", "sender_agent_id"} <= columns


def test_migration_outer_runner_is_idempotent():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with test_engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE mai_messages (id INTEGER PRIMARY KEY, message_id VARCHAR(255), reply_frequency FLOAT)"
        )
        migrate_v40_to_v41(_make_context(connection))
        migrate_v40_to_v41(_make_context(connection))
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(mai_messages)")}

    assert {"sender_type", "sender_agent_id"} <= columns


def test_create_all_has_sender_columns():
    columns = {column["name"] for column in inspect(engine).get_columns("mai_messages")}

    assert {"sender_type", "sender_agent_id"} <= columns


def _insert_row(message_id: str, *, sender_type: str | None, sender_agent_id: str | None) -> None:
    with get_db_session() as session:
        session.add(
            Messages(
                message_id=message_id,
                timestamp=datetime.now(),
                platform="qq",
                user_id="bot_account",
                user_nickname="麦麦",
                session_id=SESSION_ID,
                raw_content=msgpack.packb([]),
                processed_plain_text="hi",
                sender_type=sender_type,
                sender_agent_id=sender_agent_id,
            )
        )


def test_round_trip_and_nullable_read():
    _insert_row("m-agent-1", sender_type="agent", sender_agent_id="silver_wolf")
    _insert_row("m-null-1", sender_type=None, sender_agent_id=None)

    rows = {row.message_id: row for row in find_messages(session_id=SESSION_ID)}

    assert rows["m-agent-1"].sender_type == "agent"
    assert rows["m-agent-1"].sender_agent_id == "silver_wolf"
    assert rows["m-agent-1"].message_info.user_info.user_id == "bot_account"
    assert rows["m-null-1"].sender_type is None
    assert rows["m-null-1"].sender_agent_id is None


def test_find_messages_sender_filters():
    _insert_row("m-agent-1", sender_type="agent", sender_agent_id="silver_wolf")
    _insert_row("m-other-agent", sender_type="agent", sender_agent_id="bronya")
    _insert_row("m-null-1", sender_type=None, sender_agent_id=None)

    only_silver = find_messages(session_id=SESSION_ID, sender_agent_id="silver_wolf")
    null_sender = find_messages(session_id=SESSION_ID, sender_agent_id="")
    agents = find_messages(session_id=SESSION_ID, sender_type="agent")

    assert [row.message_id for row in only_silver] == ["m-agent-1"]
    assert [row.message_id for row in null_sender] == ["m-null-1"]
    assert {row.message_id for row in agents} == {"m-agent-1", "m-other-agent"}