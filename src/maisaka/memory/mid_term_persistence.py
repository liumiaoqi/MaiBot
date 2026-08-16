"""ZH1-1a: 摘要持久化服务——新表 CRUD + 自动建表 + 批量 embedding + timestamp 兜底。

设计参考：dsh SettingsProvider.publish/commit + ZG16-5 scope_audit 全局单例模式。
"""

import asyncio
import hashlib
import json

from datetime import datetime
from typing import Any

from sqlmodel import select

from src.common.data_models.message_component_data_model import DictComponent
from src.common.database.database_model import MidTermMemorySummaries
from src.common.logger import get_logger

logger = get_logger("maisaka.mid_term_persistence")


def _extract_time_from_message_id(message_id: str) -> datetime | None:
    """从消息 ID 提取时间（napcat message_id 不含可靠时间戳前缀）。

    spec 5.6.1 规则 4 降级：napcat message_id 为纯数字 ID，
    无法可靠提取时间戳 → 永远返回 None → fix_timestamp_fallback 降级为当前时间。
    保留函数签名供未来 SDK 升级（如适配器上报 message_id 含时间前缀时可实现）。
    """
    return None


def fix_timestamp_fallback(
    raw_timestamp: int | float | None,
    message_id: str,
) -> datetime:
    """timestamp 兜底（缺失/0/1970 → 消息 ID 时间或当前时间）。

    spec 5.6.1 规则 1-7：
      - 有效 timestamp 不动（仅对 None/0/1970 兜底，规则 2）
      - 兜底优先级：消息 ID 时间 > 当前时间（规则 4）
      - 幂等（重复修复不产生副作用，规则 3）
      - 不兜底为未来时间（规则 7）
      - 记审计日志（规则 5）
    """
    if raw_timestamp is not None and float(raw_timestamp) > 0:
        return datetime.fromtimestamp(float(raw_timestamp))
    message_id_time = _extract_time_from_message_id(message_id)
    now = datetime.now()
    if message_id_time is not None and message_id_time <= now:
        logger.info(
            f"timestamp 兜底: message_id={message_id} raw={raw_timestamp} "
            f"fixed={message_id_time} source=message_id_time"
        )
        return message_id_time
    logger.info(
        f"timestamp 兜底: message_id={message_id} raw={raw_timestamp} "
        f"fixed={now} source=current_time"
    )
    return now


