"""v30 schema 升级到 v31：清理低信息行为场景。"""

from collections import defaultdict
from datetime import datetime
from typing import Any, Sequence

import json
import random

from sqlalchemy.engine import Connection

from src.common.logger import get_logger

from .models import MigrationExecutionContext
from .schema import SQLiteSchemaInspector
# === 以下为行为学习系统内联（激进档废弃，迁移语义保持原样）===
# 来源: 行为学习系统通用标签模块（激进档废弃时内联，迁移语义保持原样）



TAG_KIND_ALIASES = {
    "domain": "domain",
    "other_domain": "domain",
}

IMAGE_UNDERSTANDING_MARKERS = ("识别", "描述", "分析", "理解")
GROUP_CHAT_GENERIC_MARKERS = (
    "互动",
    "调侃",
    "玩梗",
    "氛围",
    "闲聊",
    "日常",
    "搞笑",
    "娱乐",
    "放松",
    "水群",
    "聊天",
    "对话",
    "社交",
    "起哄",
    "吐槽",
    "玩笑",
    "幽默",
)
IMAGE_GENERIC_MARKERS = ("表情包", "斗图", "发图", "刷表情")
SHORT_GENERIC_MARKERS = ("聊天", "群聊", "闲聊", "水群", "玩梗", "调侃", "复读", "刷屏", "发图", "斗图")

