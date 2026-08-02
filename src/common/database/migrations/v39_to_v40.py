"""v39 schema 升级到 v40：agent_autonomy_speaker_change_records 增加 transfer_type / decision_source 列。"""

from sqlalchemy.engine import Connection

from src.common.logger import get_logger

from .models import MigrationExecutionContext
from .schema import SQLiteSchemaInspector

logger = get_logger("database_migration")


def migrate_v39_to_v40(context: MigrationExecutionContext) -> None:
    """为 ``agent_autonomy_speaker_change_records`` 表增加 ``transfer_type`` / ``decision_source`` 列。"""

    context.start_progress(
        total_tables=1,
        total_records=2,
        description="v39 -> v40 迁移进度",
        table_unit_name="表",
        record_unit_name="列",
    )

    added = add_missing_columns(context.connection)
    context.advance_progress(records=added, completed_tables=1, item_name="agent_autonomy_speaker_change_records")

    logger.info("v39 -> v40 数据库迁移完成：发言权移交字段已就绪")


def add_missing_columns(connection: Connection) -> int:
    """为 agent_autonomy_speaker_change_records 表补齐模型新增列（模型已加，迁移未跟，写库必崩）。"""

    schema_inspector = SQLiteSchemaInspector()
    added = 0

    table_schema = schema_inspector.get_table_schema(connection, "agent_autonomy_speaker_change_records")

    if table_schema and not table_schema.has_column("transfer_type"):
        connection.exec_driver_sql(
            "ALTER TABLE agent_autonomy_speaker_change_records ADD COLUMN transfer_type VARCHAR(32) NOT NULL DEFAULT 'permanent_transfer'"
        )
        added += 1

    if table_schema and not table_schema.has_column("decision_source"):
        connection.exec_driver_sql(
            "ALTER TABLE agent_autonomy_speaker_change_records ADD COLUMN decision_source VARCHAR(32) NOT NULL DEFAULT 'manual'"
        )
        added += 1

    return added
