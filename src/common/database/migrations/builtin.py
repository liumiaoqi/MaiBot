"""数据库迁移内置版本与默认注册表。"""

from typing import List, Optional

from .legacy_v1_to_v2 import migrate_legacy_v1_to_v2
from .models import DatabaseSchemaSnapshot, MigrationStep
from .registry import MigrationRegistry
from .resolver import BaseSchemaVersionDetector, SchemaVersionResolver
from .schema import SQLiteSchemaInspector
from .v2_to_v3 import migrate_v2_to_v3
from .v3_to_v4 import migrate_v3_to_v4
from .v4_to_v5 import migrate_v4_to_v5
from .v5_to_v6 import migrate_v5_to_v6
from .v6_to_v7 import migrate_v6_to_v7
from .v7_to_v8 import migrate_v7_to_v8
from .v8_to_v9 import migrate_v8_to_v9
from .v9_to_v10 import migrate_v9_to_v10
from .v10_to_v11 import migrate_v10_to_v11
from .v11_to_v12 import migrate_v11_to_v12
from .v12_to_v13 import migrate_v12_to_v13
from .version_store import SQLiteUserVersionStore

EMPTY_SCHEMA_VERSION = 0
LEGACY_V1_SCHEMA_VERSION = 1
V2_SCHEMA_VERSION = 2
V3_SCHEMA_VERSION = 3
V4_SCHEMA_VERSION = 4
V5_SCHEMA_VERSION = 5
V6_SCHEMA_VERSION = 6
V7_SCHEMA_VERSION = 7
V8_SCHEMA_VERSION = 8
V9_SCHEMA_VERSION = 9
V10_SCHEMA_VERSION = 10
V11_SCHEMA_VERSION = 11
V12_SCHEMA_VERSION = 12
LATEST_SCHEMA_VERSION = 13

_LEGACY_V1_EXCLUSIVE_TABLES = (
    "chat_streams",
    "emoji",
    "emoji_description_cache",
    "expression",
    "group_info",
    "image_descriptions",
    "jargon",
    "messages",
    "thinking_back",
)
_COMMON_MARKER_TABLES = (
    "mai_messages",
    "chat_sessions",
    "expressions",
    "jargons",
    "tool_records",
)


class LatestSchemaVersionDetector(BaseSchemaVersionDetector):
    """当前最新 schema 结构探测器。"""

    @property
    def name(self) -> str:
        """返回探测器名称。

        Returns:
            str: 当前探测器名称。
        """

        return "latest_schema_detector"

    def detect_version(self, snapshot: DatabaseSchemaSnapshot) -> Optional[int]:
        """检测数据库是否已经是当前最新结构。

        Args:
            snapshot: 当前数据库结构快照。

        Returns:
            Optional[int]: 若识别为最新结构则返回最新版本号，否则返回 ``None``。
        """

        if any(snapshot.has_table(table_name) for table_name in _LEGACY_V1_EXCLUSIVE_TABLES):
            return None
        if not all(snapshot.has_table(table_name) for table_name in _COMMON_MARKER_TABLES):
            return None
        if snapshot.has_table("action_records"):
            return None
        if snapshot.has_table("thinking_questions"):
            return None
        if snapshot.has_column("images", "emotion"):
            return None
        if not snapshot.has_column("images", "image_hash"):
            return None
        if not snapshot.has_column("images", "full_path"):
            return None
        if not snapshot.has_column("images", "image_type"):
            return None
        if not snapshot.has_column("chat_history", "session_id"):
            return None
        if not snapshot.has_column("person_info", "user_nickname"):
            return None
        if not snapshot.has_column("chat_sessions", "account_id"):
            return None
        if not snapshot.has_column("chat_sessions", "scope"):
            return None
        if not snapshot.has_column("chat_sessions", "user_nickname"):
            return None
        if not snapshot.has_column("chat_sessions", "user_cardname"):
            return None
        if not snapshot.has_column("chat_sessions", "group_name"):
            return None
        if snapshot.has_column("expressions", "rejected"):
            return None
        if snapshot.has_column("mai_messages", "display_message"):
            return None
        if not snapshot.has_table("statistics_message_hourly"):
            return None
        if not snapshot.has_table("statistics_tool_hourly"):
            return None
        if not snapshot.has_table("statistics_model_hourly"):
            return None
        if not snapshot.has_table("statistics_aggregation_cursors"):
            return None
        if not snapshot.has_column("jargons", "created_timestamp"):
            return None
        if not snapshot.has_column("jargons", "updated_timestamp"):
            return None
        if snapshot.has_column("jargons", "inference_with_context"):
            return None
        if snapshot.has_column("jargons", "inference_with_content_only"):
            return None
        if not snapshot.has_column("jargons", "created_by"):
            return None
        return LATEST_SCHEMA_VERSION


