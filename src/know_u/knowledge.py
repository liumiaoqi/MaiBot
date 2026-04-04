"""
Maisaka knowledge retrieval and learning helpers.
"""

from typing import Any, Dict, List

import asyncio
import json

from src.chat.message_receive.message import SessionMessage
from src.chat.utils.utils import is_bot_self
from src.common.data_models.llm_service_data_models import LLMGenerationOptions
from src.common.logger import get_logger
from src.know_u.knowledge_store import KNOWLEDGE_CATEGORIES, get_knowledge_store
from src.maisaka.context_messages import AssistantMessage, LLMContextMessage, SessionBackedMessage, ToolResultMessage
from src.maisaka.message_adapter import parse_speaker_content
from src.person_info.person_info import Person
from src.services.llm_service import LLMServiceClient

logger = get_logger("maisaka_knowledge")

NO_RESULT_KEYWORDS = [
    "无",
    "没有",
    "不适用",
    "无需",
    "无相关",
]


def extract_category_ids_from_result(result: str) -> List[str]:
    """Extract valid category ids from an LLM result string."""
    if not result:
        return []

    normalized = result.strip()
    if not normalized:
        return []

    lowered = normalized.lower()
    if any(keyword in lowered for keyword in ["none", "no relevant", "no_need", "no need"]):
        return []
    if any(keyword in normalized for keyword in NO_RESULT_KEYWORDS):
        return []

    category_ids: List[str] = []
    for part in normalized.replace(",", " ").replace("，", " ").replace("\n", " ").split():
        candidate = part.strip()
        if candidate in KNOWLEDGE_CATEGORIES and candidate not in category_ids:
            category_ids.append(candidate)

    return category_ids


async def retrieve_relevant_knowledge(
    knowledge_analyzer: Any,
    chat_history: List[LLMContextMessage],
) -> str:
    """Retrieve formatted knowledge snippets relevant to the current chat history."""
    store = get_knowledge_store()
    categories_summary = store.get_categories_summary()

    try:
        category_ids = await knowledge_analyzer.analyze_knowledge_need(chat_history, categories_summary)
        if not category_ids:
            return ""
        return store.get_formatted_knowledge(category_ids)
    except Exception:
        logger.exception("检索相关知识失败")
        return ""


