"""智能体记忆适配器。

通过语义映射将交互记忆写入 A_Memorix，
使用 agent_interaction:{A}:{B} chat_id 和 agent:{agent_id} person_id
命名空间隔离，不污染用户记忆。
"""

from __future__ import annotations

import logging
import time

from src.core.types import MemorySearchResult, MemoryWriteResult

logger = logging.getLogger(__name__)

_CHAT_ID_PREFIX = "agent_interaction"
_PERSON_ID_PREFIX = "agent"


class AgentMemoryAdapter:
    """智能体交互记忆适配器。

    通过语义映射复用 MemoryServicePort 接口，
    将智能体间交互记忆与用户记忆隔离。
    """

    def __init__(self) -> None:
        self._memory_port: Any = None

    @property
    def memory_port(self) -> Any:
        """获取 MemoryServicePort 实例（延迟初始化）。"""
        if self._memory_port is None:
            from src.core.adapters.memory_service import AMemorixMemoryServicePort
            self._memory_port = AMemorixMemoryServicePort()
        return self._memory_port

    @staticmethod
    def build_chat_id(agent_a_id: str, agent_b_id: str) -> str:
        """构建交互记忆的 chat_id，按字典序排列保证方向无关。"""
        ids = sorted([agent_a_id, agent_b_id])
        return f"{_CHAT_ID_PREFIX}:{ids[0]}:{ids[1]}"

    @staticmethod
    def build_person_id(agent_id: str) -> str:
        """构建智能体的 person_id。"""
        return f"{_PERSON_ID_PREFIX}:{agent_id}"

    @staticmethod
    def is_interaction_chat_id(chat_id: str) -> bool:
        """判断 chat_id 是否为智能体交互记忆。"""
        return chat_id.startswith(f"{_CHAT_ID_PREFIX}:")

    @staticmethod
    def parse_agent_ids_from_chat_id(chat_id: str) -> tuple[str, str] | None:
        """从交互 chat_id 中解析两个智能体ID。"""
        if not chat_id.startswith(f"{_CHAT_ID_PREFIX}:"):
            return None
        parts = chat_id[len(_CHAT_ID_PREFIX) + 1:].split(":")
        if len(parts) != 2:
            return None
        return (parts[0], parts[1])

    async def write_interaction_memory(
        self,
        event_id: str,
        initiator_id: str,
        target_id: str,
        content: str,
        emotion_tag: str,
        interaction_type: str,
        emotion_snapshot: str = "",
        relationship_delta: float = 0.0,
    ) -> MemoryWriteResult:
        """为双方写入交互记忆。

        Args:
            event_id: 交互事件ID
            initiator_id: 发起方智能体ID
            target_id: 目标方智能体ID
            content: 交互内容摘要
            emotion_tag: 情绪标签（positive/negative/neutral/mixed）
            interaction_type: 交互类型
            emotion_snapshot: 情绪快照JSON
            relationship_delta: 关系变化量

        Returns:
            MemoryWriteResult
        """
        chat_id = self.build_chat_id(initiator_id, target_id)
        now = time.time()

        # 为发起方写入
        initiator_person_id = self.build_person_id(initiator_id)
        initiator_result = await self._write_single(
            external_id=f"{event_id}:initiator",
            chat_id=chat_id,
            person_id=initiator_person_id,
            text=content,
            emotion_tag=emotion_tag,
            interaction_type=interaction_type,
            event_id=event_id,
            emotion_snapshot=emotion_snapshot,
            relationship_delta=relationship_delta,
            timestamp=now,
        )

        # 为目标方写入
        target_person_id = self.build_person_id(target_id)
        target_result = await self._write_single(
            external_id=f"{event_id}:target",
            chat_id=chat_id,
            person_id=target_person_id,
            text=content,
            emotion_tag=emotion_tag,
            interaction_type=interaction_type,
            event_id=event_id,
            emotion_snapshot=emotion_snapshot,
            relationship_delta=relationship_delta,
            timestamp=now,
        )

        if initiator_result.success and target_result.success:
            return MemoryWriteResult(
                success=True,
                stored_ids=initiator_result.stored_ids + target_result.stored_ids,
            )
        return MemoryWriteResult(
            success=False,
            detail=f"initiator_ok={initiator_result.success}, target_ok={target_result.success}",
        )

    async def search_interaction_memory(
        self,
        agent_id: str,
        target_agent_id: str,
        query: str = "",
        limit: int = 5,
    ) -> MemorySearchResult:
        """检索智能体间交互记忆。"""
        chat_id = self.build_chat_id(agent_id, target_agent_id)
        person_id = self.build_person_id(agent_id)

        if not query:
            query = f"与{target_agent_id}的交互"

        return await self.memory_port.search(
            query=query,
            chat_id=chat_id,
            person_id=person_id,
            limit=limit,
        )

    async def _write_single(
        self,
        external_id: str,
        chat_id: str,
        person_id: str,
        text: str,
        emotion_tag: str,
        interaction_type: str,
        event_id: str,
        emotion_snapshot: str,
        relationship_delta: float,
        timestamp: float,
    ) -> MemoryWriteResult:
        """写入单条交互记忆。"""
        return await self.memory_port.ingest_text(
            external_id=external_id,
            source_type="agent_interaction",
            text=text,
            chat_id=chat_id,
            person_ids=[person_id],
            tags=["agent_interaction", emotion_tag, interaction_type],
            timestamp=timestamp,
            metadata={
                "interaction_event_id": event_id,
                "emotion_snapshot": emotion_snapshot,
                "relationship_delta": relationship_delta,
            },
        )

    async def propagate_memory(
        self,
        source_agent_id: str,
        target_agent_id: str,
        about_agent_id: str,
    ) -> None:
        """记忆传播：将 source 关于 about 的记忆传播给 target。

        间接记忆标记 propagated_from，不可再传播（防止链式传播）。
        """
        # 检索 source 关于 about 的交互记忆
        search_result = await self.search_interaction_memory(
            source_agent_id, about_agent_id, limit=10
        )

        if not search_result.success or not search_result.hits:
            return

        # 筛选可传播的记忆（排除间接记忆）
        propagatable = []
        for hit in search_result.hits:
            metadata = hit.metadata if isinstance(hit.metadata, dict) else {}
            # 间接记忆不可再传播
            if metadata.get("propagated_from"):
                continue
            propagatable.append(hit)

        if not propagatable:
            return

        # 将筛选后的记忆写入 target 的记忆
        target_chat_id = self.build_chat_id(target_agent_id, about_agent_id)
        target_person_id = self.build_person_id(target_agent_id)

        for hit in propagatable[:5]:
            content = hit.content.strip()
            if not content:
                continue

            await self.memory_port.ingest_text(
                external_id=f"propagated:{hit.hash_value or hit.episode_id}",
                source_type="agent_interaction_propagated",
                text=content,
                chat_id=target_chat_id,
                person_ids=[target_person_id],
                tags=["agent_interaction", "propagated"],
                metadata={
                    "propagated_from": source_agent_id,
                    "about_agent": about_agent_id,
                    "original_hash": hit.hash_value,
                },
            )

        logger.info(
            "[agent_interaction] 记忆传播: %s→%s about=%s count=%d",
            source_agent_id,
            target_agent_id,
            about_agent_id,
            len(propagatable[:5]),
        )

    async def apply_memory_decay(
        self,
        agent_id: str,
        target_agent_id: str,
        decay_days: int = 7,
        decay_ratio: float = 0.3,
    ) -> None:
        """记忆衰减：超过 decay_days 未被引用的交互记忆检索权重衰减。"""
        try:
            await self.memory_port.maintain_memory(
                action="decay",
                target=self.build_chat_id(agent_id, target_agent_id),
                hours=decay_days * 24,
                reason=f"agent_interaction_decay:{agent_id}:{target_agent_id}",
            )
        except Exception as e:
            logger.debug("[agent_interaction] 记忆衰减失败: %s", e)

    async def reinforce_memory(
        self,
        agent_id: str,
        target_agent_id: str,
        content_hash: str = "",
    ) -> None:
        """记忆强化：被引用的旧记忆权重恢复，频繁交互时最近记忆权重+20%。"""
        try:
            target = content_hash or self.build_chat_id(agent_id, target_agent_id)
            await self.memory_port.maintain_memory(action="reinforce", target=target)
        except Exception as e:
            logger.debug("[agent_interaction] 记忆强化失败: %s", e)

    async def check_frequent_interaction(
        self,
        agent_id: str,
        target_agent_id: str,
        threshold: int = 3,
        reinforce_ratio: float = 0.2,
    ) -> bool:
        """检查是否频繁交互，若是则强化最近记忆。"""
        try:
            result = await self.search_interaction_memory(
                agent_id, target_agent_id, limit=threshold + 2
            )
            if result.success and len(result.hits) >= threshold:
                # 频繁交互，强化最近记忆
                for hit in result.hits[:threshold]:
                    if hit.hash_value:
                        await self.reinforce_memory(
                            agent_id, target_agent_id, hit.hash_value
                        )
                return True
        except Exception:
            pass
        return False