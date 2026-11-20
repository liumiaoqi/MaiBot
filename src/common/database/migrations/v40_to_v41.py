"""v40 schema 升级到 v41：消息发送者身份字段。"""

from sqlalchemy.engine import Connection

from src.common.logger import get_logger

from .models import MigrationExecutionContext
from .schema import SQLiteSchemaInspector

logger = get_logger("database_migration")


def migrate_v40_to_v41(context: MigrationExecutionContext) -> None:
    """为 mai_messages 增加发送者类别与角色身份字段。"""

    context.start_progress(
        total_tables=1,
        total_records=2,
        description="v40 -> v41 迁移进度",
        table_unit_name="表",
        record_unit_name="记录",
    )

    added = _add_sender_identity_columns(context.connection)
    context.advance_progress(records=added, completed_tables=1, item_name="mai_messages")

    logger.info("消息发送者身份字段已就绪")


def _add_sender_identity_columns(connection: Connection) -> int:
    schema_inspector = SQLiteSchemaInspector()
    if not schema_inspector.table_exists(connection, "mai_messages"):
        return 0

    table_schema = schema_inspector.get_table_schema(connection, "mai_messages")
    added = 0
    if not table_schema.has_column("sender_type"):
        connection.exec_driver_sql("ALTER TABLE mai_messages ADD COLUMN sender_type VARCHAR(16)")
        added += 1
    if not table_schema.has_column("sender_agent_id"):
        connection.exec_driver_sql("ALTER TABLE mai_messages ADD COLUMN sender_agent_id VARCHAR(64)")
        added += 1
    return added