GENERIC_DOMAIN_TAGS = {
    "聊天",
    "群聊",
    "群消息",
    "群内聊天",
    "群友互动",
    "群聊互动",
    "群内互动",
    "群聊氛围",
    "群聊日常",
    "日常对话",
    "水群",
    "闲聊",
    "随意聊天",
    "玩梗",
    "调侃互动",
    "轻松搞笑",
    "搞笑对话",
    "表情包交流",
    "表情包聊天",
    "发图",
    "图片分享",
    "情绪表达",
    "复读",
    "刷屏",
    "群聊调侃",
    "群聊玩梗",
    "群聊互动氛围",
    "群聊社交",
    "群聊搞笑",
    "群聊闲聊",
    "群聊幽默对话",
    "群聊日常互动",
    "群友聊天",
    "群聊水群",
    "群聊聊天",
    "群聊娱乐互动",
    "群聊放松",
    "群内闲聊",
    "群聊调侃玩梗",
    "群聊玩梗互动",
    "群聊调侃氛围",
    "群友玩梗",
    "群友调侃",
    "群友玩梗调侃",
    "群友交流",
    "群组交流",
    "群内讨论",
    "多人聊天",
    "群聊分享",
    "群聊场景",
    "群友讨论",
    "群组讨论",
    "互动",
    "群组互动",
    "群聊呼叫",
    "群友@",
    "群聊技术讨论",
    "ai闲聊",
    "技术群聊",
    "多人对话",
    "群聊功能",
    "群组聊天",
    "群聊机制",
    "群聊经验分享",
    "群聊反馈",
    "社交对话",
    "日常聊天",
    "日常水群",
    "群聊活跃",
    "群聊活跃度",
    "群聊气氛",
    "聊天梗互动",
    "群聊寒暄",
    "娱乐互动",
    "闲聊接话",
    "日常交流",
    "日常闲聊互动",
    "生活闲聊",
    "日常吐槽",
    "日常分享",
    "日常闲聊吐槽",
    "日常话题",
    "轻松聊天",
    "闲聊互动",
    "群聊戏谑",
    "群聊调戏",
    "群聊嘲讽",
    "聊天调侃",
    "互动调侃",
    "群内整活",
    "群内嘲讽",
    "群聊杂谈",
    "群聊热闹",
    "群内欢乐",
    "轻松水群",
    "半夜闲聊",
    "闲聊混搭",
    "测试机器人",
    "逗机器人",
    "抽象行为",
    "玩梗抽象",
    "抽象提问",
    "抽象测试",
    "玩梗氛围",
    "轻松氛围",
    "群友嘲讽",
    "群聊段子",
    "戏谑对话",
    "轻松玩笑",
    "跟风互动",
    "聊天热闹",
    "随口聊天",
    "网络流行梗",
    "接梗",
    "幽默接梗",
    "群聊吐槽",
    "网络段子",
    "梗文化",
    "网络梗文化",
    "网络梗",
    "群聊梗",
    "群聊幽默",
    "群聊互动调侃",
    "群聊起哄",
    "开玩笑回复",
    "配合调侃",
    "互怼",
    "抬杠",
    "回怼",
    "表情包回复",
    "表情包斗图",
    "表情包刷屏",
    "表情包表达",
    "表情包玩梗",
    "表情包使用",
    "表情包互动",
    "斗图",
    "表情包分享",
    "表情包回应",
    "表情包轰炸",
    "发表情包",
    "表情回复",
    "表情包社交",
    "表情包传情",
    "分享图片",
    "刷表情",
    "图片表情包互动",
    "图片互动",
    "表情包表达情绪",
    "图片梗",
    "发图交流",
    "meme交流",
    "动漫表情",
    "群聊斗图",
    "表情包与玩梗",
    "图片消息",
    "图片",
    "截图分享",
    "晒图",
    "发表情",
    "mface",
    "mface表情",
    "表情回应",
    "表情交流",
    "图片回复",
    "玩梗刷图",
    "图片回应",
    "表情图回复",
    "发送表情",
    "图片表情",
    "搞笑表情",
    "魔性表情",
    "face表情",
    "颜文字",
    "发梗图",
    "分享搞笑图",
    "愤怒表情",
    "崩溃表情",
    "委屈表情",
    "q版表情",
    "大量表情",
    "用表情回复",
    "分享表情",
    "贴表情",
    "表情轰炸",
    "图片交流",
    "图片互怼",
    "图片分享互动",
    "复读机",
    "重复发言",
    "复读行为",
    "复读梗",
    "重复消息",
    "刷屏复读",
    "群聊复读",
    "群聊复读行为",
    "复读接龙",
    "刷屏接龙",
    "跟风回复",
    "跟风玩梗",
    "跟风接龙",
    "接龙玩梗",
    "玩梗接龙",
    "梗互动",
    "复制发言",
    "复制粘贴",
    "模仿回复",
    "队形",
    "群聊跟风刷队形",
    "复制粘贴队形",
    "重复内容",
    "刷梗",
    "梗文化互动",
    "深夜聊天",
    "深夜水群",
    "凌晨闲聊",
    "夜间社交",
    "深夜闲聊",
    "深夜互动",
    "半夜群聊",
    "夜间群聊",
    "凌晨聊天",
    "深夜群聊",
    "半夜聊天",
    "凌晨群聊",
    "夜猫子群聊",
    "熬夜群聊",
    "深夜活跃",
    "夜间活跃",
    "夜间互动",
    "深夜调侃",
    "半夜水群",
    "闲聊话题",
    "日常闲聊",
    "随便聊聊",
    "无主题对话",
    "社交闲聊",
    "朋友间互动",
    "轻松社交",
    "meme互动",
    "梗图互动",
    "用图回复",
    "用梗互动",
    "配图交流",
    "meme回应",
    "meme 互动",
    "群聊话题切换",
    "群友逗机器人",
    "群聊接梗",
    "群聊调戏bot",
    "群聊生态",
    "群聊风格",
    "群聊热度",
    "群友接梗",
    "同时讨论多个话题",
    "轻松谈天",
    "简短回复",
    "梗接力",
    "群聊接龙文化",
    "模仿发言",
    "队列式回复",
    "网络梗接龙",
    "乐接龙",
    "复制粘贴接龙",
    "群内气氛轻松",
    "多人互动",
    "群聊欢乐",
    "幽默接梗互动",
    "群内锐评",
    "幽默邀请",
    "跟风",
    "接龙",
    "重复句式",
    "连续发送相同内容",
    "群里玩梗",
    "非技术话题",
    "生活琐事",
    "幽默吐槽",
    "轻松调侃",
    "调侃玩梗",
    "调侃与幽默",
    "社群文化",
    "视觉内容",
    "meme分享",
    "meme对战",
    "meme对话",
    "q版插画",
    "情绪表达图",
    "meme连发",
    "用图回应",
    "mface发送",
    "图包回应",
    "媒体消息发送",
    "图片传输",
    "qq 机器人图片发送",
    "害羞表情",
    "多话题并行",
    "技术群日常",
    "幽默对话",
    "搞笑互动",
    "玩梗调侃",
    "群聊欢乐气氛",
    "群聊梗图",
    "轻松对抗",
    "轻松魔怔",
    "技术圈幽默",
    "相互调侃与回怼",
    "调侃斗嘴",
    "拌嘴",
    "玩笑式对抗",
    "呛声与抬杠",
    "嘲讽回击",
    "对线",
    "打闹",
    "玩梗斗嘴",
    "互怼调侃",
    "调侃互损",
    "挑衅互动",
    "挑衅",
    "叫板",
    "激将",
    "调侃回应",
    "对抗性互动",
    "群聊文化",
    "玩笑话",
    "玩笑要求",
    "群聊梗文化",
    "群聊流行语",
    "幽默图片",
    "社交媒体梗",
    "流行语",
    "网络流行语与梗",
    "抖音截图",
    "二次元表情",
    "登场",
    "meme",
    "萌系图片",
    "颜艺表情",
    "萌系表情",
    "萌系互动图",
    "瞳孔地震表情",
    "精神污染表情",
    "卡通图片",
    "猫娘图片",
    "q版图片",
    "色气图片",
    "猫耳少女图片",
    "沙雕图",
    "技术话题",
    "功能讨论",
    "技术话题讨论",
    "科技圈玩梗调侃",
    "熬夜话题",
    "凌晨话题",
    "深夜话题",
    "深夜唠嗑",
    "夜聊",
    "晚睡话题",
    "拟人化互动",
    "人格化互动",
    "扮演互动",
    "互动扮演",
    "拟人化调侃",
    "群聊扮演",
    "扮演对话",
    "机器人功能",
    "机器人功能讨论",
    "机器人能力",
    "机器人能力调侃",
    "机器人设定",
    "机器人特性",
    "机器人功能询问",
    "机器人回复",
    "机器人设计",
    "机器人功能表现",
    "机器人回复内容",
    "机器人性能玩梗",
    "机器人智商调侃",
    "bot能力吐槽",
    "qq机器人功能",
    "qq机器人操作",
    "群聊机器人功能",
    "玩梗互动",
    "调戏机器人",
    "调戏互动",
    "群友调戏",
    "逗bot",
    "群聊玩闹",
    "测试bot反应",
    "玩笑式互动",
    "毒舌调侃",
    "毒舌吐槽",
    "吐槽调侃",
    "玩梗回复",
    "机器人性格",
    "话题跳跃",
    "多用户对话",
    "多线程聊天",
    "群聊同时回复",
    "群聊多话题",
    "同时多个话题",
    "群聊切换",
    "多用户互动",
    "群聊多线",
    "群聊并行",
    "多人同时聊天",
    "多线聊天",
    "轻松吐槽",
    "氛围感调侃",
    "群内调戏",
    "群聊打趣",
    "幽默回应",
    "群聊气氛活跃",
    "调侃式互动",
    "调侃吐槽",
    "群聊拱火",
    "喵喵",
    "打call",
    "调侃ai",
    "找骂",
    "故意激怒",
    "针锋相对",
    "二次元图片",
    "动漫风格图片",
    "二次元话题",
    "动漫萌系图片",
    "二次元氛围",
    "猫娘动漫图片",
    "合并转发",
    "合并转发消息",
    "群聊转发",
    "转发消息",
    "消息转发",
    "消息合并转发",
    "转发聊天记录",
    "聊天记录分享",
    "聊天记录转发",
    "群内转发",
    "失传媒体",
    "旧聊天记录",
    "群聊截图",
    "群聊转发消息",
    "转发群聊",
    "图片转发",
    "长消息转发",
    "转发内容",
    "转发截图",
    "分享聊天记录",
    "转发记录",
    "合并消息",
    "转发对话",
    "转发聊天",
}



