"""v34 schema 升级到 v35：为 chat_sessions 增加 agent_id 字段。"""

from sqlalchemy.engine import Connection

from src.common.logger import get_logger

from .models import MigrationExecutionContext
from .schema import SQLiteSchemaInspector

logger = get_logger("database_migration")


def migrate_v34_to_v35(context: MigrationExecutionContext) -> None:
    """为 ``chat_sessions`` 增加 ``agent_id`` 列，默认值为 ``silver_wolf``。"""

    context.start_progress(
        total_tables=1,
        total_records=1,
        description="v34 -> v35 迁移进度",
        table_unit_name="表",
        record_unit_name="列",
    )

    added = add_agent_id_column(context.connection)
    context.advance_progress(records=added, completed_tables=1, item_name="chat_sessions")

    logger.info("v34 -> v35 数据库迁移完成：chat_sessions.agent_id 列已就绪")


def add_agent_id_column(connection: Connection) -> int:
    """为 chat_sessions 表添加 agent_id 列。"""

    schema_inspector = SQLiteSchemaInspector()
    if not schema_inspector.table_exists(connection, "chat_sessions"):
        return 0

    table_schema = schema_inspector.get_table_schema(connection, "chat_sessions")
    if table_schema.has_column("agent_id"):
        return 0

    connection.exec_driver_sql(
        "ALTER TABLE chat_sessions ADD COLUMN agent_id VARCHAR(64) NOT NULL DEFAULT 'silver_wolf'"
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_chat_sessions_agent_id ON chat_sessions (agent_id)"
    )

    return 1