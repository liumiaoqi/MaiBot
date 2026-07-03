"""v35 schema 升级到 v36：创建 agent_relationships 表。"""

from sqlalchemy.engine import Connection

from src.common.logger import get_logger

from .models import MigrationExecutionContext
from .schema import SQLiteSchemaInspector

logger = get_logger("database_migration")


def migrate_v35_to_v36(context: MigrationExecutionContext) -> None:
    """创建 ``agent_relationships`` 表用于存储智能体与用户的关系数据。"""

    context.start_progress(
        total_tables=1,
        total_records=1,
        description="v35 -> v36 迁移进度",
        table_unit_name="表",
        record_unit_name="列",
    )

    created = create_agent_relationships_table(context.connection)
    context.advance_progress(records=created, completed_tables=1, item_name="agent_relationships")

    logger.info("v35 -> v36 数据库迁移完成：agent_relationships 表已就绪")


def create_agent_relationships_table(connection: Connection) -> int:
    """创建 agent_relationships 表。"""

    schema_inspector = SQLiteSchemaInspector()
    if schema_inspector.table_exists(connection, "agent_relationships"):
        return 0

    connection.exec_driver_sql(
        """
        CREATE TABLE agent_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id VARCHAR(64) NOT NULL,
            user_id VARCHAR(255) NOT NULL,
            score FLOAT NOT NULL DEFAULT 0.0,
            level INTEGER NOT NULL DEFAULT 0,
            interaction_count INTEGER NOT NULL DEFAULT 0,
            last_interaction_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_agent_relationships_agent_id ON agent_relationships (agent_id)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_agent_relationships_user_id ON agent_relationships (user_id)"
    )
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX uix_agent_relationships_agent_user ON agent_relationships (agent_id, user_id)"
    )

    return 1