class V12SchemaVersionDetector(BaseSchemaVersionDetector):
    """v12 schema 结构探测器。"""

    @property
    def name(self) -> str:
        return "v12_schema_detector"

    def detect_version(self, snapshot: DatabaseSchemaSnapshot) -> Optional[int]:
        """检测数据库是否为 v12 结构。"""

        if any(snapshot.has_table(table_name) for table_name in _LEGACY_V1_EXCLUSIVE_TABLES):
            return None
        if not all(snapshot.has_table(table_name) for table_name in _COMMON_MARKER_TABLES):
            return None
        if snapshot.has_table("action_records"):
            return None
        if snapshot.has_table("thinking_questions"):
            return None
        if snapshot.has_column("images", "emotion"):
            return None
        if not snapshot.has_column("images", "image_hash"):
            return None
        if not snapshot.has_column("images", "full_path"):
            return None
        if not snapshot.has_column("images", "image_type"):
            return None
        if not snapshot.has_column("chat_history", "session_id"):
            return None
        if not snapshot.has_column("person_info", "user_nickname"):
            return None
        if not snapshot.has_column("chat_sessions", "account_id"):
            return None
        if not snapshot.has_column("chat_sessions", "scope"):
            return None
        if not snapshot.has_column("chat_sessions", "user_nickname"):
            return None
        if not snapshot.has_column("chat_sessions", "user_cardname"):
            return None
        if not snapshot.has_column("chat_sessions", "group_name"):
            return None
        if snapshot.has_column("expressions", "rejected"):
            return None
        if snapshot.has_column("mai_messages", "display_message"):
            return None
        if not snapshot.has_table("statistics_message_hourly"):
            return None
        if not snapshot.has_table("statistics_tool_hourly"):
            return None
        if not snapshot.has_table("statistics_model_hourly"):
            return None
        if not snapshot.has_table("statistics_aggregation_cursors"):
            return None
        if not snapshot.has_column("jargons", "created_timestamp"):
            return None
        if not snapshot.has_column("jargons", "updated_timestamp"):
            return None
        if snapshot.has_column("jargons", "inference_with_context"):
            return None
        if snapshot.has_column("jargons", "inference_with_content_only"):
            return None
        if snapshot.has_column("jargons", "created_by"):
            return None
        return V12_SCHEMA_VERSION


class V11SchemaVersionDetector(BaseSchemaVersionDetector):
    """v11 schema 结构探测器。"""

    @property
    def name(self) -> str:
        return "v11_schema_detector"

    def detect_version(self, snapshot: DatabaseSchemaSnapshot) -> Optional[int]:
        """检测数据库是否为 v11 结构。"""

        if any(snapshot.has_table(table_name) for table_name in _LEGACY_V1_EXCLUSIVE_TABLES):
            return None
        if not all(snapshot.has_table(table_name) for table_name in _COMMON_MARKER_TABLES):
            return None
        if snapshot.has_table("action_records"):
            return None
        if snapshot.has_table("thinking_questions"):
            return None
        if snapshot.has_column("images", "emotion"):
            return None
        if not snapshot.has_column("images", "image_hash"):
            return None
        if not snapshot.has_column("images", "full_path"):
            return None
        if not snapshot.has_column("images", "image_type"):
            return None
        if not snapshot.has_column("chat_history", "session_id"):
            return None
        if not snapshot.has_column("person_info", "user_nickname"):
            return None
        if not snapshot.has_column("chat_sessions", "account_id"):
            return None
        if not snapshot.has_column("chat_sessions", "scope"):
            return None
        if not snapshot.has_column("chat_sessions", "user_nickname"):
            return None
        if not snapshot.has_column("chat_sessions", "user_cardname"):
            return None
        if not snapshot.has_column("chat_sessions", "group_name"):
            return None
        if snapshot.has_column("expressions", "rejected"):
            return None
        if snapshot.has_column("mai_messages", "display_message"):
            return None
        if not snapshot.has_table("statistics_message_hourly"):
            return None
        if not snapshot.has_table("statistics_tool_hourly"):
            return None
        if not snapshot.has_table("statistics_model_hourly"):
            return None
        if not snapshot.has_table("statistics_aggregation_cursors"):
            return None
        if not snapshot.has_column("jargons", "created_timestamp"):
            return None
        if not snapshot.has_column("jargons", "updated_timestamp"):
            return None
        has_jargon_inference_cache = snapshot.has_column(
            "jargons", "inference_with_context"
        ) or snapshot.has_column("jargons", "inference_with_content_only")
        if not has_jargon_inference_cache:
            return None
        return V11_SCHEMA_VERSION


