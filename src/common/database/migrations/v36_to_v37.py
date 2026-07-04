"""v36 schema 升级到 v37：创建 subagent_execution_records 表。"""

from sqlalchemy.engine import Connection

from src.common.logger import get_logger

from .models import MigrationExecutionContext
from .schema import SQLiteSchemaInspector

logger = get_logger("database_migration")


def migrate_v36_to_v37(context: MigrationExecutionContext) -> None:
    """创建 ``subagent_execution_records`` 表用于存储子智能体执行审计日志。"""

    context.start_progress(
        total_tables=1,
        total_records=1,
        description="v36 -> v37 迁移进度",
        table_unit_name="表",
        record_unit_name="列",
    )

    created = create_subagent_execution_records_table(context.connection)
    context.advance_progress(records=created, completed_tables=1, item_name="subagent_execution_records")

    logger.info("v36 -> v37 数据库迁移完成：subagent_execution_records 表已就绪")


def create_subagent_execution_records_table(connection: Connection) -> int:
    """创建 subagent_execution_records 表。"""

    schema_inspector = SQLiteSchemaInspector()
    if schema_inspector.table_exists(connection, "subagent_execution_records"):
        return 0

    connection.exec_driver_sql(
        """
        CREATE TABLE subagent_execution_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subagent_id VARCHAR(64) NOT NULL,
            agent_id VARCHAR(64) NOT NULL,
            subagent_type VARCHAR(32) NOT NULL,
            session_id VARCHAR(255),
            lifecycle VARCHAR(16) NOT NULL DEFAULT 'ephemeral',
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            trigger_type VARCHAR(16) NOT NULL DEFAULT 'auto',
            trigger_reason TEXT DEFAULT '',
            fork_context_captured INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cache_hit_tokens INTEGER NOT NULL DEFAULT 0,
            started_at DATETIME,
            completed_at DATETIME,
            error_message TEXT DEFAULT '',
            result_summary TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_subagent_exec_subagent_id ON subagent_execution_records (subagent_id)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_subagent_exec_agent_id ON subagent_execution_records (agent_id)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_subagent_exec_type ON subagent_execution_records (subagent_type)"
    )

    return 1