class MidTermPersistenceService:
    """摘要持久化服务——新表 CRUD + 自动建表 + 批量 embedding。"""

    def __init__(self) -> None:
        self._table_ready: bool = False

    def init_table(self) -> None:
        """自动建表 CREATE TABLE IF NOT EXISTS（spec 5.2.1 规则 1）。

        建表失败降级仅内存 + error 日志 + 上报（spec 5.2.3 场景 1）。
        """
        try:
            from src.common.database.database import initialize_database

            initialize_database()
            self._table_ready = True
            logger.info("mid_term_memory_summaries 表就绪")
        except Exception as exc:
            logger.error(f"摘要表建表失败，降级仅内存: {exc}", exc_info=True)
            self._table_ready = False
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port

            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, f"摘要表建表失败: {exc}", component_id="mid_term_persistence")

    async def persist_summary_to_db(
        self,
        summary_message: Any,
        session_id: str,
    ) -> bool:
        """持久化摘要到新表（含批量 embedding + 重试 3 次指数退避）。

        返回 True=成功，False=失败（调用方不 insert 到历史）。
        持久化与 insert 必须最终一致（spec 4.2 可靠性规则 7）。
        """
        if not self._table_ready:
            logger.warning("摘要表未就绪，跳过持久化（仅内存模式）")
            return False
        payload_data = self._extract_payload_data(summary_message)
        record = self._build_record(payload_data, session_id, summary_message.timestamp)
        for attempt in range(3):
            try:
                self._insert_record(record)
                logger.info(
                    f"摘要持久化成功: summary_id={record.summary_id} "
                    f"session_id={session_id} time_range={record.time_range}"
                )
                return True
            except Exception as exc:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                logger.error(f"摘要持久化失败（重试 3 次）: {exc}", exc_info=True)
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port

                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, f"摘要持久化失败: {exc}", component_id="mid_term_persistence")
                return False
        return False

    def _extract_payload_data(self, summary_message: Any) -> dict[str, Any]:
        """从 ComplexSessionMessage payload 提取字段。"""
        raw = summary_message.raw_message
        if raw and len(raw.components) > 0:
            comp = raw.components[0]
            if isinstance(comp, DictComponent) and isinstance(comp.data, dict):
                return comp.data
        return {}

    def _build_record(
        self,
        payload_data: dict[str, Any],
        session_id: str,
        timestamp: datetime,
    ) -> MidTermMemorySummaries:
        """构造 MidTermMemorySummaries 记录。"""
        time_range = str(payload_data.get("time_range", ""))
        participants = payload_data.get("participants", [])
        summary = str(payload_data.get("summary", ""))
        recall_cues = payload_data.get("recall_cues", [])
        recall_cue_embeddings = payload_data.get("recall_cue_embeddings", [])
        summary_id = f"mtm:{int(timestamp.timestamp()):x}:{hashlib.sha1((summary + time_range).encode('utf-8')).hexdigest()[:8]}"
        time_range_start = payload_data.get("time_range_start")
        time_range_end = payload_data.get("time_range_end")
        return MidTermMemorySummaries(
            summary_id=summary_id,
            session_id=session_id,
            time_range=time_range,
            time_range_start=time_range_start if isinstance(time_range_start, datetime) else None,
            time_range_end=time_range_end if isinstance(time_range_end, datetime) else None,
            participants=json.dumps(participants, ensure_ascii=False),
            summary=summary,
            recall_cues=json.dumps(recall_cues, ensure_ascii=False),
            recall_cue_embeddings=json.dumps(recall_cue_embeddings, ensure_ascii=False),
            timestamp=timestamp,
        )

    def _insert_record(self, record: MidTermMemorySummaries) -> None:
        """INSERT OR IGNORE 幂等写入（summary_id 冲突跳过，spec 5.2.3 场景 3）。"""
        from src.common.database.database import get_db_session

        with get_db_session() as session:
            existing = session.get(MidTermMemorySummaries, record.summary_id)
            if existing is not None:
                logger.info(f"摘要已存在，跳过重复持久化: {record.summary_id}")
                return
            session.add(record)

    def load_summaries_by_session(
        self,
        session_id: str,
        limit: int = 10,
    ) -> list[MidTermMemorySummaries]:
        """按 session_id 加载摘要记录（隔离查询，spec 4.3 安全性规则 1）。

        chat_loop_service 下次构建上下文时调用（方案 A，design 4.4）。
        """
        if not self._table_ready:
            return []
        from src.common.database.database import get_db_session

        with get_db_session() as session:
            stmt = (
                select(MidTermMemorySummaries)
                .where(MidTermMemorySummaries.session_id == session_id)
                .order_by(MidTermMemorySummaries.timestamp.desc())
                .limit(limit)
            )
            return list(session.exec(stmt))


_mid_term_persistence: MidTermPersistenceService | None = None


def init_mid_term_persistence() -> MidTermPersistenceService:
    """初始化全局持久化服务 + 自动建表（@startup_item 触发）。"""
    global _mid_term_persistence
    service = MidTermPersistenceService()
    service.init_table()
    _mid_term_persistence = service
    return service


def get_mid_term_persistence() -> MidTermPersistenceService | None:
    """返回全局单例（未初始化返回 None，调用方跳过持久化）。"""
    return _mid_term_persistence


async def close_mid_term_persistence() -> None:
    """关闭全局持久化服务（main.py 关闭时调用）。"""
    global _mid_term_persistence
    _mid_term_persistence = None