class V10SchemaVersionDetector(BaseSchemaVersionDetector):
    """v10 schema 结构探测器。"""

    @property
    def name(self) -> str:
        return "v10_schema_detector"

    def detect_version(self, snapshot: DatabaseSchemaSnapshot) -> Optional[int]:
        """检测数据库是否为 v10 结构。"""

        if any(snapshot.has_table(table_name) for table_name in _LEGACY_V1_EXCLUSIVE_TABLES):
            return None
        if not all(snapshot.has_table(table_name) for table_name in _COMMON_MARKER_TABLES):
            return None
        if snapshot.has_table("action_records"):
            return None
        if snapshot.has_table("thinking_questions"):
            return None
        if snapshot.has_column("images", "emotion"):
            return None
        if not snapshot.has_column("images", "image_hash"):
            return None
        if not snapshot.has_column("images", "full_path"):
            return None
        if not snapshot.has_column("images", "image_type"):
            return None
        if not snapshot.has_column("chat_history", "session_id"):
            return None
        if not snapshot.has_column("person_info", "user_nickname"):
            return None
        if not snapshot.has_column("chat_sessions", "account_id"):
            return None
        if not snapshot.has_column("chat_sessions", "scope"):
            return None
        if not snapshot.has_column("chat_sessions", "user_nickname"):
            return None
        if not snapshot.has_column("chat_sessions", "user_cardname"):
            return None
        if not snapshot.has_column("chat_sessions", "group_name"):
            return None
        if snapshot.has_column("expressions", "rejected"):
            return None
        if snapshot.has_column("mai_messages", "display_message"):
            return None
        if not snapshot.has_table("statistics_message_hourly"):
            return None
        if not snapshot.has_table("statistics_tool_hourly"):
            return None
        if not snapshot.has_table("statistics_model_hourly"):
            return None
        if not snapshot.has_table("statistics_aggregation_cursors"):
            return None
        has_jargon_created_timestamp = snapshot.has_column("jargons", "created_timestamp")
        has_jargon_updated_timestamp = snapshot.has_column("jargons", "updated_timestamp")
        if has_jargon_created_timestamp and has_jargon_updated_timestamp:
            return None
        return V10_SCHEMA_VERSION


