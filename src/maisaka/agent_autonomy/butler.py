"""管家系统 — 彼岸居客厅规则。

管家不是第14个角色，是"谁在客厅谁就回消息"这个自然规则的实现。
核心定位：过滤（谁看见了消息）和协调（谁先抢到键盘）。

两条流共享同一管道：
- 对话流：用户消息 → 主智能体回复 → 管家协调插话
- 提醒流：定时器触发 → 管家协调谁提醒 → 主智能体优先
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.common.logger import get_logger
from src.maisaka.agent.config import AgentConfig, InternalRelationship
from src.maisaka.agent.registry import AgentConfigRegistry
from src.maisaka.agent_autonomy.reminder import ReminderManager, Reminder
from src.maisaka.message_port import MessagePort, get_message_port

logger = get_logger("agent_autonomy.butler")

_TZ_CN = timezone(timedelta(hours=8))
MAX_INTERJECTORS = 2


def _now() -> datetime:
    return datetime.now(_TZ_CN)


@dataclass
class InterjectionCandidate:
    """管家筛选出的插话候选。"""

    agent_id: str
    display_name: str
    is_mentioned: bool
    has_relation: bool


class Butler:
    """管家 — 过滤+协调+提醒，不说话。

    三层过滤：
    1. 规则过滤（零成本）：名字被提到→必看见；有关系→可能看见；无关→很少看见
    2. 管家LLM（1次调用）：理解话题+角色性格+关系网，判断"谁会关心"
    3. 角色LLM（仅选中者）：被选中的角色决定插话内容
    """

    def __init__(
        self,
        primary_agent_id: str,
        session_id: str,
        reminder_manager: ReminderManager | None = None,
        message_port: MessagePort | None = None,
    ) -> None:
        self._primary_agent_id = primary_agent_id
        self._session_id = session_id
        self._reminder_manager = reminder_manager or ReminderManager()
        self._message_port = message_port or get_message_port()

        self._resident_briefs: list[dict] = []
        self._resident_ids: list[str] = []
        self._primary_display_name: str = ""
        self._last_interjection: dict[str, float] = {}
        self._interjection_cooldown = 30.0

        self._load_agents()

    def _load_agents(self) -> None:
        """从 AgentConfigRegistry 加载智能体信息。"""
        registry = AgentConfigRegistry.get_instance()
        agents = registry.list_agents()

        for agent in agents:
            if agent.agent_id == self._primary_agent_id:
                self._primary_display_name = agent.display_name
                continue

            rels = []
            for rel in (agent.internal_relationships or []):
                rels.append({
                    "target": rel.target_agent_id,
                    "type": rel.relationship_type,
                    "attitude": rel.attitude,
                })

            focus_areas = list(agent.memory_personality.attention_tags) if agent.memory_personality.attention_tags else []

            self._resident_briefs.append({
                "id": agent.agent_id,
                "name": agent.display_name,
                "identity_summary": agent.get_identity_summary(),
                "relationships": rels,
                "focus_areas": focus_areas,
            })
            self._resident_ids.append(agent.agent_id)

        logger.info(
            f"[butler] 初始化: primary={self._primary_agent_id} "
            f"residents={len(self._resident_briefs)} session={self._session_id}"
        )

    @property
    def reminder_manager(self) -> ReminderManager:
        return self._reminder_manager

    # ── 对话流 ──────────────────────────────────────────

    def _rule_filter(self, user_text: str, agent_text: str) -> list[InterjectionCandidate]:
        """第一层：规则过滤（零成本）。"""
        all_text = f"{user_text} {agent_text}"
        candidates = []

        for brief in self._resident_briefs:
            aid = brief["id"]
            last_time = self._last_interjection.get(aid, 0)
            if time.time() - last_time < self._interjection_cooldown:
                continue

            is_mentioned = brief["name"] in all_text or aid in all_text
            has_relation = any(
                r["target"] == self._primary_agent_id
                for r in brief["relationships"]
            )

            focus_matched = False
            focus_areas = brief.get("focus_areas", [])
            if focus_areas:
                all_text_lower = all_text.lower()
                focus_matched = any(area.lower() in all_text_lower for area in focus_areas)

            if is_mentioned:
                candidates.append(InterjectionCandidate(
                    agent_id=aid,
                    display_name=brief["name"],
                    is_mentioned=True,
                    has_relation=has_relation,
                ))
            elif has_relation and random.random() < 0.5:
                prob = 0.5 + (0.3 if focus_matched else 0.0)
                if random.random() < prob:
                    candidates.append(InterjectionCandidate(
                        agent_id=aid,
                        display_name=brief["name"],
                        is_mentioned=False,
                        has_relation=True,
                    ))
            elif focus_matched and random.random() < 0.4:
                candidates.append(InterjectionCandidate(
                    agent_id=aid,
                    display_name=brief["name"],
                    is_mentioned=False,
                    has_relation=has_relation,
                ))
            elif random.random() < 0.1:
                candidates.append(InterjectionCandidate(
                    agent_id=aid,
                    display_name=brief["name"],
                    is_mentioned=False,
                    has_relation=False,
                ))

        return candidates

    async def _llm_filter(
        self,
        user_text: str,
        agent_text: str,
        candidates: list[InterjectionCandidate],
    ) -> list[InterjectionCandidate]:
        """第二层：管家LLM（1次调用），判断谁会关心。"""
        if not candidates:
            return []

        from src.llm_models.payload_content.message import MessageBuilder, RoleType
        from src.common.data_models.llm_service_data_models import LLMGenerationOptions
        from src.services.llm_service import LLMServiceClient

        context = f"用户：{user_text}"
        if agent_text:
            context += f"\n{self._primary_display_name}：{agent_text}"

        agent_list = []
        candidate_map = {c.agent_id: c for c in candidates}
        for c in candidates:
            brief = next(b for b in self._resident_briefs if b["id"] == c.agent_id)
            agent_list.append(brief)

        prompt = (
            "你是一个管家，判断哪些角色会对一段对话感兴趣并可能想插话。\n\n"
            f"对话内容：\n{context}\n\n"
            "可能感兴趣的角色：\n"
        )
        for i, brief in enumerate(agent_list):
            prompt += f"\n{i+1}. {brief['name']}（{brief['id']}）：{brief['identity_summary']}"
            if brief.get("focus_areas"):
                prompt += f"\n   关注领域：{'、'.join(brief['focus_areas'])}"
            if brief["relationships"]:
                rel_str = "，".join(
                    f"与{r['target']}({r['type']})：{r['attitude']}"
                    for r in brief["relationships"]
                )
                prompt += f"\n   关系：{rel_str}"

        prompt += (
            f"\n\n判断哪些角色会自然想插话。最多选{MAX_INTERJECTORS}个，按可能性排序。"
            "只返回JSON数组，如：[\"bronya\", \"tighnari\"]\n无则返回：[]"
        )

        client = LLMServiceClient(task_name="replyer", request_type="butler_filter")
        def message_factory(_client):
            return [MessageBuilder().set_role(RoleType.User).add_text_part(prompt).build()]

        try:
            result = await client.generate_response_with_messages(
                message_factory=message_factory,
                options=LLMGenerationOptions(temperature=0.3),
            )
            response = (result.response or "").strip()
            if "[" in response and "]" in response:
                start = response.index("[")
                end = response.rindex("]") + 1
                response = response[start:end]
            selected_ids = json.loads(response)
            if not isinstance(selected_ids, list):
                return []
            return [
                candidate_map[aid]
                for aid in selected_ids
                if aid in candidate_map
            ][:MAX_INTERJECTORS]
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"[butler] LLM筛选失败: {e}")
            return []

    async def decide_interjection(
        self,
        user_text: str,
        agent_text: str,
    ) -> list[InterjectionCandidate]:
        """管家决策：谁该插话。"""
        candidates = self._rule_filter(user_text, agent_text)
        if not candidates:
            return []
        return await self._llm_filter(user_text, agent_text, candidates)

    def mark_interjected(self, agent_id: str) -> None:
        """标记智能体刚插过话，进入冷却。"""
        self._last_interjection[agent_id] = time.time()

    # ── 提醒流 ──────────────────────────────────────────

    def check_reminders(self) -> list[Reminder]:
        """检查到期的提醒。"""
        return self._reminder_manager.check_due(self._session_id)

    async def try_create_reminder(
        self,
        text: str,
        agent_id: str,
        client=None,
    ) -> Reminder | None:
        """尝试从用户消息中创建提醒。"""
        return await self._reminder_manager.try_create(
            text=text,
            session_id=self._session_id,
            agent_id=agent_id,
            client=client,
        )

    # ── 发送 ──────────────────────────────────────────

    async def send(
        self,
        text: str,
        *,
        agent_id: str = "",
        source: str = "core",
    ) -> bool:
        """通过 MessagePort 发送消息。"""
        return await self._message_port.send(
            session_id=self._session_id,
            text=text,
            agent_id=agent_id,
            source=source,
        )