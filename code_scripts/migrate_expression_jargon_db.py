from argparse import ArgumentParser, Namespace
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from sys import path as sys_path
from typing import Any, Optional

import json
import sqlite3

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, delete

ROOT_PATH = Path(__file__).resolve().parent.parent
if str(ROOT_PATH) not in sys_path:
    sys_path.insert(0, str(ROOT_PATH))

from src.common.database.database_model import Expression, Jargon, ModifiedBy  # noqa: E402


def build_argument_parser() -> ArgumentParser:
    """构建命令行参数解析器。"""
    parser = ArgumentParser(
        description="将旧版 expression/jargon 数据迁移到新版 expressions/jargons 数据库。"
    )
    parser.add_argument("--source-db", dest="source_db", help="旧版 SQLite 数据库路径")
    parser.add_argument("--target-db", dest="target_db", help="新版 SQLite 数据库路径")
    parser.add_argument(
        "--clear-target",
        dest="clear_target",
        action="store_true",
        help="迁移前清空目标库中的 expressions 和 jargons 表",
    )
    return parser


def prompt_path(prompt_text: str, current_value: Optional[str] = None) -> Path:
    """读取数据库路径输入。"""
    while True:
        suffix = f" [{current_value}]" if current_value else ""
        raw_text = input(f"{prompt_text}{suffix}: ").strip()
        value = raw_text or current_value or ""
        if not value:
            print("路径不能为空，请重新输入。")
            continue
        return Path(value).expanduser().resolve()


def prompt_yes_no(prompt_text: str, default: bool = False) -> bool:
    """读取是否确认输入。"""
    default_hint = "Y/n" if default else "y/N"
    raw_text = input(f"{prompt_text} [{default_hint}]: ").strip().lower()
    if not raw_text:
        return default
    return raw_text in {"y", "yes"}


def ensure_sqlite_file(path: Path, should_exist: bool) -> None:
    """校验 SQLite 文件路径。"""
    if should_exist and not path.is_file():
        raise FileNotFoundError(f"数据库文件不存在：{path}")
    if not should_exist:
        path.parent.mkdir(parents=True, exist_ok=True)


def connect_sqlite(path: Path) -> sqlite3.Connection:
    """创建 SQLite 连接。"""
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    """检查表是否存在。"""
    result = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return result is not None


def resolve_source_table_name(connection: sqlite3.Connection, candidates: list[str]) -> str:
    """从候选表名中解析实际存在的表名。"""
    for table_name in candidates:
        if table_exists(connection, table_name):
            return table_name
    raise ValueError(f"未找到候选表：{', '.join(candidates)}")


def get_table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    """获取表字段名集合。"""
    rows = connection.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    return {str(row["name"]) for row in rows}


def get_table_nullable_map(connection: sqlite3.Connection, table_name: str) -> dict[str, bool]:
    """获取表字段是否允许 NULL 的映射。"""
    rows = connection.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    return {str(row["name"]): not bool(row["notnull"]) for row in rows}


def load_rows(connection: sqlite3.Connection, table_name: str) -> list[sqlite3.Row]:
    """读取整张表的数据。"""
    return connection.execute(f"SELECT * FROM {table_name}").fetchall()


def normalize_optional_text(raw_value: Any) -> Optional[str]:
    """标准化可空文本字段。"""
    if raw_value is None:
        return None
    return str(raw_value)


def ensure_nullable_compatibility(
    table_name: str,
    column_name: str,
    row_id: Any,
    value: Any,
    nullable_map: dict[str, bool],
) -> None:
    """检查待迁移值是否与目标表可空约束兼容。"""
    if value is None and not nullable_map.get(column_name, True):
        raise ValueError(
            f"目标表 {table_name}.{column_name} 不允许 NULL，但源记录 id={row_id} 的该字段为 NULL。"
        )


def normalize_string_list(raw_value: Any) -> list[str]:
    """将旧库中的 JSON/文本字段标准化为字符串列表。"""
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    if isinstance(raw_value, str):
        raw_text = raw_value.strip()
        if not raw_text:
            return []
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            return [raw_text]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        if isinstance(parsed, str):
            parsed_text = parsed.strip()
            return [parsed_text] if parsed_text else []
        if parsed is None:
            return []
        return [str(parsed).strip()]
    return [str(raw_value).strip()]