def normalize_behavior_tag_kind(raw_value: object) -> str:
    normalized_kind = " ".join(str(raw_value or "").lower().split()).strip()
    return TAG_KIND_ALIASES.get(normalized_kind, normalized_kind)


def normalize_behavior_tag_value(raw_value: object) -> str:
    return " ".join(str(raw_value or "").lower().split()).strip()


def is_behavior_generic_tag(tag_kind: object, tag_value: object) -> bool:
    normalized_kind = normalize_behavior_tag_kind(tag_kind)
    if normalized_kind != "domain":
        return False

    normalized_value = normalize_behavior_tag_value(tag_value)
    if not normalized_value:
        return False
    if normalized_value in GENERIC_DOMAIN_TAGS:
        return True

    if any(marker in normalized_value for marker in IMAGE_GENERIC_MARKERS):
        return not any(marker in normalized_value for marker in IMAGE_UNDERSTANDING_MARKERS)

    if "群聊" in normalized_value and any(marker in normalized_value for marker in GROUP_CHAT_GENERIC_MARKERS):
        return True
    if ("群友" in normalized_value or "群内" in normalized_value) and any(
        marker in normalized_value for marker in GROUP_CHAT_GENERIC_MARKERS
    ):
        return True
    if any(marker in normalized_value for marker in ("复读", "刷屏")):
        return True
    if len(normalized_value) <= 4 and any(marker == normalized_value for marker in SHORT_GENERIC_MARKERS):
        return True
    return False