class V9SchemaVersionDetector(BaseSchemaVersionDetector):
    """v9 schema 结构探测器。"""

    @property
    def name(self) -> str:
        return "v9_schema_detector"

    def detect_version(self, snapshot: DatabaseSchemaSnapshot) -> Optional[int]:
        """检测数据库是否为 v9 结构。"""

        if any(snapshot.has_table(table_name) for table_name in _LEGACY_V1_EXCLUSIVE_TABLES):
            return None
        if not all(snapshot.has_table(table_name) for table_name in _COMMON_MARKER_TABLES):
            return None
        if snapshot.has_table("action_records"):
            return None
        if snapshot.has_table("thinking_questions"):
            return None
        if snapshot.has_column("images", "emotion"):
            return None
        if not snapshot.has_column("images", "image_hash"):
            return None
        if not snapshot.has_column("images", "full_path"):
            return None
        if not snapshot.has_column("images", "image_type"):
            return None
        if not snapshot.has_column("chat_history", "session_id"):
            return None
        if not snapshot.has_column("person_info", "user_nickname"):
            return None
        if not snapshot.has_column("chat_sessions", "account_id"):
            return None
        if not snapshot.has_column("chat_sessions", "scope"):
            return None
        if snapshot.has_column("chat_sessions", "user_nickname"):
            return None
        if snapshot.has_column("chat_sessions", "user_cardname"):
            return None
        if snapshot.has_column("chat_sessions", "group_name"):
            return None
        if snapshot.has_column("expressions", "rejected"):
            return None
        if snapshot.has_column("mai_messages", "display_message"):
            return None
        if not snapshot.has_table("statistics_message_hourly"):
            return None
        if not snapshot.has_table("statistics_tool_hourly"):
            return None
        if not snapshot.has_table("statistics_model_hourly"):
            return None
        if not snapshot.has_table("statistics_aggregation_cursors"):
            return None
        return V9_SCHEMA_VERSION


class V6SchemaVersionDetector(BaseSchemaVersionDetector):
    """v6 schema 缁撴瀯鎺㈡祴鍣ㄣ€?"""

    @property
    def name(self) -> str:
        return "v6_schema_detector"

    def detect_version(self, snapshot: DatabaseSchemaSnapshot) -> Optional[int]:
        """妫€娴嬫暟鎹簱鏄惁涓?v6 缁撴瀯銆?"""

        if any(snapshot.has_table(table_name) for table_name in _LEGACY_V1_EXCLUSIVE_TABLES):
            return None
        if not all(snapshot.has_table(table_name) for table_name in _COMMON_MARKER_TABLES):
            return None
        if snapshot.has_table("action_records"):
            return None
        if snapshot.has_table("thinking_questions"):
            return None
        if snapshot.has_column("images", "emotion"):
            return None
        if not snapshot.has_column("images", "image_hash"):
            return None
        if not snapshot.has_column("images", "full_path"):
            return None
        if not snapshot.has_column("images", "image_type"):
            return None
        if not snapshot.has_column("chat_history", "session_id"):
            return None
        if not snapshot.has_column("person_info", "user_nickname"):
            return None
        if not snapshot.has_column("chat_sessions", "account_id"):
            return None
        if not snapshot.has_column("chat_sessions", "scope"):
            return None
        if not snapshot.has_column("expressions", "rejected"):
            return None
        if snapshot.has_column("mai_messages", "display_message"):
            return None
        return V6_SCHEMA_VERSION


class V5SchemaVersionDetector(BaseSchemaVersionDetector):
    """v5 schema 结构探测器。"""

    @property
    def name(self) -> str:
        return "v5_schema_detector"

    def detect_version(self, snapshot: DatabaseSchemaSnapshot) -> Optional[int]:
        """检测数据库是否为 v5 结构。"""

        if any(snapshot.has_table(table_name) for table_name in _LEGACY_V1_EXCLUSIVE_TABLES):
            return None
        if not all(snapshot.has_table(table_name) for table_name in _COMMON_MARKER_TABLES):
            return None
        if snapshot.has_table("action_records"):
            return None
        if snapshot.has_table("thinking_questions"):
            return None
        if snapshot.has_column("images", "emotion"):
            return None
        if not snapshot.has_column("images", "image_hash"):
            return None
        if not snapshot.has_column("images", "full_path"):
            return None
        if not snapshot.has_column("images", "image_type"):
            return None
        if not snapshot.has_column("chat_history", "session_id"):
            return None
        if not snapshot.has_column("person_info", "user_nickname"):
            return None
        if snapshot.has_column("mai_messages", "display_message"):
            return None
        if snapshot.has_column("chat_sessions", "account_id") or snapshot.has_column("chat_sessions", "scope"):
            return None
        return V5_SCHEMA_VERSION