def normalize_modified_by(raw_value: Any) -> Optional[ModifiedBy]:
    """标准化审核来源字段。"""
    if raw_value is None:
        return None

    normalized_raw_value = raw_value
    if isinstance(raw_value, str):
        raw_text = raw_value.strip()
        if raw_text.startswith('"') and raw_text.endswith('"'):
            try:
                normalized_raw_value = json.loads(raw_text)
            except json.JSONDecodeError:
                normalized_raw_value = raw_text
        else:
            normalized_raw_value = raw_text

    value = str(normalized_raw_value).strip().lower()
    if value in {"", "none", "null"}:
        return None
    if value in {ModifiedBy.AI.value, ModifiedBy.AI.name.lower()}:
        return ModifiedBy.AI
    if value in {ModifiedBy.USER.value, ModifiedBy.USER.name.lower()}:
        return ModifiedBy.USER
    return None


def parse_optional_bool(raw_value: Any) -> Optional[bool]:
    """解析可空布尔值，兼容整数和字符串。"""
    if raw_value is None:
        return None
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, int):
        return bool(raw_value)
    if isinstance(raw_value, float):
        return bool(int(raw_value))

    value = str(raw_value).strip().lower()
    if value in {"", "none", "null"}:
        return None
    if value in {"1", "true", "t", "yes", "y"}:
        return True
    if value in {"0", "false", "f", "no", "n"}:
        return False
    raise ValueError(f"无法解析布尔值：{raw_value}")


def parse_bool(raw_value: Any, default: bool = False) -> bool:
    """解析非空布尔值。"""
    parsed = parse_optional_bool(raw_value)
    return default if parsed is None else parsed


def timestamp_to_datetime(raw_value: Any, fallback_now: bool) -> Optional[datetime]:
    """将旧库中的 Unix 时间戳转换为 datetime。"""
    if raw_value is None or raw_value == "":
        return datetime.now() if fallback_now else None
    if isinstance(raw_value, datetime):
        return raw_value
    try:
        return datetime.fromtimestamp(float(raw_value))
    except (TypeError, ValueError, OSError, OverflowError):
        return datetime.now() if fallback_now else None


def build_session_id_dict(raw_chat_id: Any, fallback_count: int) -> str:
    """将旧版 jargon.chat_id 转换为新版 session_id_dict。"""
    if raw_chat_id is None:
        return json.dumps({}, ensure_ascii=False)

    if isinstance(raw_chat_id, str):
        raw_text = raw_chat_id.strip()
    else:
        raw_text = str(raw_chat_id).strip()

    if not raw_text:
        return json.dumps({}, ensure_ascii=False)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return json.dumps({raw_text: max(fallback_count, 1)}, ensure_ascii=False)

    if isinstance(parsed, str):
        parsed_text = parsed.strip()
        session_counts = {parsed_text: max(fallback_count, 1)} if parsed_text else {}
        return json.dumps(session_counts, ensure_ascii=False)

    if not isinstance(parsed, list):
        return json.dumps({}, ensure_ascii=False)

    session_counts: dict[str, int] = {}
    for item in parsed:
        if not isinstance(item, list) or not item:
            continue
        session_id = str(item[0]).strip()
        if not session_id:
            continue
        item_count = 1
        if len(item) > 1:
            try:
                item_count = int(item[1])
            except (TypeError, ValueError):
                item_count = 1
        session_counts[session_id] = max(item_count, 1)

    return json.dumps(session_counts, ensure_ascii=False)


def create_target_engine(target_db_path: Path):
    """创建目标数据库引擎。"""
    return create_engine(
        f"sqlite:///{target_db_path.as_posix()}",
        echo=False,
        connect_args={"check_same_thread": False},
    )


def clear_target_tables(session: Session) -> None:
    """清空目标表。"""
    session.exec(delete(Expression))
    session.exec(delete(Jargon))