logger = get_logger("database_migration")
LOW_DOMAIN_SCENE_DELETE_RATES = {
    1: 1.0,
    2: 0.75,
    3: 0.5,
}


def migrate_v30_to_v31(context: MigrationExecutionContext) -> None:
    """清理泛 tag 和低信息行为场景簇。"""

    context.start_progress(
        total_tables=3,
        total_records=_count_behavior_cleanup_rows(context.connection),
        description="v30 -> v31 迁移进度",
        table_unit_name="表",
        record_unit_name="记录",
    )
    behavior_cleanup_stats = _cleanup_behavior_scene_generic_tags(context.connection)
    context.advance_progress(
        records=behavior_cleanup_stats["tag_rows_deleted"],
        completed_tables=1,
        item_name="behavior_scene_tag_clusters",
    )
    context.advance_progress(
        records=behavior_cleanup_stats["scene_clusters_updated"] + behavior_cleanup_stats["scene_clusters_deleted"],
        completed_tables=1,
        item_name="behavior_scene_clusters",
    )
    context.advance_progress(
        records=behavior_cleanup_stats["behavior_paths_deleted"]
        + behavior_cleanup_stats["offline_import_records_deleted"],
        completed_tables=1,
        item_name="behavior_experience_paths",
    )
    logger.info(
        "v30 -> v31 数据库迁移完成：行为场景清理 tag=%s, 场景更新=%s, 场景删除=%s, 路径删除=%s, 导入记录删除=%s",
        behavior_cleanup_stats["tag_rows_deleted"],
        behavior_cleanup_stats["scene_clusters_updated"],
        behavior_cleanup_stats["scene_clusters_deleted"],
        behavior_cleanup_stats["behavior_paths_deleted"],
        behavior_cleanup_stats["offline_import_records_deleted"],
    )


def _count_behavior_cleanup_rows(connection: Connection) -> int:
    schema_inspector = SQLiteSchemaInspector()
    total_rows = 0
    for table_name in ("behavior_scene_tag_clusters", "behavior_scene_clusters"):
        if not schema_inspector.table_exists(connection, table_name):
            continue
        row = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        total_rows += int(row[0] or 0) if row is not None else 0
    return total_rows


def _cleanup_behavior_scene_generic_tags(connection: Connection) -> dict[str, int]:
    stats = {
        "tag_rows_deleted": 0,
        "scene_clusters_updated": 0,
        "behavior_paths_deleted": 0,
        "offline_import_records_deleted": 0,
        "scene_clusters_deleted": 0,
    }
    schema_inspector = SQLiteSchemaInspector()
    if not schema_inspector.table_exists(connection, "behavior_scene_tag_clusters"):
        return stats
    if not schema_inspector.table_exists(connection, "behavior_scene_clusters"):
        return stats

    cleanup_plan = _build_behavior_cleanup_plan(connection)
    stats["tag_rows_deleted"] = _delete_by_ids(
        connection,
        "behavior_scene_tag_clusters",
        "id",
        cleanup_plan["generic_tag_row_ids"],
    )

    deleted_scene_ids = {int(item["scene_cluster_id"]) for item in cleanup_plan["scene_deletes"]}
    for update_plan in cleanup_plan["scene_updates"]:
        scene_cluster_id = int(update_plan["scene_cluster_id"])
        if scene_cluster_id in deleted_scene_ids:
            continue
        cursor = connection.exec_driver_sql(
            """
            UPDATE behavior_scene_clusters
            SET tag_distribution = ?,
                update_time = ?
            WHERE id = ?
            """,
            (update_plan["new_distribution"], datetime.now().isoformat(timespec="seconds"), scene_cluster_id),
        )
        stats["scene_clusters_updated"] += int(cursor.rowcount or 0)

    scene_cluster_ids = sorted(deleted_scene_ids)
    stats["behavior_paths_deleted"] = _delete_paths_by_scene_ids(connection, scene_cluster_ids)
    stats["offline_import_records_deleted"] = _delete_import_records_by_scene_ids(connection, scene_cluster_ids)
    stats["scene_clusters_deleted"] = _delete_by_ids(
        connection,
        "behavior_scene_clusters",
        "id",
        scene_cluster_ids,
    )
    return stats