class V3SchemaVersionDetector(BaseSchemaVersionDetector):
    """v3 schema 结构探测器。"""

    @property
    def name(self) -> str:
        return "v3_schema_detector"

    def detect_version(self, snapshot: DatabaseSchemaSnapshot) -> Optional[int]:
        """检测数据库是否为 v3 结构。"""

        if any(snapshot.has_table(table_name) for table_name in _LEGACY_V1_EXCLUSIVE_TABLES):
            return None
        if not all(snapshot.has_table(table_name) for table_name in _COMMON_MARKER_TABLES):
            return None
        if snapshot.has_table("action_records"):
            return None
        if snapshot.has_table("thinking_questions"):
            return None
        if snapshot.has_column("images", "emotion"):
            return None
        if not snapshot.has_column("images", "image_hash"):
            return None
        if not snapshot.has_column("images", "full_path"):
            return None
        if not snapshot.has_column("images", "image_type"):
            return None
        if not snapshot.has_column("chat_history", "session_id"):
            return None
        if not snapshot.has_column("person_info", "user_nickname"):
            return None
        if not snapshot.has_column("mai_messages", "display_message"):
            return None
        return V3_SCHEMA_VERSION


class V2SchemaVersionDetector(BaseSchemaVersionDetector):
    """v2 schema 结构探测器。"""

    @property
    def name(self) -> str:
        """返回探测器名称。

        Returns:
            str: 当前探测器名称。
        """

        return "v2_schema_detector"

    def detect_version(self, snapshot: DatabaseSchemaSnapshot) -> Optional[int]:
        """检测数据库是否为 v2 结构。

        Args:
            snapshot: 当前数据库结构快照。

        Returns:
            Optional[int]: 若识别为 v2 结构则返回 ``2``，否则返回 ``None``。
        """

        if any(snapshot.has_table(table_name) for table_name in _LEGACY_V1_EXCLUSIVE_TABLES):
            return None
        if not all(snapshot.has_table(table_name) for table_name in _COMMON_MARKER_TABLES):
            return None
        if not snapshot.has_table("action_records"):
            return None
        if not snapshot.has_table("thinking_questions"):
            return None
        if not snapshot.has_column("images", "emotion"):
            return None
        if not snapshot.has_column("action_records", "session_id"):
            return None
        if not snapshot.has_column("chat_history", "session_id"):
            return None
        if not snapshot.has_column("person_info", "user_nickname"):
            return None
        return V2_SCHEMA_VERSION


class LegacyV1SchemaDetector(BaseSchemaVersionDetector):
    """旧版 ``0.x`` schema 结构探测器。"""

    @property
    def name(self) -> str:
        """返回探测器名称。

        Returns:
            str: 当前探测器名称。
        """

        return "legacy_v1_schema_detector"

    def detect_version(self, snapshot: DatabaseSchemaSnapshot) -> Optional[int]:
        """检测数据库是否为旧版 ``0.x`` 结构。

        Args:
            snapshot: 当前数据库结构快照。

        Returns:
            Optional[int]: 若识别为旧版结构则返回 ``1``，否则返回 ``None``。
        """

        if any(snapshot.has_table(table_name) for table_name in _LEGACY_V1_EXCLUSIVE_TABLES):
            return LEGACY_V1_SCHEMA_VERSION

        legacy_shared_markers = (
            ("action_records", ("chat_id", "time")),
            ("chat_history", ("chat_id", "original_text")),
            ("images", ("emoji_hash", "path", "type")),
            ("llm_usage", ("model_api_provider", "status")),
            ("online_time", ("duration",)),
            ("person_info", ("nickname", "group_nick_name")),
        )
        for table_name, required_columns in legacy_shared_markers:
            if snapshot.has_table(table_name) and all(
                snapshot.has_column(table_name, column_name) for column_name in required_columns
            ):
                return LEGACY_V1_SCHEMA_VERSION
        return None


def build_default_schema_version_detectors() -> List[BaseSchemaVersionDetector]:
    """构建默认 schema 版本探测器链。

    Returns:
        List[BaseSchemaVersionDetector]: 按优先级排序的探测器列表。
    """

    return [
        LatestSchemaVersionDetector(),
        V12SchemaVersionDetector(),
        V11SchemaVersionDetector(),
        V10SchemaVersionDetector(),
        V9SchemaVersionDetector(),
        V6SchemaVersionDetector(),
        V5SchemaVersionDetector(),
        V3SchemaVersionDetector(),
        V2SchemaVersionDetector(),
        LegacyV1SchemaDetector(),
    ]