def migrate_expressions(
    old_rows: Iterable[sqlite3.Row],
    target_session: Session,
    expression_columns: set[str],
) -> int:
    """迁移 expression 数据。"""
    migrated_count = 0
    modified_by_ai_count = 0
    modified_by_user_count = 0
    modified_by_null_count = 0
    unknown_modified_by_values: dict[str, int] = {}
    for row in old_rows:
        create_time = timestamp_to_datetime(row["create_date"] if "create_date" in expression_columns else None, True)
        last_active_time = timestamp_to_datetime(
            row["last_active_time"] if "last_active_time" in expression_columns else None,
            True,
        )
        content_list = normalize_string_list(row["content_list"] if "content_list" in expression_columns else None)
        raw_modified_by = row["modified_by"] if "modified_by" in expression_columns else None
        modified_by = normalize_modified_by(raw_modified_by)
        if modified_by == ModifiedBy.AI:
            modified_by_ai_count += 1
        elif modified_by == ModifiedBy.USER:
            modified_by_user_count += 1
        else:
            modified_by_null_count += 1
            if raw_modified_by not in (None, "", "null", "NULL", "None"):
                unknown_key = str(raw_modified_by)
                unknown_modified_by_values[unknown_key] = unknown_modified_by_values.get(unknown_key, 0) + 1

        target_session.execute(
            text(
                """
                INSERT INTO expressions (
                    id,
                    situation,
                    style,
                    content_list,
                    count,
                    last_active_time,
                    create_time,
                    session_id,
                    checked,
                    rejected,
                    modified_by
                ) VALUES (
                    :id,
                    :situation,
                    :style,
                    :content_list,
                    :count,
                    :last_active_time,
                    :create_time,
                    :session_id,
                    :checked,
                    :rejected,
                    :modified_by
                )
                """
            ),
            {
                "id": int(row["id"]) if row["id"] is not None else None,
                "situation": str(row["situation"]).strip(),
                "style": str(row["style"]).strip(),
                "content_list": json.dumps(content_list, ensure_ascii=False),
                "count": int(row["count"]) if "count" in expression_columns and row["count"] is not None else 1,
                "last_active_time": last_active_time or datetime.now(),
                "create_time": create_time or datetime.now(),
                "session_id": str(row["chat_id"]).strip() if "chat_id" in expression_columns and row["chat_id"] else None,
                "checked": parse_bool(row["checked"] if "checked" in expression_columns else None, default=False),
                "rejected": parse_bool(row["rejected"] if "rejected" in expression_columns else None, default=False),
                "modified_by": modified_by.name if modified_by is not None else None,
            },
        )
        migrated_count += 1

    print(
        "Expression modified_by 迁移统计："
        f" AI={modified_by_ai_count}, USER={modified_by_user_count}, NULL={modified_by_null_count}"
    )
    if unknown_modified_by_values:
        preview_items = list(unknown_modified_by_values.items())[:10]
        preview_text = ", ".join(f"{value!r} x{count}" for value, count in preview_items)
        print(f"警告：以下旧 modified_by 值未识别，已按 NULL 迁移：{preview_text}")
    return migrated_count


def migrate_jargons(
    old_rows: Iterable[sqlite3.Row],
    target_session: Session,
    jargon_columns: set[str],
    jargon_nullable_map: dict[str, bool],
) -> int:
    """迁移 jargon 数据。"""
    migrated_count = 0
    coerced_meaning_null_count = 0
    for row in old_rows:
        count = int(row["count"]) if "count" in jargon_columns and row["count"] is not None else 0
        raw_content_value = row["raw_content"] if "raw_content" in jargon_columns else None
        raw_content_list = normalize_string_list(raw_content_value)
        meaning_value = normalize_optional_text(row["meaning"] if "meaning" in jargon_columns else None)
        is_jargon_value = parse_optional_bool(row["is_jargon"] if "is_jargon" in jargon_columns else None)
        inference_content_key = (
            "inference_content_only"
            if "inference_content_only" in jargon_columns
            else "inference_with_content_only"
            if "inference_with_content_only" in jargon_columns
            else None
        )

        ensure_nullable_compatibility("jargons", "is_jargon", row["id"], is_jargon_value, jargon_nullable_map)

        if meaning_value is None and not jargon_nullable_map.get("meaning", True):
            meaning_value = ""
            coerced_meaning_null_count += 1

        # 显式执行 SQL，避免 ORM 在 None 场景下回填模型默认值。
        target_session.execute(
            text(
                """
                INSERT INTO jargons (
                    id,
                    content,
                    raw_content,
                    meaning,
                    session_id_dict,
                    count,
                    is_jargon,
                    is_complete,
                    is_global,
                    last_inference_count,
                    inference_with_context,
                    inference_with_content_only
                ) VALUES (
                    :id,
                    :content,
                    :raw_content,
                    :meaning,
                    :session_id_dict,
                    :count,
                    :is_jargon,
                    :is_complete,
                    :is_global,
                    :last_inference_count,
                    :inference_with_context,
                    :inference_with_content_only
                )
                """
            ),
            {
                "id": int(row["id"]) if row["id"] is not None else None,
                "content": str(row["content"]).strip(),
                "raw_content": json.dumps(raw_content_list, ensure_ascii=False) if raw_content_value is not None else None,
                "meaning": meaning_value,
                "session_id_dict": build_session_id_dict(
                    row["chat_id"] if "chat_id" in jargon_columns else None,
                    fallback_count=count,
                ),
                "count": count,
                "is_jargon": is_jargon_value,
                "is_complete": parse_bool(row["is_complete"] if "is_complete" in jargon_columns else None, default=False),
                "is_global": parse_bool(row["is_global"] if "is_global" in jargon_columns else None, default=False),
                "last_inference_count": (
                    int(row["last_inference_count"])
                    if "last_inference_count" in jargon_columns and row["last_inference_count"] is not None
                    else 0
                ),
                "inference_with_context": (
                    str(row["inference_with_context"])
                    if "inference_with_context" in jargon_columns and row["inference_with_context"] is not None
                    else None
                ),
                "inference_with_content_only": (
                    str(row[inference_content_key])
                    if inference_content_key and row[inference_content_key] is not None
                    else None
                ),
            },
        )
        migrated_count += 1

    if coerced_meaning_null_count > 0:
        print(
            f"警告：目标表 jargons.meaning 不允许 NULL，已将 {coerced_meaning_null_count} 条旧记录的 NULL meaning 转为空字符串。"
        )
    return migrated_count


