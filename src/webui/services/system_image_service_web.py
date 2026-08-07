"""系统图片与数据库 Service 层（WebUI 专用）

从 routers/system.py 下沉的 ORM 操作函数 + 辅助函数。
router 层退化为薄包装：HTTP 解析 + session 管理 + 响应包装。
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import func, inspect, text
from sqlmodel import col, select

from src.common.database.database import engine
from src.common.database.database_model import Images, ImageType
from src.common.logger import get_logger
from src.common.utils.image_path import (
    StoredImagePathError,
    resolve_stored_image_path,
    stored_image_paths_equal,
)
from src.webui.errors import AppError
from src.webui.errors.codes import ErrorCode
from src.webui.schemas.system import DatabaseTableStats


logger = get_logger("webui_system")


# ── 常量 ──────────────────────────────────────────────────────────────

IMAGE_TYPE_IMAGE = ImageType.IMAGE
IMAGE_TYPE_EMOJI = ImageType.EMOJI

_DATABASE_CLEANUP_TABLES: dict[str, dict[str, str]] = {
    "llm_usage": {
        "label": "LLM 调用记录",
        "category": "调用与统计",
        "description": "模型调用、Token、耗时和费用记录。",
        "date_column": "timestamp",
    },
    "tool_records": {
        "label": "工具调用记录",
        "category": "调用与统计",
        "description": "内置工具和插件工具的调用过程记录。",
        "date_column": "timestamp",
    },
    "mai_messages": {
        "label": "消息记录",
        "category": "聊天历史",
        "description": "收到的聊天消息与消息元数据。",
        "date_column": "timestamp",
    },
    "chat_history": {
        "label": "聊天摘要历史",
        "category": "聊天历史",
        "description": "聊天片段摘要、主题和关键词记录。",
        "date_column": "end_timestamp",
    },
    "online_time": {
        "label": "在线时长记录",
        "category": "运行统计",
        "description": "运行在线时长统计记录。",
        "date_column": "timestamp",
    },
    "statistics_message_hourly": {
        "label": "消息小时统计",
        "category": "统计缓存",
        "description": "按小时聚合的消息统计缓存。",
        "date_column": "bucket_time",
    },
    "statistics_tool_hourly": {
        "label": "工具小时统计",
        "category": "统计缓存",
        "description": "按小时聚合的工具调用统计缓存。",
        "date_column": "bucket_time",
    },
    "statistics_model_hourly": {
        "label": "模型小时统计",
        "category": "统计缓存",
        "description": "按小时聚合的模型调用统计缓存。",
        "date_column": "bucket_time",
    },
}


# ── 纯转换/辅助函数 ──────────────────────────────────────────────────

def paths_equal(left: str, right: Path) -> bool:
    try:
        return stored_image_paths_equal(left, right)
    except (OSError, RuntimeError, StoredImagePathError):
        return False


def remove_emoji_hashes_from_memory(image_hashes: set[str]) -> None:
    if not image_hashes:
        return

    try:
        from src.emoji_system.emoji_manager import emoji_manager

        emoji_manager.emojis = [emoji for emoji in emoji_manager.emojis if emoji.file_hash not in image_hashes]
        emoji_manager._emoji_num = len(emoji_manager.emojis)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARN, "同步移除内存表情包失败", exception=exc)
        logger.warning(f"同步移除内存表情包失败: {exc}")


def quote_sqlite_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


# ── ORM 操作函数（接收 session 参数，不自行创建 session）──────────

def get_image_records_by_path(session: Any, image_type: ImageType) -> dict[Path, list[Images]]:
    records_by_path: dict[Path, list[Images]] = {}
    statement = select(Images).where(col(Images.image_type) == image_type)
    records = session.exec(statement).all()

    for record in records:
        try:
            record_path = resolve_stored_image_path(record.full_path)
        except (OSError, RuntimeError, StoredImagePathError):
            continue
        records_by_path.setdefault(record_path, []).append(record)
    return records_by_path


def get_image_record_count(session: Any, image_type: ImageType) -> int:
    statement = select(func.count()).select_from(Images).where(col(Images.image_type) == image_type)
    return int(session.exec(statement).one())


def delete_image_records_for_file(session: Any, image_type: ImageType, file_path: Path) -> tuple[int, set[str]]:
    removed_records = 0
    removed_hashes: set[str] = set()

    statement = select(Images).where(col(Images.image_type) == image_type)
    for record in session.exec(statement).all():
        if not paths_equal(record.full_path, file_path):
            continue

        if record.image_hash:
            removed_hashes.add(record.image_hash)
        session.delete(record)
        removed_records += 1

    if image_type == ImageType.EMOJI:
        remove_emoji_hashes_from_memory(removed_hashes)
    return removed_records, removed_hashes


def delete_image_records(session: Any, image_type: ImageType) -> int:
    removed_records = 0
    removed_hashes: set[str] = set()
    statement = select(Images).where(col(Images.image_type) == image_type)
    for record in session.exec(statement).all():
        if record.image_hash:
            removed_hashes.add(record.image_hash)
        session.delete(record)
        removed_records += 1
    if image_type == ImageType.EMOJI:
        remove_emoji_hashes_from_memory(removed_hashes)
    return removed_records


def resolve_monitor_media_file(session: Any, media_kind: str, media_hash: str) -> Path:
    """根据监控事件中的媒体 hash 解析原始图片或表情文件。"""

    normalized_hash = media_hash.strip()
    if not normalized_hash:
        raise AppError(ErrorCode.PARAM_INVALID, "媒体 hash 不能为空")

    image_type = ImageType.IMAGE if media_kind == "image" else ImageType.EMOJI
    label = "图片" if media_kind == "image" else "表情包"
    statement = select(Images).filter_by(image_hash=normalized_hash, image_type=image_type).limit(1)
    image_record = session.exec(statement).first()

    if image_record is None:
        raise AppError(ErrorCode.BIZ_NOT_FOUND, f"未找到指定{label}记录", http_status=404)

    try:
        file_path = resolve_stored_image_path(image_record.full_path)
    except (OSError, RuntimeError, StoredImagePathError) as exc:
        raise AppError(ErrorCode.BIZ_NOT_FOUND, f"无法解析指定{label}文件", http_status=404) from exc

    if not file_path.is_file():
        raise AppError(ErrorCode.BIZ_NOT_FOUND, f"未找到指定{label}文件", http_status=404)
    return file_path


# ── 数据库统计函数（使用 engine 直接操作）──────────────────────────

def get_table_indexes(connection, table_name: str) -> list[str]:
    quoted_table_name = quote_sqlite_identifier(table_name)
    indexes = []
    for row in connection.execute(text(f"PRAGMA index_list({quoted_table_name})")).fetchall():
        if len(row) > 1 and row[1]:
            indexes.append(str(row[1]))
    return indexes


def get_dbstat_table_sizes(connection, table_names: list[str]) -> dict[str, int] | None:
    try:
        connection.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS temp.local_cache_dbstat USING dbstat(main)"))
        rows = connection.execute(
            text("SELECT name, SUM(pgsize) AS size FROM temp.local_cache_dbstat GROUP BY name")
        ).fetchall()
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARN, "当前 SQLite 环境不支持 dbstat，数据库表大小将使用估算值", exception=exc)
        logger.warning(f"当前 SQLite 环境不支持 dbstat，数据库表大小将使用估算值: {exc}")
        return None

    object_sizes = {str(row[0]): int(row[1] or 0) for row in rows}
    table_sizes: dict[str, int] = {}
    for table_name in table_names:
        table_size = object_sizes.get(table_name, 0)
        for index_name in get_table_indexes(connection, table_name):
            table_size += object_sizes.get(index_name, 0)
        table_sizes[table_name] = table_size
    return table_sizes


def estimate_table_data_size(connection, table_name: str, rows: int) -> int:
    if rows <= 0:
        return 0

    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    if not columns:
        return 0

    quoted_table_name = quote_sqlite_identifier(table_name)
    sample_limit = min(rows, 200)
    column_expressions = [
        f"COALESCE(LENGTH(CAST({quote_sqlite_identifier(column['name'])} AS BLOB)), 0)" for column in columns
    ]
    expression = " + ".join(column_expressions)
    sample_size, sample_rows = connection.execute(
        text(
            f"SELECT COALESCE(SUM({expression}), 0), COUNT(*) "
            f"FROM (SELECT * FROM {quoted_table_name} LIMIT {sample_limit})"
        )
    ).one()
    if int(sample_rows or 0) == 0:
        return 0
    return int(int(sample_size or 0) * rows / int(sample_rows))


def get_database_table_stats() -> list[DatabaseTableStats]:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    table_stats: list[DatabaseTableStats] = []
    with engine.connect() as connection:
        dbstat_sizes = get_dbstat_table_sizes(connection, table_names)
        for table_name in table_names:
            quoted_table_name = quote_sqlite_identifier(table_name)
            rows = connection.execute(text(f"SELECT COUNT(*) FROM {quoted_table_name}")).scalar_one()
            row_count = int(rows)
            if dbstat_sizes is None:
                size = estimate_table_data_size(connection, table_name, row_count)
                size_source: Literal["dbstat", "estimated"] = "estimated"
            else:
                size = dbstat_sizes.get(table_name, 0)
                size_source = "dbstat"
            cleanup_config = _DATABASE_CLEANUP_TABLES.get(table_name)
            table_stats.append(
                DatabaseTableStats(
                    name=table_name,
                    rows=row_count,
                    size=size,
                    size_source=size_source,
                    label=cleanup_config["label"] if cleanup_config is not None else table_name,
                    category=cleanup_config["category"] if cleanup_config is not None else "其他",
                    description=cleanup_config["description"] if cleanup_config is not None else "",
                    cleanup_supported=cleanup_config is not None,
                    cleanup_date_column=cleanup_config["date_column"] if cleanup_config is not None else None,
                )
            )
    return sorted(table_stats, key=lambda item: item.name)


def delete_database_records(
    table_names: list[str],
    mode: str,
    older_than_days: int | None,
) -> int:
    allowed_tables = set(_DATABASE_CLEANUP_TABLES)
    invalid_tables = set(table_names) - allowed_tables
    if invalid_tables:
        raise ValueError(f"不支持清理这些表: {', '.join(sorted(invalid_tables))}")
    if mode == "older_than_days" and older_than_days is None:
        raise AppError(ErrorCode.PARAM_INVALID, "按时间清理时必须设置保留天数")

    removed_records = 0
    existing_tables = set(inspect(engine).get_table_names())
    with engine.begin() as connection:
        for table_name in table_names:
            if table_name not in existing_tables:
                continue

            quoted_table_name = quote_sqlite_identifier(table_name)
            if mode == "all":
                result = connection.execute(text(f"DELETE FROM {quoted_table_name}"))
            else:
                cleanup_config = _DATABASE_CLEANUP_TABLES[table_name]
                date_column = cleanup_config["date_column"]
                cutoff_time = datetime.now() - timedelta(days=older_than_days or 0)
                quoted_date_column = quote_sqlite_identifier(date_column)
                result = connection.execute(
                    text(f"DELETE FROM {quoted_table_name} WHERE {quoted_date_column} < :cutoff_time"),
                    {"cutoff_time": cutoff_time},
                )
            removed_records += int(result.rowcount or 0)
    return removed_records