class KnowledgeLearner:
    """
    从最近对话中提取用户画像类知识并写入知识库。
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._store = get_knowledge_store()
        self._llm = LLMServiceClient(task_name="utils", request_type="maisaka.knowledge.learn")
        self._learning_lock = asyncio.Lock()
        self._last_processed_index = 0
        self.min_messages_for_extraction = 10

    def get_pending_count(self, message_cache: List[SessionMessage]) -> int:
        """??????????????"""
        return max(0, len(message_cache) - self._last_processed_index)

    async def learn(self, message_cache: List[SessionMessage]) -> int:
        """?????????????????????"""
        pending_messages = message_cache[self._last_processed_index :]
        if not pending_messages:
            return 0
        if len(pending_messages) < self.min_messages_for_extraction:
            return 0

        async with self._learning_lock:
            chat_excerpt = self._build_chat_excerpt(pending_messages)
            if not chat_excerpt:
                return 0

            prompt = self._build_learning_prompt(chat_excerpt)
            try:
                result = await self._llm.generate_response(
                    prompt=prompt,
                    options=LLMGenerationOptions(
                        temperature=0.1,
                        max_tokens=512,
                    ),
                )
            except Exception:
                logger.exception("??????????")
                return 0

            knowledge_items = self._parse_learning_result(result.response or "")
            if not knowledge_items:
                logger.debug("?????????????????")
                self._last_processed_index = len(message_cache)
                return 0

            added_count = 0
            for item in knowledge_items:
                category_id = str(item.get("category_id", "")).strip()
                content = str(item.get("content", "")).strip()
                if not category_id or not content:
                    continue

                metadata = {
                    "session_id": self._session_id,
                    "source": "maisaka_learning",
                }
                for field_name in ("platform", "user_id", "user_nickname", "person_name"):
                    field_value = str(item.get(field_name, "")).strip()
                    if field_value:
                        metadata[field_name] = field_value

                if self._store.add_knowledge(
                    category_id=category_id,
                    content=content,
                    metadata=metadata,
                ):
                    added_count += 1

            self._last_processed_index = len(message_cache)

            if added_count > 0:
                logger.info(
                    f"Maisaka ???????: ????={self._session_id} ????={added_count}"
                )
            else:
                logger.debug(
                    f"Maisaka ???????????????: ????={self._session_id}"
                )

            return added_count

    def _build_chat_excerpt(self, messages: List[SessionMessage]) -> str:
        """
        构建适合画像提取的对话片段，只保留用户可见文本。
        """
        lines: List[str] = []
        for message in messages[-30:]:
            if isinstance(message, (AssistantMessage, ToolResultMessage)):
                continue
            if isinstance(message, SessionBackedMessage):
                if message.original_message and is_bot_self(
                    message.original_message.platform,
                    message.original_message.message_info.user_info.user_id,
                ):
                    continue
                raw_text = message.processed_plain_text.strip()
                fallback_speaker = (
                    message.original_message.message_info.user_info.user_nickname
                    if message.original_message is not None
                    else "用户"
                )
            else:
                if is_bot_self(message.platform, message.message_info.user_info.user_id):
                    continue
                raw_text = message.processed_plain_text.strip()
                fallback_speaker = message.message_info.user_info.user_nickname or "用户"

            if not raw_text:
                continue

            speaker_name, body = parse_speaker_content(raw_text)
            visible_text = (body or raw_text).strip()
            if not visible_text:
                continue

            speaker = speaker_name or fallback_speaker
            user_metadata = self._extract_message_user_metadata(message)
            metadata_parts = [
                f"platform={user_metadata['platform'] or 'unknown'}",
                f"user_id={user_metadata['user_id'] or 'unknown'}",
                f"user_nickname={user_metadata['user_nickname'] or speaker}",
                f"person_name={user_metadata['person_name'] or ''}",
            ]
            lines.append(
                f"[用户信息] {'; '.join(metadata_parts)}\n"
                f"[发言] {speaker}: {visible_text}"
            )

        return "\n".join(lines)

    @staticmethod
    def _extract_message_user_metadata(message: SessionMessage) -> Dict[str, str]:
        """提取消息对应的用户元信息。"""
        source_message = message.original_message if isinstance(message, SessionBackedMessage) else message
        platform = str(getattr(source_message, "platform", "") or "").strip()
        user_info = getattr(getattr(source_message, "message_info", None), "user_info", None)
        user_id = str(getattr(user_info, "user_id", "") or "").strip()
        user_nickname = str(getattr(user_info, "user_nickname", "") or "").strip()

        person_name = ""
        if platform and user_id:
            try:
                person = Person(platform=platform, user_id=user_id)
                if person.is_known and person.person_name:
                    person_name = str(person.person_name).strip()
            except Exception:
                person_name = ""

        return {
            "platform": platform,
            "user_id": user_id,
            "user_nickname": user_nickname,
            "person_name": person_name,
        }

    def _build_learning_prompt(self, chat_excerpt: str) -> str:
        """构建知识提取提示词。"""
        categories_text = "\n".join(
            f"{category_id}. {category_name}" for category_id, category_name in KNOWLEDGE_CATEGORIES.items()
        )
        return (
            "你是一个用户画像知识提取器，需要从聊天记录里提取稳定、可复用的用户事实。\n"
            "只提取用户明确表达或高置信度可归纳的信息，不要猜测，不要提取一次性情绪，不要重复表述。\n"
            "如果没有可提取内容，返回空数组 []。\n"
            "输出必须是 JSON 数组，每项格式为 "
            '{"category_id":"分类编号","content":"简洁中文陈述"}。\n'
            "分类如下：\n"
            f"{categories_text}\n\n"
            "聊天记录：\n"
            f"{chat_excerpt}"
        )

    def _parse_learning_result(self, result: str) -> List[Dict[str, str]]:
        """解析模型返回的知识条目。"""
        normalized = result.strip()
        if not normalized:
            return []

        if "```" in normalized:
            normalized = normalized.replace("```json", "").replace("```JSON", "").replace("```", "").strip()

        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            logger.warning("知识学习结果不是有效的 JSON")
            return []

        if not isinstance(parsed, list):
            return []

        normalized_items: List[Dict[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for item in parsed:
            if not isinstance(item, dict):
                continue

            category_id = str(item.get("category_id", "")).strip()
            content = " ".join(str(item.get("content", "")).strip().split())
            if category_id not in KNOWLEDGE_CATEGORIES:
                continue
            if not content:
                continue

            pair = (category_id, content)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            normalized_items.append(
                {
                    "category_id": category_id,
                    "content": content,
                }
            )

        return normalized_items

    def _build_learning_prompt(self, chat_excerpt: str) -> str:
        """构建知识提取提示词。"""
        categories_text = "\n".join(
            f"{category_id}. {category_name}" for category_id, category_name in KNOWLEDGE_CATEGORIES.items()
        )
        return (
            "你是一个用户画像知识提取器，需要从聊天记录里提取稳定、可复用的用户事实。\n"
            "聊天记录每条发言前都带有用户元信息，你必须明确判断这些特征属于哪个用户。\n"
            "只提取用户明确表达或高置信度可归纳的信息，不要猜测，不要提取一次性情绪，不要重复表达。\n"
            "如果没有可提取内容，返回空数组[]。\n"
            "输出必须是 JSON 数组，每项格式为 "
            '{"category_id":"分类编号","content":"简洁中文陈述","platform":"平台","user_id":"用户ID","user_nickname":"用户昵称","person_name":"人物名或空字符串"}。\n'
            "其中 platform 和 user_id 必填；user_nickname 尽量填写；person_name 仅在用户信息中明确给出时填写，否则填空字符串。\n"
            "同一条知识只能归属到一个用户，不要混合不同人的信息。\n"
            "分类如下：\n"
            f"{categories_text}\n\n"
            "聊天记录：\n"
            f"{chat_excerpt}"
        )

    def _parse_learning_result(self, result: str) -> List[Dict[str, str]]:
        """解析模型返回的知识条目。"""
        normalized = result.strip()
        if not normalized:
            return []

        if "```" in normalized:
            normalized = normalized.replace("```json", "").replace("```JSON", "").replace("```", "").strip()

        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            logger.warning("知识学习结果不是有效的 JSON")
            return []

        if not isinstance(parsed, list):
            return []

        normalized_items: List[Dict[str, str]] = []
        seen_pairs: set[tuple[str, str, str, str]] = set()
        for item in parsed:
            if not isinstance(item, dict):
                continue

            category_id = str(item.get("category_id", "")).strip()
            content = " ".join(str(item.get("content", "")).strip().split())
            platform = str(item.get("platform", "")).strip()
            user_id = str(item.get("user_id", "")).strip()
            user_nickname = str(item.get("user_nickname", "")).strip()
            person_name = str(item.get("person_name", "")).strip()
            if category_id not in KNOWLEDGE_CATEGORIES:
                continue
            if not content or not platform or not user_id:
                continue

            pair = (category_id, content, platform, user_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            normalized_items.append(
                {
                    "category_id": category_id,
                    "content": content,
                    "platform": platform,
                    "user_id": user_id,
                    "user_nickname": user_nickname,
                    "person_name": person_name,
                }
            )

        return normalized_items
