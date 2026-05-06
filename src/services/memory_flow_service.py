from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional

import asyncio
import json
import pickle
import time

from json_repair import repair_json

from src.services import memory_service as memory_service_module
from src.chat.utils.utils import is_bot_self
from src.common.logger import get_logger
from src.common.message_repository import count_messages, find_messages
from src.config.config import global_config
from src.person_info.person_info import Person, get_person_id, store_person_memory_from_answer
from src.services.memory_service import memory_service
from src.services.llm_service import LLMServiceClient

logger = get_logger("memory_flow_service")


class PersonFactWritebackService:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=256)
        self._worker_task: Optional[asyncio.Task] = None
        self._stopping = False
        self._extractor = LLMServiceClient(task_name="utils", request_type="person_fact_writeback")

    async def start(self) -> None:
        if self._worker_task is not None and not self._worker_task.done():
            return
        self._stopping = False
        self._worker_task = asyncio.create_task(self._worker_loop(), name="memory_person_fact_writeback")

    async def shutdown(self) -> None:
        self._stopping = True
        worker = self._worker_task
        self._worker_task = None
        if worker is None:
            return
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("关闭人物事实写回 worker 失败: %s", exc)

    async def enqueue(self, message: Any) -> None:
        if not bool(global_config.a_memorix.integration.person_fact_writeback_enabled):
            return
        if self._stopping:
            return
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            logger.warning("人物事实写回队列已满，跳过本次回复")

    async def _worker_loop(self) -> None:
        try:
            while not self._stopping:
                message = await self._queue.get()
                try:
                    await self._handle_message(message)
                except Exception as exc:
                    logger.warning("人物事实写回处理失败: %s", exc, exc_info=True)
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:
            raise

    async def _handle_message(self, message: Any) -> None:
        reply_text = str(getattr(message, "processed_plain_text", "") or "").strip()
        if not reply_text:
            return
        if self._looks_ephemeral(reply_text):
            return

        target_person = self._resolve_target_person(message)
        if target_person is None or not target_person.is_known:
            return

        facts = await self._extract_facts(target_person, reply_text)
        if not facts:
            return

        session_id = str(
            getattr(message, "session_id", "")
            or getattr(getattr(message, "session", None), "session_id", "")
            or ""
        ).strip()
        if not session_id:
            return

        person_name = str(
            getattr(target_person, "person_name", "")
            or getattr(target_person, "nickname", "")
            or ""
        ).strip()
        if not person_name:
            return

        for fact in facts:
            await store_person_memory_from_answer(person_name, fact, session_id)

    def _resolve_target_person(self, message: Any) -> Optional[Person]:
        session = getattr(message, "session", None)
        session_platform = str(getattr(session, "platform", "") or getattr(message, "platform", "") or "").strip()
        session_user_id = str(getattr(session, "user_id", "") or "").strip()
        group_id = str(getattr(session, "group_id", "") or "").strip()

        if session_platform and session_user_id and not group_id:
            if is_bot_self(session_platform, session_user_id):
                return None
            person_id = get_person_id(session_platform, session_user_id)
            person = Person(person_id=person_id)
            return person if person.is_known else None

        reply_to = str(getattr(message, "reply_to", "") or "").strip()
        if not reply_to:
            return None
        try:
            replies = find_messages(message_id=reply_to, limit=1)
        except Exception as exc:
            logger.debug("查询 reply_to 目标失败: %s", exc)
            return None
        if not replies:
            return None
        reply_message = replies[0]
        reply_platform = str(getattr(reply_message, "platform", "") or session_platform or "").strip()
        reply_user_info = getattr(getattr(reply_message, "message_info", None), "user_info", None)
        reply_user_id = str(getattr(reply_user_info, "user_id", "") or "").strip()
        if not reply_platform or not reply_user_id or is_bot_self(reply_platform, reply_user_id):
            return None
        person_id = get_person_id(reply_platform, reply_user_id)
        person = Person(person_id=person_id)
        return person if person.is_known else None

    async def _extract_facts(self, person: Person, reply_text: str) -> List[str]:
        person_name = str(getattr(person, "person_name", "") or getattr(person, "nickname", "") or person.person_id)
        prompt = f"""你要从一条机器人刚刚发送的回复中，提取“关于{person_name}的稳定事实”。

目标人物：{person_name}
机器人回复：
{reply_text}

请只提取满足以下条件的事实：
1. 明确是关于目标人物本人的信息。
2. 具有相对稳定性，可以作为长期记忆保存。
3. 用简洁中文陈述句表达。
4. 如果回复是在直接对目标人物说话，出现“你/你的/你自己”时，默认都指目标人物，请先改写成关于目标人物的第三人称事实再输出。

不要提取：
- 机器人的情绪、计划、临时动作、客套话
- 只适用于当前时刻的短期安排
- 不确定、猜测、反问
- 与目标人物无关的信息

严格输出 JSON 数组，例如：
["他喜欢深夜打游戏", "他养了一只猫"]
如果没有可写入的事实，输出 []"""
        try:
            response_result = await self._extractor.generate_response(prompt)
        except Exception as exc:
            logger.debug("人物事实提取模型调用失败: %s", exc)
            return []
        return self._parse_fact_list(response_result.response)

    @staticmethod
    def _parse_fact_list(raw: str) -> List[str]:
        text = str(raw or "").strip()
        if not text:
            return []
        try:
            repaired = repair_json(text)
            payload = json.loads(repaired) if isinstance(repaired, str) else repaired
        except Exception:
            payload = None
        if not isinstance(payload, list):
            return []

        items: List[str] = []
        seen = set()
        for item in payload:
            fact = str(item or "").strip().strip("- ")
            if not fact or len(fact) < 4:
                continue
            if fact in seen:
                continue
            seen.add(fact)
            items.append(fact)
        return items[:5]

    @staticmethod
    def _looks_ephemeral(text: str) -> bool:
        content = str(text or "").strip()
        if not content:
            return True
        ephemeral_markers = (
            "哈哈",
            "好的",
            "收到",
            "嗯嗯",
            "晚安",
            "早安",
            "拜拜",
            "谢谢",
            "在吗",
            "？",
        )
        if len(content) <= 8 and any(marker in content for marker in ephemeral_markers):
            return True
        return False