def build_default_schema_version_resolver() -> SchemaVersionResolver:
    """构建默认 schema 版本解析器。

    Returns:
        SchemaVersionResolver: 配置完成的 schema 版本解析器。
    """

    return SchemaVersionResolver(
        version_store=SQLiteUserVersionStore(),
        schema_inspector=SQLiteSchemaInspector(),
        detectors=build_default_schema_version_detectors(),
    )


def build_default_migration_registry() -> MigrationRegistry:
    """构建默认迁移步骤注册表。

    Returns:
        MigrationRegistry: 含默认迁移步骤的注册表实例。
    """

    return MigrationRegistry(
        steps=[
            MigrationStep(
                version_from=LEGACY_V1_SCHEMA_VERSION,
                version_to=V2_SCHEMA_VERSION,
                name="legacy_v1_to_v2",
                description="将旧版 0.x 数据库迁移到 v2 schema。",
                handler=migrate_legacy_v1_to_v2,
            ),
            MigrationStep(
                version_from=V2_SCHEMA_VERSION,
                version_to=V3_SCHEMA_VERSION,
                name="v2_to_v3",
                description="移除废弃表，并将 emoji 标签统一收敛到 description 字段。",
                handler=migrate_v2_to_v3,
            ),
            MigrationStep(
                version_from=V3_SCHEMA_VERSION,
                version_to=V4_SCHEMA_VERSION,
                name="v3_to_v4",
                description="移除 mai_messages.display_message 弃用列。",
                handler=migrate_v3_to_v4,
            ),
            MigrationStep(
                version_from=V4_SCHEMA_VERSION,
                version_to=V5_SCHEMA_VERSION,
                name="v4_to_v5",
                description="清空群聊 chat_sessions.user_id，避免把首个发言人误认为聊天流归属。",
                handler=migrate_v4_to_v5,
            ),
            MigrationStep(
                version_from=V5_SCHEMA_VERSION,
                version_to=V6_SCHEMA_VERSION,
                name="v5_to_v6",
                description="为 chat_sessions 增加 account_id/scope 路由归属字段。",
                handler=migrate_v5_to_v6,
            ),
            MigrationStep(
                version_from=V6_SCHEMA_VERSION,
                version_to=V7_SCHEMA_VERSION,
                name="v6_to_v7",
                description="移除 expressions.rejected 列，并删除已审核拒绝的表达方式。",
                handler=migrate_v6_to_v7,
            ),
            MigrationStep(
                version_from=V7_SCHEMA_VERSION,
                version_to=V8_SCHEMA_VERSION,
                name="v7_to_v8",
                description="将 AI 标记的已审核表达方式改回待人工审核。",
                handler=migrate_v7_to_v8,
            ),
            MigrationStep(
                version_from=V8_SCHEMA_VERSION,
                version_to=V9_SCHEMA_VERSION,
                name="v8_to_v9",
                description="新增统计汇总表、索引与历史统计回填。",
                handler=migrate_v8_to_v9,
            ),
            MigrationStep(
                version_from=V9_SCHEMA_VERSION,
                version_to=V10_SCHEMA_VERSION,
                name="v9_to_v10",
                description="为 chat_sessions 增加群名与私聊用户展示名字段。",
                handler=migrate_v9_to_v10,
            ),
            MigrationStep(
                version_from=V10_SCHEMA_VERSION,
                version_to=V11_SCHEMA_VERSION,
                name="v10_to_v11",
                description="为 jargons 增加创建时间和更新时间字段。",
                handler=migrate_v10_to_v11,
            ),
            MigrationStep(
                version_from=V11_SCHEMA_VERSION,
                version_to=V12_SCHEMA_VERSION,
                name="v11_to_v12",
                description="移除 jargons 中不再持久化的推理过程缓存字段。",
                handler=migrate_v11_to_v12,
            ),
            MigrationStep(
                version_from=V12_SCHEMA_VERSION,
                version_to=LATEST_SCHEMA_VERSION,
                name="v12_to_v13",
                description="为 jargons 增加创建来源字段。",
                handler=migrate_v12_to_v13,
            ),
        ]
    )