def confirm_target_replacement(target_db_path: Path, clear_target: bool) -> bool:
    """确认是否写入目标数据库。"""
    if clear_target:
        return prompt_yes_no(f"将清空目标库中的 expressions/jargons 后再迁移，确认继续吗？\n目标库：{target_db_path}")
    return prompt_yes_no(f"将写入目标库，若主键冲突会导致迁移失败，确认继续吗？\n目标库：{target_db_path}")


def parse_arguments() -> Namespace:
    """解析参数。"""
    return build_argument_parser().parse_args()


def main() -> None:
    """脚本入口。"""
    args = parse_arguments()

    print("旧版 expression/jargon -> 新版 expressions/jargons 迁移工具")
    source_db_path = prompt_path("请输入旧版数据库路径", args.source_db)
    target_db_path = prompt_path("请输入新版数据库路径", args.target_db)
    clear_target = args.clear_target or prompt_yes_no("迁移前是否清空目标库中的 expressions 和 jargons 表？", False)

    if source_db_path == target_db_path:
        raise ValueError("旧版数据库路径和新版数据库路径不能相同。")

    ensure_sqlite_file(source_db_path, should_exist=True)
    ensure_sqlite_file(target_db_path, should_exist=False)

    print(f"旧库：{source_db_path}")
    print(f"新库：{target_db_path}")
    print(f"清空目标表：{'是' if clear_target else '否'}")

    if not confirm_target_replacement(target_db_path, clear_target):
        print("已取消迁移。")
        return

    source_connection = connect_sqlite(source_db_path)
    try:
        expression_table_name = resolve_source_table_name(source_connection, ["expression", "expressions"])
        jargon_table_name = resolve_source_table_name(source_connection, ["jargon", "jargons"])
        expression_columns = get_table_columns(source_connection, expression_table_name)
        jargon_columns = get_table_columns(source_connection, jargon_table_name)
        expression_rows = load_rows(source_connection, expression_table_name)
        jargon_rows = load_rows(source_connection, jargon_table_name)
    finally:
        source_connection.close()

    target_engine = create_target_engine(target_db_path)
    SQLModel.metadata.create_all(target_engine)

    target_sqlite_connection = connect_sqlite(target_db_path)
    try:
        jargon_nullable_map = get_table_nullable_map(target_sqlite_connection, "jargons")
    finally:
        target_sqlite_connection.close()

    with Session(target_engine) as target_session:
        if clear_target:
            clear_target_tables(target_session)
            target_session.commit()

        expression_count = migrate_expressions(expression_rows, target_session, expression_columns)
        jargon_count = migrate_jargons(jargon_rows, target_session, jargon_columns, jargon_nullable_map)
        target_session.commit()

    print("迁移完成。")
    print(f"已迁移 expression 记录：{expression_count}")
    print(f"已迁移 jargon 记录：{jargon_count}")


if __name__ == "__main__":
    main()
