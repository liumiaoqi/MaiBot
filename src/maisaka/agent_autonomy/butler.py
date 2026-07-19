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
from src.core.message_port_registry import get_message_port_v2
from src.core.protocols import MessagePortV2

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
    """管家 — 丽塔·洛丝薇瑟，客厅的守护者。

    管家是第14个智能体，有自己的人格和回复。
    三层过滤：
    1. 规则过滤（零成本）：名字被提到→必看见；有关系→可能看见；无关→很少看见
    2. 管家LLM（1次调用）：理解话题+角色性格+关系网，判断"谁会关心"
    3. 角色LLM（仅选中者）：被选中的角色决定插话内容

    管家自己也会发言——引导话题、提醒、接话，使用 rita 的人格。
    """

    def __init__(
        self,
        primary_agent_id: str,
        session_id: str,
        reminder_manager: ReminderManager | None = None,
        message_port: MessagePortV2 | None = None,
    ) -> None:
        self._primary_agent_id = primary_agent_id
        self._session_id = session_id
        self._reminder_manager = reminder_manager or ReminderManager()
        self._message_port = message_port or get_message_port_v2()

        self._resident_briefs: list[dict] = []
        self._resident_ids: list[str] = []
        self._primary_display_name: str = ""
        self._last_interjection: dict[str, float] = {}
        self._interjection_cooldown = 30.0

        # 管家自己的配置（丽塔·洛丝薇瑟）
        self._butler_config: AgentConfig | None = None
        self._butler_id: str = ""
        self._butler_display_name: str = "管家"
        self._butler_personality: str = ""
        self._butler_anti_mechanization: list[str] = []

        self._load_agents()

    def _load_agents(self) -> None:
        """从 AgentConfigRegistry 加载智能体信息，含管家配置。"""
        registry = AgentConfigRegistry.get_instance()
        agents = registry.list_agents()

        for agent in agents:
            # 加载管家配置
            if getattr(agent, "is_butler", False):
                self._butler_config = agent
                self._butler_id = agent.agent_id
                self._butler_display_name = agent.display_name
                self._butler_personality = agent.personality or ""
                self._butler_anti_mechanization = list(agent.anti_mechanization_rules or [])
                logger.info(
                    f"[butler] 管家配置加载: id={agent.agent_id} name={agent.display_name}"
                )
                continue

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
            f"butler={self._butler_id or '未配置'} "
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

        # 注入管家人格——丽塔不是通用AI，是客厅的守护者
        butler_identity = self._butler_personality[:200] if self._butler_personality else "客厅的守护者，优雅而敏锐"
        anti_mech = "\n".join(f"- {r}" for r in self._butler_anti_mechanization[:3]) if self._butler_anti_mechanization else ""

        prompt = f"你是{self._butler_display_name}。{butler_identity}\n"
        if anti_mech:
            prompt += f"\n注意：\n{anti_mech}\n"
        prompt += (
            f"\n你正在观察客厅里的对话，判断哪些角色会对这段对话感兴趣并可能想插话。\n\n"
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

    # ── 管家自己发言 ──────────────────────────────────

    async def speak_self(
        self,
        user_text: str,
        agent_text: str,
        context_hint: str = "",
    ) -> str | None:
        """管家以丽塔的人格自己发言。

        场景：主智能体 SILENT 时管家接管、引导话题、提醒等。
        返回发言文本，None 表示管家选择不说话。
        """
        if not self._butler_config:
            return None

        from src.llm_models.payload_content.message import MessageBuilder, RoleType
        from src.common.data_models.llm_service_data_models import LLMGenerationOptions
        from src.services.llm_service import LLMServiceClient

        now = _now()
        parts = [
            f"当前时间：{now.strftime('%Y年%m月%d日 %H:%M')}（{'一二三四五六日'[now.weekday()]}）",
        ]
        if self._butler_personality:
            parts.append(self._butler_personality)
        if self._butler_config.reply_style:
            parts.append(f"表达风格：{self._butler_config.reply_style}")
        if self._butler_config.internal_relationships:
            parts.append(self._butler_config.internal_relationships_prompt)

        system_prompt = "\n\n".join(parts)

        context_parts = []
        if user_text:
            context_parts.append(f"用户说：{user_text}")
        if agent_text:
            context_parts.append(f"{self._primary_display_name}回复：{agent_text}")
        if context_hint:
            context_parts.append(context_hint)

        context = "\n".join(context_parts) if context_parts else "（无具体内容，管家主动发言）"

        user_prompt = (
            f"{context}\n\n"
            f"你是{self._butler_display_name}，客厅的守护者。"
            f"根据你的判断，自然地说一句话——可以是接话、引导话题、提醒、或者只是表达你的存在。"
            f"如果你觉得此刻不需要你说话，回复：NONE"
        )

        client = LLMServiceClient(task_name="replyer", request_type="butler_speak")
        def message_factory(_client):
            return [
                MessageBuilder().set_role(RoleType.System).add_text_part(system_prompt).build(),
                MessageBuilder().set_role(RoleType.User).add_text_part(user_prompt).build(),
            ]

        try:
            result = await client.generate_response_with_messages(
                message_factory=message_factory,
                options=LLMGenerationOptions(temperature=0.7),
            )
            response = (result.response or "").strip()
            if response == "NONE" or not response:
                return None
            return response
        except Exception as e:
            logger.warning(f"[butler] 管家发言失败: {e}")
            return None

    async def speak_and_send(
        self,
        user_text: str = "",
        agent_text: str = "",
        context_hint: str = "",
    ) -> bool:
        """管家发言并发送。返回是否发送成功。"""
        text = await self.speak_self(user_text, agent_text, context_hint)
        if text is None:
            return False

        success = await self.send(text, agent_id=self._butler_id, source="butler_speak")
        if success:
            logger.info(
                f"[butler] 管家发言: agent={self._butler_id} "
                f"text_len={len(text)} session={self._session_id}"
            )
        return success

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
        """通过 MessagePortV2 发送消息。"""
        from src.common.data_models.message_component_data_model import MessageSequence, TextComponent

        result = await self._message_port.send_message(
            session_id=self._session_id,
            message=MessageSequence(components=[TextComponent(text=text)]),
            agent_id=agent_id,
            source=source,
        )
        return result.success