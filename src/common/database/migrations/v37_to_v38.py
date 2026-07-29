"""v37 schema 升级到 v38：agent_autonomy_activities 增加思维连续性字段。"""

from sqlalchemy.engine import Connection

from src.common.logger import get_logger

from .models import MigrationExecutionContext
from .schema import SQLiteSchemaInspector

logger = get_logger("database_migration")


def migrate_v37_to_v38(context: MigrationExecutionContext) -> None:
    """为 ``agent_autonomy_activities`` 表增加 ``thought_summary`` 和 ``last_think_at`` 列。"""

    context.start_progress(
        total_tables=1,
        total_records=2,
        description="v37 -> v38 迁移进度",
        table_unit_name="表",
        record_unit_name="列",
    )

    added = add_thinking_continuity_columns(context.connection)
    context.advance_progress(records=added, completed_tables=1, item_name="agent_autonomy_activities")

    logger.info("v37 -> v38 数据库迁移完成：思维连续性字段已就绪")


def add_thinking_continuity_columns(connection: Connection) -> int:
    """为 agent_autonomy_activities 表增加 thought_summary 和 last_think_at 列。"""

    schema_inspector = SQLiteSchemaInspector()
    added = 0

    table_schema = schema_inspector.get_table_schema(connection, "agent_autonomy_activities")

    if table_schema and not table_schema.has_column("thought_summary"):
        connection.exec_driver_sql(
            "ALTER TABLE agent_autonomy_activities ADD COLUMN thought_summary VARCHAR(500) NOT NULL DEFAULT ''"
        )
        added += 1

    if table_schema and not table_schema.has_column("last_think_at"):
        connection.exec_driver_sql(
            "ALTER TABLE agent_autonomy_activities ADD COLUMN last_think_at DATETIME"
        )
        added += 1

    return added
