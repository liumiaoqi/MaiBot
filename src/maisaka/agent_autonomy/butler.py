"""管家系统 — 彼岸居客厅规则。

管家不是第14个角色，是"谁在客厅谁就回消息"这个自然规则的实现。
核心定位：过滤（谁看见了消息）和协调（谁先抢到键盘）。

两条流共享同一管道：
- 对话流：用户消息 → 主智能体回复 → 管家协调插话
- 提醒流：定时器触发 → 管家协调谁提醒 → 主智能体优先
"""


import json
import math
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.common.logger import get_logger
from src.maisaka.agent.config import AgentConfig
from src.core.adapters.agent_config_port import get_agent_config_provider
from src.maisaka.agent_autonomy.reminder import ReminderManager, Reminder
from src.maisaka.agent_autonomy.speaker_transfer import (
    ButlerConfig,
    SpeakerTransferType,
    TransferDecision,
    TransferDecisionSource,
)
from src.core.message_port_registry import get_message_port_v2
from src.core.protocols import MessagePortV2
from src.maisaka.agent_autonomy.log_utils import fmt_butler

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

        # 发言权转移状态追踪
        self._consecutive_silent_count: int = 0
        self._consecutive_responder: tuple[str, int] | None = None
        self._butler_takeover_count: int = 0
        self._borrow_counts: dict[str, int] = {}

        # 管家自己的配置（丽塔·洛丝薇瑟）
        self._butler_config: AgentConfig | None = None
        self._butler_id: str = ""
        self._butler_display_name: str = "管家"
        self._butler_personality: str = ""
        self._butler_anti_mechanization: list[str] = []

        self._load_agents()

    def _load_agents(self) -> None:
        """加载智能体信息，含管家配置。"""
        registry = get_agent_config_provider()
        agents = registry.list_agents()

        for agent in agents:
            # 加载管家配置
            if getattr(agent, "is_butler", False):
                self._butler_config = agent
                self._butler_id = agent.agent_id
                self._butler_display_name = agent.display_name
                self._butler_personality = (
                    agent.layered_personality.expression_layer
                    if agent.layered_personality and agent.layered_personality.expression_layer
                    else ""
                )
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

        # 解析发言权转移配置
        butler_config_dict = {}
        if self._butler_config and self._butler_config.butler_config:
            butler_config_dict = self._butler_config.butler_config
        self._butler_transfer_config = ButlerConfig(**butler_config_dict)

    @property
    def reminder_manager(self) -> ReminderManager:
        return self._reminder_manager

    # ── 发言权转移状态管理 ──────────────────────────────

    def update_primary_status(self, status: str, responder_id: str = "") -> None:
        """更新主智能体状态，维护发言权转移计数器。

        由 Orchestrator 在主智能体回复/沉默后调用。
        """
        if status == "reply":
            self._consecutive_silent_count = 0
            self._butler_takeover_count = 0
            if responder_id:
                if self._consecutive_responder and self._consecutive_responder[0] == responder_id:
                    self._consecutive_responder = (responder_id, self._consecutive_responder[1] + 1)
                else:
                    self._consecutive_responder = (responder_id, 1)
        elif status == "silent":
            self._consecutive_silent_count += 1
        elif status == "butler_takeover":
            self._butler_takeover_count += 1

    def update_primary(self, new_primary_id: str) -> None:
        """永久转移后更新管家追踪的主发言智能体，重置所有计数器。"""
        self._primary_agent_id = new_primary_id
        # 更新显示名称
        for brief in self._resident_briefs:
            if brief["id"] == new_primary_id:
                self._primary_display_name = brief["name"]
                break
        # 重置所有计数器
        self._consecutive_silent_count = 0
        self._consecutive_responder = None
        self._butler_takeover_count = 0
        self._borrow_counts = {}
        logger.info(fmt_butler(
            f"主发言更新→{new_primary_id}", butler_id=self._butler_id,
            butler_name=self._butler_display_name,
        ))

    def record_borrow(self, agent_id: str) -> None:
        """记录一次临时借用。"""
        self._borrow_counts[agent_id] = self._borrow_counts.get(agent_id, 0) + 1

    # ── 对话流 ──────────────────────────────────────────

    def _rule_filter(self, user_text: str, agent_text: str) -> list[InterjectionCandidate]:
        """第一层：规则过滤（零成本）。

        LS-4: has_relation 分支使用 Sigmoid 映射 coactivation_strength，
        公式: 0.2 + 0.6 / (1 + exp(-8 * (x - 0.5)))
        """
        all_text = f"{user_text} {agent_text}"
        candidates = []

        # LS-4: 预加载共激活强度
        coactivation_map = self._get_coactivation_map()

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
            elif has_relation:
                # LS-4: Sigmoid 映射 coactivation_strength
                coactivation = coactivation_map.get(aid, 0.0)
                prob = self._sigmoid_interjection_prob(coactivation)
                if focus_matched:
                    prob += 0.1
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

    @staticmethod
    def _sigmoid_interjection_prob(coactivation: float) -> float:
        """LS-4: Sigmoid 映射 coactivation → 插话概率。

        prob = 0.2 + 0.6 / (1 + exp(-8 * (x - 0.5)))
        coactivation=0 → ~0.21, 0.5 → 0.50, 1.0 → ~0.79
        """
        return 0.2 + 0.6 / (1.0 + math.exp(-8.0 * (coactivation - 0.5)))

    def _get_coactivation_map(self) -> dict[str, float]:
        """LS-4: 返回预加载的共激活映射。由 _load_coactivation_map 填充。"""
        return getattr(self, "_coactivation_cache", {})

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
        from src.core.adapters.llm_service_port import get_llm_service

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

        def message_factory(_client):
            return [MessageBuilder().set_role(RoleType.User).add_text_part(prompt).build()]

        try:
            result = await get_llm_service().generate_response_with_messages(
                "replyer", message_factory,
                LLMGenerationOptions(temperature=0.3),
                request_type="butler_filter",
            )
            response = (result.response or "").strip()
            if "[" in response and "]" in response:
                start = response.index("[")
                end = response.rindex("]") + 1
                response = response[start:end]
            selected_ids = json.loads(response)
            if not isinstance(selected_ids, list):
                return []
            result = [
                candidate_map[aid]
                for aid in selected_ids
                if aid in candidate_map
            ][:MAX_INTERJECTORS]
            if result:
                names = ",".join(r.display_name for r in result)
                logger.info(fmt_butler(
                    "插话决策", butler_id=self._butler_id, butler_name=self._butler_display_name,
                    extra=f"candidates={len(candidates)} selected={len(result)} → {names}",
                ))
            return result
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"[butler] LLM筛选失败: {e}")
            return []

    async def decide_interjection(
        self,
        user_text: str,
        agent_text: str,
    ) -> list[InterjectionCandidate]:
        """管家决策：谁该插话。"""
        # LS-4: 预加载共激活强度供 _rule_filter 使用
        await self._load_coactivation_map()
        candidates = self._rule_filter(user_text, agent_text)
        if not candidates:
            return []
        return await self._llm_filter(user_text, agent_text, candidates)

    async def _load_coactivation_map(self) -> None:
        """LS-4: 异步加载共激活强度到缓存。"""
        try:
            from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager

            rel_manager = AgentRelationshipManager()
            result = {}
            for aid in self._resident_ids:
                result[aid] = await rel_manager.get_coactivation(aid, self._primary_agent_id)
            self._coactivation_cache = result
        except Exception as exc:
            logger.debug(f"[butler] 共激活加载失败: error={exc}")
            self._coactivation_cache = {}

    def mark_interjected(self, agent_id: str) -> None:
        """标记智能体刚插过话，进入冷却。"""
        self._last_interjection[agent_id] = time.time()

    # ── 发言权转移决策 ──────────────────────────────────

    _SWITCH_KEYWORDS = ("接管", "来回答", "换你", "你来", "你来回答", "你来说", "你来处理", "你来接")

    def _evaluate_permanent_transfer(self, user_text: str) -> TransferDecision | None:
        """纯规则判断永久转移条件。

        优先级：用户明确要求 > 连续沉默 > 连续回应。
        can_switch_primary=False 时返回 None。
        """
        if not self._butler_transfer_config.can_switch_primary:
            return None

        # 1) 用户明确要求切换
        for brief in self._resident_briefs:
            name = brief["name"]
            aid = brief["id"]
            mentioned = name in user_text or aid in user_text
            if mentioned and any(kw in user_text for kw in self._SWITCH_KEYWORDS):
                return TransferDecision(
                    transfer_type=SpeakerTransferType.PERMANENT_TRANSFER,
                    target_agent_id=aid,
                    reason=f"用户明确要求切换到{name}",
                    decision_source=TransferDecisionSource.RULE,
                    display_name=name,
                )

        # 2) 主智能体连续沉默达阈值
        if self._consecutive_silent_count >= self._butler_transfer_config.consecutive_silent_threshold:
            target = self._find_best_transfer_target(user_text)
            if target:
                return TransferDecision(
                    transfer_type=SpeakerTransferType.PERMANENT_TRANSFER,
                    target_agent_id=target["id"],
                    reason=f"主智能体连续{self._consecutive_silent_count}次沉默",
                    decision_source=TransferDecisionSource.RULE,
                    display_name=target["name"],
                )

        # 3) 连续回应同一共居者达阈值
        if (self._consecutive_responder
                and self._consecutive_responder[1] >= self._butler_transfer_config.consecutive_response_threshold):
            aid = self._consecutive_responder[0]
            name = next((b["name"] for b in self._resident_briefs if b["id"] == aid), "")
            if name:
                return TransferDecision(
                    transfer_type=SpeakerTransferType.PERMANENT_TRANSFER,
                    target_agent_id=aid,
                    reason=f"{name}连续回应{self._consecutive_responder[1]}次",
                    decision_source=TransferDecisionSource.RULE,
                    display_name=name,
                )

        return None

    def _evaluate_borrow_upgrade(self) -> TransferDecision | None:
        """借用升级评估：同一智能体借用次数达阈值时评估永久转移。"""
        if not self._butler_transfer_config.can_switch_primary:
            return None

        threshold = self._butler_transfer_config.borrow_upgrade_threshold
        for aid, count in self._borrow_counts.items():
            if count >= threshold:
                name = next((b["name"] for b in self._resident_briefs if b["id"] == aid), "")
                if name:
                    return TransferDecision(
                        transfer_type=SpeakerTransferType.PERMANENT_TRANSFER,
                        target_agent_id=aid,
                        reason=f"{name}连续借用{count}次，升级为永久转移",
                        decision_source=TransferDecisionSource.RULE,
                        display_name=name,
                    )
        return None

    async def decide_speaker_transfer(
        self,
        user_text: str,
        agent_text: str,
        primary_status: str,
    ) -> list[TransferDecision]:
        """管家发言权转移统一决策入口。

        根据 primary_status 决定决策路径：
        - "reply": 复用三层过滤，输出 TEMPORARY_BORROW
        - "silent": 先评估永久转移，再评估临时借用
        多决策优先级：永久转移最多1个，临时借用最多2个，永久转移优先执行。
        """
        decisions: list[TransferDecision] = []

        if primary_status == "silent":
            # 先评估永久转移
            perm = self._evaluate_permanent_transfer(user_text)
            if perm is not None:
                decisions.append(perm)
                # 永久转移优先，不再评估临时借用
                return decisions

        # 复用三层过滤，输出临时借用
        candidates = await self.decide_interjection(user_text, agent_text)
        for c in candidates[:MAX_INTERJECTORS]:
            decisions.append(TransferDecision(
                transfer_type=SpeakerTransferType.TEMPORARY_BORROW,
                target_agent_id=c.agent_id,
                reason="管家三层过滤选中",
                decision_source=TransferDecisionSource.LLM if c.has_relation or c.is_mentioned else TransferDecisionSource.RULE,
                display_name=c.display_name,
            ))

        # 检查借用升级（仅在非永久转移时）
        if not any(d.transfer_type == SpeakerTransferType.PERMANENT_TRANSFER for d in decisions):
            upgrade = self._evaluate_borrow_upgrade()
            if upgrade is not None:
                decisions.insert(0, upgrade)

        if decisions:
            descs = ",".join(f"{d.target_agent_id}({d.transfer_type.value})" for d in decisions)
            logger.info(fmt_butler(
                "发言权决策", butler_id=self._butler_id, butler_name=self._butler_display_name,
                extra=f"status={primary_status} decisions=[{descs}]",
            ))

        return decisions

    def _find_best_transfer_target(self, user_text: str) -> dict | None:
        """根据话题匹配找到最佳转移目标。"""
        user_text_lower = user_text.lower()
        best: dict | None = None
        best_score = 0
        for brief in self._resident_briefs:
            score = 0
            focus_areas = brief.get("focus_areas", [])
            if focus_areas:
                for area in focus_areas:
                    if area.lower() in user_text_lower:
                        score += 2
            if brief["name"] in user_text or brief["id"] in user_text:
                score += 3
            has_relation = any(
                r["target"] == self._primary_agent_id
                for r in brief["relationships"]
            )
            if has_relation:
                score += 1
            if score > best_score:
                best_score = score
                best = brief
        return best

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
        from src.core.adapters.llm_service_port import get_llm_service

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

        def message_factory(_client):
            return [
                MessageBuilder().set_role(RoleType.System).add_text_part(system_prompt).build(),
                MessageBuilder().set_role(RoleType.User).add_text_part(user_prompt).build(),
            ]

        try:
            result = await get_llm_service().generate_response_with_messages(
                "replyer", message_factory,
                LLMGenerationOptions(temperature=0.7),
                request_type="butler_speak",
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

        # 添加管家名字前缀
        from src.maisaka.agent_autonomy.bridge.reply_context_extender import ReplyToolContextExtender
        text = ReplyToolContextExtender.prepend_speaker_tag_to_content(
            text, self._butler_id, True,
        )
        success = await self.send(text, agent_id=self._butler_id, source="butler_speak")
        if success:
            logger.info(fmt_butler(
                f"发言(text_len={len(text)})", butler_id=self._butler_id,
                butler_name=self._butler_display_name,
                extra=f"context={context_hint[:30] if context_hint else 'auto'}",
            ))
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