def _build_behavior_cleanup_plan(connection: Connection) -> dict[str, list[dict[str, Any]] | list[int]]:
    tag_rows = connection.exec_driver_sql(
        """
        SELECT id, tag_kind, tag, cluster_key, source_count
        FROM behavior_scene_tag_clusters
        ORDER BY id
        """
    ).mappings().all()
    scene_rows = connection.exec_driver_sql(
        """
        SELECT id, session_id, tag_distribution, source_count
        FROM behavior_scene_clusters
        ORDER BY id
        """
    ).mappings().all()

    rows_by_key: dict[tuple[str, str], list[Any]] = defaultdict(list)
    generic_tag_rows: list[Any] = []
    for row in tag_rows:
        key = (str(row["tag_kind"] or ""), str(row["cluster_key"] or ""))
        if key[0] and key[1]:
            rows_by_key[key].append(row)
        if is_behavior_generic_tag(row["tag_kind"], row["tag"]):
            generic_tag_rows.append(row)

    generic_tag_row_ids = {int(row["id"]) for row in generic_tag_rows}
    remaining_keys: set[tuple[str, str]] = set()
    emptied_keys: set[tuple[str, str]] = set()
    for key, rows in rows_by_key.items():
        remaining_rows = [row for row in rows if int(row["id"]) not in generic_tag_row_ids]
        if remaining_rows:
            remaining_keys.add(key)
        elif any(int(row["id"]) in generic_tag_row_ids for row in rows):
            emptied_keys.add(key)

    scene_updates: list[dict[str, Any]] = []
    scene_deletes: list[dict[str, Any]] = []
    for row in scene_rows:
        raw_items = _load_json_list(row["tag_distribution"])
        kept_items: list[dict[str, Any]] = []
        scene_changed = not raw_items
        for item in raw_items:
            if not isinstance(item, dict):
                scene_changed = True
                continue
            split_ref = _split_tag_ref(item.get("tag"))
            if split_ref is None:
                scene_changed = True
                continue
            if split_ref in emptied_keys or split_ref not in remaining_keys:
                scene_changed = True
                continue
            kept_items.append(item)

        new_distribution = _normalize_distribution(kept_items)
        old_distribution = str(row["tag_distribution"] or "[]")
        normalized_items = [item for item in _load_json_list(new_distribution) if isinstance(item, dict)]
        if new_distribution == "[]" and scene_changed:
            scene_deletes.append({"scene_cluster_id": int(row["id"])})
        elif _low_signal_scene_delete_reason(normalized_items):
            scene_deletes.append({"scene_cluster_id": int(row["id"])})
        elif scene_changed and new_distribution != old_distribution:
            scene_updates.append(
                {
                    "scene_cluster_id": int(row["id"]),
                    "new_distribution": new_distribution,
                }
            )

    return {
        "generic_tag_row_ids": sorted(generic_tag_row_ids),
        "scene_updates": scene_updates,
        "scene_deletes": scene_deletes,
    }


def _delete_by_ids(connection: Connection, table_name: str, column_name: str, ids: Sequence[int]) -> int:
    deleted_count = 0
    for batch in _iter_batches(list(ids)):
        placeholders = ",".join("?" for _ in batch)
        cursor = connection.exec_driver_sql(
            f"DELETE FROM {table_name} WHERE {column_name} IN ({placeholders})",
            tuple(batch),
        )
        deleted_count += int(cursor.rowcount or 0)
    return deleted_count


