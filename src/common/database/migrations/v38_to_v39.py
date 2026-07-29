"""v38 schema 升级到 v39：agent_interaction_relationships 增加 Hebbian 共激活字段。"""

from sqlalchemy.engine import Connection

from src.common.logger import get_logger

from .models import MigrationExecutionContext
from .schema import SQLiteSchemaInspector

logger = get_logger("database_migration")


def migrate_v38_to_v39(context: MigrationExecutionContext) -> None:
    """为 ``agent_interaction_relationships`` 表增加 ``coactivation_strength`` 和 ``last_coactivation_at`` 列。"""

    context.start_progress(
        total_tables=1,
        total_records=2,
        description="v38 -> v39 迁移进度",
        table_unit_name="表",
        record_unit_name="列",
    )

    added = add_coactivation_columns(context.connection)
    context.advance_progress(records=added, completed_tables=1, item_name="agent_interaction_relationships")

    logger.info("v38 -> v39 数据库迁移完成：Hebbian共激活字段已就绪")


def add_coactivation_columns(connection: Connection) -> int:
    """为 agent_interaction_relationships 表增加 coactivation_strength 和 last_coactivation_at 列。"""

    schema_inspector = SQLiteSchemaInspector()
    added = 0

    table_schema = schema_inspector.get_table_schema(connection, "agent_interaction_relationships")

    if table_schema and not table_schema.has_column("coactivation_strength"):
        connection.exec_driver_sql(
            "ALTER TABLE agent_interaction_relationships ADD COLUMN coactivation_strength REAL NOT NULL DEFAULT 0.0"
        )
        added += 1

    if table_schema and not table_schema.has_column("last_coactivation_at"):
        connection.exec_driver_sql(
            "ALTER TABLE agent_interaction_relationships ADD COLUMN last_coactivation_at REAL NOT NULL DEFAULT 0.0"
        )
        added += 1

    return added