@dataclass
class ChatSummaryWritebackState:
    last_trigger_message_count: int = 0
    last_trigger_time: float = 0.0


class ChatSummaryWritebackService:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=256)
        self._worker_task: Optional[asyncio.Task] = None
        self._stopping = False
        self._states: dict[str, ChatSummaryWritebackState] = {}

    async def start(self) -> None:
        if self._worker_task is not None and not self._worker_task.done():
            return
        self._stopping = False
        self._worker_task = asyncio.create_task(self._worker_loop(), name="memory_chat_summary_writeback")

    async def shutdown(self) -> None:
        self._stopping = True
        worker = self._worker_task
        self._worker_task = None
        if worker is None:
            return
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("关闭聊天摘要写回 worker 失败: %s", exc)

    async def enqueue(self, message: Any) -> None:
        if not bool(global_config.a_memorix.integration.chat_summary_writeback_enabled):
            return
        if self._stopping:
            return
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            logger.warning("聊天摘要写回队列已满，跳过本次触发")

    async def _worker_loop(self) -> None:
        try:
            while not self._stopping:
                message = await self._queue.get()
                try:
                    await self._handle_message(message)
                except Exception as exc:
                    logger.warning("聊天摘要写回处理失败: %s", exc, exc_info=True)
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:
            raise

    async def _handle_message(self, message: Any) -> None:
        session_id = self._resolve_session_id(message)
        if not session_id:
            return

        total_message_count = count_messages(session_id=session_id)
        if total_message_count <= 0:
            return

        threshold = self._message_threshold()
        state = self._states.get(session_id)
        if state is None:
            restored_count = await self._load_last_trigger_message_count(
                session_id=session_id,
                total_message_count=total_message_count,
            )
            state = ChatSummaryWritebackState(
                last_trigger_message_count=restored_count,
                last_trigger_time=time.time() if restored_count > 0 else 0.0,
            )
            self._states[session_id] = state
        pending_message_count = max(0, total_message_count - state.last_trigger_message_count)
        if pending_message_count < threshold:
            return

        context_length = self._context_length()
        message_time = self._extract_message_timestamp(message)
        result = await memory_service.ingest_summary(
            external_id=f"chat_auto_summary:{session_id}:{total_message_count}",
            chat_id=session_id,
            text="",
            participants=[],
            time_end=message_time,
            metadata={
                "generate_from_chat": True,
                "context_length": context_length,
                "writeback_source": "memory_flow_service",
                "trigger": "message_threshold",
                "trigger_message_count": total_message_count,
            },
            respect_filter=True,
            user_id=self._extract_session_user_id(message),
            group_id=self._extract_session_group_id(message),
        )
        if not getattr(result, "success", False):
            logger.warning(
                "聊天摘要自动写回失败: session_id=%s detail=%s",
                session_id,
                getattr(result, "detail", ""),
            )
            return

        state.last_trigger_message_count = total_message_count
        state.last_trigger_time = time.time()
        logger.info(
            "聊天摘要自动写回成功: session_id=%s trigger=%s total_messages=%s context_length=%s detail=%s",
            session_id,
            "message_threshold",
            total_message_count,
            context_length,
            getattr(result, "detail", ""),
        )

    async def _load_last_trigger_message_count(self, *, session_id: str, total_message_count: int) -> int:
        """从已落库的聊天摘要恢复触发游标，避免服务重启后重复摘要。"""
        try:
            runtime_manager = getattr(memory_service_module, "a_memorix_host_service", None)
            ensure_kernel = getattr(runtime_manager, "_ensure_kernel", None)
            if not callable(ensure_kernel):
                return 0

            kernel = await ensure_kernel()
            metadata_store = getattr(kernel, "metadata_store", None)
            if metadata_store is None:
                return 0

            paragraphs = metadata_store.get_paragraphs_by_source(f"chat_summary:{session_id}")
            if not paragraphs:
                return 0

            latest_paragraph = max(paragraphs, key=self._paragraph_created_at)
            metadata = self._paragraph_metadata(latest_paragraph)
            trigger_message_count = self._coerce_positive_int(metadata.get("trigger_message_count"))
            if trigger_message_count > 0:
                return min(total_message_count, trigger_message_count)

            # 兼容旧摘要数据：没有触发计数时，只能退化为对齐当前计数，
            # 至少避免重启后立刻重复写入一条相近摘要。
            return total_message_count
        except Exception as exc:
            logger.debug("恢复聊天摘要写回游标失败: session_id=%s error=%s", session_id, exc)
            return 0

    @staticmethod
    def _paragraph_created_at(paragraph: dict[str, Any]) -> float:
        try:
            return float(paragraph.get("created_at") or 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _paragraph_metadata(paragraph: dict[str, Any]) -> dict[str, Any]:
        metadata = paragraph.get("metadata")
        if isinstance(metadata, dict):
            return metadata
        if isinstance(metadata, (bytes, bytearray)):
            try:
                parsed = pickle.loads(metadata)
            except Exception:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _coerce_positive_int(value: Any) -> int:
        try:
            number = int(value or 0)
        except Exception:
            return 0
        return max(0, number)

    @staticmethod
    def _resolve_session_id(message: Any) -> str:
        return str(
            getattr(message, "session_id", "")
            or getattr(getattr(message, "session", None), "session_id", "")
            or ""
        ).strip()

    @staticmethod
    def _extract_session_user_id(message: Any) -> str:
        return str(
            getattr(getattr(message, "session", None), "user_id", "")
            or getattr(message, "user_id", "")
            or ""
        ).strip()

    @staticmethod
    def _extract_session_group_id(message: Any) -> str:
        return str(
            getattr(getattr(message, "session", None), "group_id", "")
            or getattr(message, "group_id", "")
            or ""
        ).strip()

    @staticmethod
    def _extract_message_timestamp(message: Any) -> float | None:
        raw_timestamp = getattr(message, "timestamp", None)
        if isinstance(raw_timestamp, datetime):
            return raw_timestamp.timestamp()
        if hasattr(raw_timestamp, "timestamp") and callable(raw_timestamp.timestamp):
            try:
                return float(raw_timestamp.timestamp())
            except Exception:
                return None
        if isinstance(raw_timestamp, (int, float)):
            return float(raw_timestamp)
        return None

    @staticmethod
    def _message_threshold() -> int:
        return max(1, int(global_config.a_memorix.integration.chat_summary_writeback_message_threshold))

    @staticmethod
    def _context_length() -> int:
        return max(1, int(global_config.a_memorix.integration.chat_summary_writeback_context_length))


class MemoryAutomationService:
    def __init__(self) -> None:
        self.fact_writeback = PersonFactWritebackService()
        self.chat_summary_writeback = ChatSummaryWritebackService()
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self.fact_writeback.start()
        await self.chat_summary_writeback.start()
        self._started = True

    async def shutdown(self) -> None:
        if not self._started:
            return
        await self.chat_summary_writeback.shutdown()
        await self.fact_writeback.shutdown()
        self._started = False

    async def on_incoming_message(self, message: Any) -> None:
        del message
        if not self._started:
            await self.start()

    async def on_message_sent(self, message: Any) -> None:
        if not self._started:
            await self.start()
        await self.fact_writeback.enqueue(message)
        await self.chat_summary_writeback.enqueue(message)


memory_automation_service = MemoryAutomationService()