def _delete_paths_by_scene_ids(connection: Connection, scene_cluster_ids: Sequence[int]) -> int:
    schema_inspector = SQLiteSchemaInspector()
    if not scene_cluster_ids or not schema_inspector.table_exists(connection, "behavior_experience_paths"):
        return 0
    deleted_count = 0
    for batch in _iter_batches(list(scene_cluster_ids)):
        placeholders = ",".join("?" for _ in batch)
        cursor = connection.exec_driver_sql(
            f"DELETE FROM behavior_experience_paths WHERE scene_cluster_id IN ({placeholders})",
            tuple(batch),
        )
        deleted_count += int(cursor.rowcount or 0)
    return deleted_count


def _delete_import_records_by_scene_ids(connection: Connection, scene_cluster_ids: Sequence[int]) -> int:
    schema_inspector = SQLiteSchemaInspector()
    if not scene_cluster_ids or not schema_inspector.table_exists(connection, "behavior_offline_import_records"):
        return 0

    table_schema = schema_inspector.get_table_schema(connection, "behavior_offline_import_records")
    columns = [
        column_name
        for column_name in ("target_scene_cluster_id", "source_scene_cluster_id")
        if table_schema.has_column(column_name)
    ]
    if not columns:
        return 0

    deleted_count = 0
    for batch in _iter_batches(list(scene_cluster_ids)):
        placeholders = ",".join("?" for _ in batch)
        where_clause = " OR ".join(f"{column_name} IN ({placeholders})" for column_name in columns)
        params: list[int] = []
        for _ in columns:
            params.extend(batch)
        cursor = connection.exec_driver_sql(
            f"DELETE FROM behavior_offline_import_records WHERE {where_clause}",
            tuple(params),
        )
        deleted_count += int(cursor.rowcount or 0)
    return deleted_count


def _load_json_list(raw_value: Any) -> list[Any]:
    if isinstance(raw_value, list):
        return raw_value
    if not isinstance(raw_value, str) or not raw_value.strip():
        return []
    try:
        parsed_value = json.loads(raw_value)
    except (TypeError, ValueError):
        return []
    return parsed_value if isinstance(parsed_value, list) else []


def _split_tag_ref(raw_value: Any) -> tuple[str, str] | None:
    tag_ref = str(raw_value or "").strip()
    if ":" not in tag_ref:
        return None
    tag_kind, cluster_key = tag_ref.split(":", 1)
    tag_kind = tag_kind.strip()
    cluster_key = cluster_key.strip()
    if not tag_kind or not cluster_key:
        return None
    return tag_kind, cluster_key


def _normalize_distribution(items: Sequence[dict[str, Any]]) -> str:
    weighted_items: list[tuple[str, float]] = []
    for item in items:
        tag_ref = str(item.get("tag")).strip()
        if not tag_ref:
            continue
        try:
            probability = float(item.get("probability") or 0.0)
        except (TypeError, ValueError) as exc:
            # P0-5: probability 解析失败出声（debug 防刷屏，跳过）（ZG-31）
            logger.debug("probability 解析失败，跳过: %s", exc)
            continue
        if probability <= 0:
            continue
        weighted_items.append((tag_ref, probability))

    total_probability = sum(probability for _, probability in weighted_items)
    if total_probability <= 0:
        return "[]"
    normalized_items = [
        {"tag": tag_ref, "probability": round(probability / total_probability, 6)}
        for tag_ref, probability in sorted(weighted_items)
    ]
    return json.dumps(normalized_items, ensure_ascii=False, sort_keys=True)


def _low_signal_scene_delete_reason(items: Sequence[dict[str, Any]]) -> str:
    domain_ref_count = 0
    for item in items:
        split_ref = _split_tag_ref(item.get("tag"))
        if split_ref is None:
            continue
        tag_kind, _ = split_ref
        if tag_kind == "domain":
            domain_ref_count += 1

    if domain_ref_count == 0:
        return "no_domain_tag"
    delete_rate = LOW_DOMAIN_SCENE_DELETE_RATES.get(domain_ref_count, 0.0)
    if delete_rate >= 1.0 or random.random() < delete_rate:
        return f"{domain_ref_count}_domain_random_delete"
    return ""


def _iter_batches(values: Sequence[int], *, batch_size: int = 500) -> Sequence[list[int]]:
    return [list(values[index : index + batch_size]) for index in range(0, len(values), batch_size)]
