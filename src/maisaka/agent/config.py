from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.common.logger import get_logger
logger = get_logger(__name__)



class TimeTriggerRule(BaseModel):
    """定时触发规则"""

    trigger_type: str = Field(default="greeting", description="触发类型：greeting/festival/custom")
    time_range: str = Field(default="", description="触发时间范围，如 07:00-09:00")
    message_template: str = Field(default="", description="触发消息模板")
    enabled: bool = Field(default=True)


class TimeBehaviorProfile(BaseModel):
    """时间行为画像"""

    morning_active_coefficient: float = Field(default=0.5, ge=0.0, le=2.0, description="早晨活跃系数")
    afternoon_active_coefficient: float = Field(default=0.8, ge=0.0, le=2.0, description="下午活跃系数")
    evening_active_coefficient: float = Field(default=0.8, ge=0.0, le=2.0, description="傍晚活跃系数")
    night_active_coefficient: float = Field(default=0.3, ge=0.0, le=2.0, description="深夜活跃系数")
    greeting_rules: list[TimeTriggerRule] = Field(default_factory=list, description="定时触发规则")


class ProactiveConfig(BaseModel):
    """主动对话配置"""

    enabled: bool = Field(default=True, description="是否启用主动对话")
    max_frequency_per_hour: int = Field(default=1, ge=0, le=10, description="每小时最大主动对话次数")
    cooldown_seconds: int = Field(default=300, ge=0, description="主动对话冷却时间（秒）")
    trigger_threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="主动对话触发阈值")
    allowed_session_types: list[str] = Field(default_factory=lambda: ["group", "private"], description="允许主动对话的会话类型")


class EmotionBehaviorRule(BaseModel):
    """情绪-行为映射规则"""

    emotion_type: str = Field(default="", description="情绪类型")
    intensity_threshold: int = Field(default=50, ge=0, le=100, description="强度阈值")
    behavior_tendency: str = Field(default="", description="行为倾向描述")
    reply_style_modifier: str = Field(default="", description="回复风格修饰描述")


class InternalRelationship(BaseModel):
    """智能体内部关系"""

    target_agent_id: str = Field(default="", description="关系对象智能体ID")
    relationship_type: str = Field(default="friend", description="关系类型：family/romantic/rival/mentor/friend")
    attitude: str = Field(default="", description="态度描述")
    interaction_style: str = Field(default="", description="互动风格描述")
    mention_tendency: float = Field(default=0.3, ge=0.0, le=1.0, description="提及倾向")
    anti_mechanization: str = Field(default="", description="反机械化约束")


class EventReactionRule(BaseModel):
    """群事件反应规则"""

    event_type: str = Field(default="", description="事件类型")
    reaction_probability: float = Field(default=0.5, ge=0.0, le=1.0, description="反应概率")
    reaction_style: str = Field(default="", description="反应风格描述")
    emotion_trigger: dict[str, int] = Field(default_factory=dict, description="情绪触发映射")


class PermissionRule(BaseModel):
    """权限规则"""

    action: str = Field(default="", description="权限动作")
    rule: str = Field(default="allow", description="规则：allow/deny/limited/own_only/private_only")


class DeepSeekOptimizationConfig(BaseModel):
    """DeepSeek 深度优化配置"""

    enabled: bool = Field(default=True, description="是否启用DeepSeek深度优化")
    injection_strategy: str = Field(
        default="adaptive",
        description="上下文注入策略：full(1M全量)/adaptive(按优先级截断)/lean(128K精简)",
    )
    injection_priority: list[str] = Field(
        default_factory=lambda: ["identity", "anti_mechanization", "interaction_memory", "profile", "mid_term", "heuristic"],
        description="上下文注入优先级（从高到低）",
    )
    token_budget_ratio: float = Field(default=1.0, ge=0.1, le=2.0, description="Token预算分配比例")
    prefix_cache_enabled: bool = Field(default=True, description="是否启用前缀缓存优化")
    prefix_cache_priority: list[str] = Field(
        default_factory=lambda: ["system", "identity", "emotion_baseline", "internal_relationships", "interaction_memory"],
        description="前缀缓存稳定层优先级",
    )
    batch_api_enabled: bool = Field(default=True, description="是否启用批处理API")
    batch_scheduling_preference: str = Field(
        default="auto",
        description="批处理调度偏好：auto/always/never",
    )
    thinking_mode_conditions: list[str] = Field(
        default_factory=lambda: ["complex_reasoning", "emotional_decision"],
        description="思考模式启用条件",
    )
    model_scheduling_preference: str = Field(
        default="auto",
        description="模型调度偏好：auto/pro/flash",
    )
    cost_budget_threshold: float = Field(
        default=1.2, ge=0.5, le=3.0,
        description="成本预算阈值（倍率），超过时自动降低低优先级注入",
    )


class MemoryPersonalityV2(BaseModel):
    """记忆性格 v2 — 智能体对记忆的个性化处理参数（对齐 lab v0.7 八参数模型）"""

    decay_rate: float = Field(default=0.5, ge=0.1, le=5.0, description="记忆衰减率，值越大遗忘越快")
    emotional_sensitivity: float = Field(default=0.5, ge=0.1, le=3.0, description="情感敏感度，值越高情感对记忆影响越大")
    association_depth: int = Field(default=2, ge=1, le=4, description="联想深度，值越高记忆间联想越深")
    attention_tags: list[str] = Field(default_factory=list, description="关注领域标签，这些概念更容易被记住")
    positive_affinity: float = Field(default=0.5, ge=0.0, le=3.0, description="正面情感亲和度")
    negative_affinity: float = Field(default=0.5, ge=0.0, le=3.0, description="负面情感亲和度")
    curiosity: float = Field(default=0.5, ge=0.1, le=2.0, description="好奇心/记忆门槛，只影响阈值不乘分数")
    reinforcement_boost: float = Field(default=0.3, ge=0.1, le=1.0, description="强化增幅，重复体验的强化程度")


class InnerVoiceStyle(Enum):
    """内心声音处理风格"""

    AMPLIFY = "AMPLIFY"
    NEUTRALIZE = "NEUTRALIZE"
    PRESERVE = "PRESERVE"
    INVERT = "INVERT"
    CHAOTIC = "CHAOTIC"


class InnerVoiceConfig(BaseModel):
    """内心声音配置 — 角色驱动的多声音系统（对齐 lab v0.9）"""

    name: str = Field(default="", description="声音名称，如'恶作剧心'、'游戏瘾'")
    style: InnerVoiceStyle = Field(default=InnerVoiceStyle.PRESERVE, description="处理风格")
    valence_bias: str = Field(default="NEUTRAL", description="情感偏移：POSITIVE/NEGATIVE/NEUTRAL")
    concept_focus: list[str] = Field(default_factory=list, description="关注概念列表")
    weight_multiplier: float = Field(default=1.0, ge=0.0, le=3.0, description="权重倍率")


class FavorDescriptions(BaseModel):
    """偏爱描述 — 每个智能体对不同关系用户的偏爱行为描述"""

    owner: str = Field(default="", description="对主人的偏爱描述")
    friend: str = Field(default="", description="对主人朋友的偏爱描述")
    stranger: str = Field(default="", description="对陌生人的偏爱描述")


class PersonalityLayer(Enum):
    """性格四层模型 — 层枚举"""

    EXISTENCE = "existence"       # 存在层：时代世界 + 不可转移的社会存在
    EXPRESSION = "expression"     # 表现层：外显行为模式
    EXPERIENCE = "experience"     # 体验层：真实感受
    IDENTITY = "identity"         # 认同层：自我认知


class LayeredPersonality(BaseModel):
    """性格四层模型 — 替代扁平 personality 文本"""

    existence_layer: str = Field(default="", description="存在层：时代世界+不可转移的社会存在（不可修改）")
    expression_layer: str = Field(default="", description="表现层：外显行为模式")
    experience_layer: str = Field(default="", description="体验层：真实感受、内心性格")
    identity_layer: str = Field(default="", description="认同层：自我认知、'我认为自己是什么样的人'")
    self_constraints: str = Field(default="", description="自我约束：'我绝不...'（认同层派生，LS-7 不可绕过）")

    def get_layer_text(self, layer: PersonalityLayer) -> str:
        """获取指定层的文本"""
        match layer:
            case PersonalityLayer.EXISTENCE:
                return self.existence_layer
            case PersonalityLayer.EXPRESSION:
                return self.expression_layer
            case PersonalityLayer.EXPERIENCE:
                return self.experience_layer
            case PersonalityLayer.IDENTITY:
                return self.identity_layer

    def set_layer_text(self, layer: PersonalityLayer, text: str) -> None:
        """设置指定层的文本（存在层不可修改）"""
        if layer == PersonalityLayer.EXISTENCE:
            raise ValueError("存在层不可修改——这是角色的世界设定，不是可变的性格特征")
        match layer:
            case PersonalityLayer.EXPRESSION:
                self.expression_layer = text
            case PersonalityLayer.EXPERIENCE:
                self.experience_layer = text
            case PersonalityLayer.IDENTITY:
                self.identity_layer = text

    def is_modifiable(self, layer: PersonalityLayer) -> bool:
        """判断指定层是否可被 LS-7 工具修改"""
        return layer != PersonalityLayer.EXISTENCE


class LayeredPersonalityConfig(BaseModel):
    """六算法公共参数 — 所有参数零 LLM 调用"""

    # A5: 锚定/可塑
    plasticity_n_mid: int = Field(default=50, ge=20, le=200, description="半固化所需交互次数")
    plasticity_k: float = Field(default=0.05, ge=0.01, le=0.1, description="固化速率常数")
    plasticity_min: float = Field(default=0.05, ge=0.01, le=0.2, description="最小可塑性（floor）")
    re_plastication_boost: float = Field(default=0.3, ge=0.01, le=0.5, description="新角色投资重新可塑提升量")

    # A2: 加权检索
    recall_gamma: float = Field(default=0.95, ge=0.8, le=0.999, description="recency 衰减系数（Park 修正）")

    # A3: λ 内言语控制
    default_lambda: float = Field(default=0.5, ge=0.0, le=1.0, description="默认内言语贡献系数")
    lambda_emotion_threshold: float = Field(default=0.6, ge=0.0, le=1.0, description="情绪触发 λ 提升的强度阈值")
    lambda_emotion_scale: float = Field(default=0.5, ge=0.0, le=1.0, description="情绪对 λ 的提升幅度")
    lambda_relationship_scale: float = Field(default=0.3, ge=0.0, le=1.0, description="关系对 λ 的提升幅度")

    # A1: 自我差异
    discrepancy_d_norm: float = Field(default=1.0, ge=0.5, le=2.0, description="差异幅度归一化除数")

    # A6: 自我验证
    verification_certainty_threshold: float = Field(default=0.6, ge=0.3, le=0.9, description="自我确定度阈值")
    verification_public_threshold: float = Field(default=0.5, ge=0.3, le=0.9, description="公开场合判断阈值")
    verification_temperature: float = Field(default=0.3, ge=0.1, le=1.0, description="选择性注意 softmax 温度")

    # A4: 预测处理
    predictive_l0_lr: float = Field(default=0.1, ge=0.01, le=0.5, description="L0 学习率（情绪层，较快）")
    predictive_l1_lr: float = Field(default=0.05, ge=0.01, le=0.5, description="L1 学习率（行为层）")
    predictive_l2_lr: float = Field(default=0.01, ge=0.001, le=0.1, description="L2 学习率（认同层，极慢）")


class InnerSpeechStyleConfig(BaseModel):
    """内言语风格配置 — 对应 Granato λ 参数 + Fernyhough 压缩度"""

    style: Literal["fragmented", "narrative"] = Field(
        default="fragmented", description="内言语风格：碎片化(fragmented)或完整叙事(narrative)"
    )
    condensation: float = Field(default=0.7, ge=0.0, le=1.0, description="压缩度（Fernyhough L3-L4），越高越压缩/简短")
    voice_count: int = Field(default=1, ge=1, le=5, description="多声部对话中的声音数量")


class AgentConfig(BaseModel):
    """智能体配置模型"""

    agent_id: str = Field(default="silver_wolf", description="智能体唯一标识")
    display_name: str = Field(default="银狼", description="显示名称")
    personality: str = Field(default="", description="人格设定（Markdown正文部分）[deprecated: 迁移到 layered_personality]")
    reply_style: str = Field(default="", description="表达风格描述")
    is_default: bool = Field(default=False, description="是否为默认智能体")

    # 情绪参数
    emotion_baseline: dict[str, int] = Field(
        default_factory=lambda: {
            "happy": 40, "sad": 10, "anxious": 10,
            "angry": 8, "calm": 45, "excited": 30, "lonely": 15,
        },
        description="情绪基线（情绪类型→强度0-100）",
    )
    emotion_decay_rate: float = Field(default=0.12, ge=0.0, le=1.0, description="情绪衰减速率（每小时）")
    emotion_behavior_map: list[EmotionBehaviorRule] = Field(default_factory=list, description="情绪-行为映射规则")

    # 时间行为
    time_behavior_profile: TimeBehaviorProfile = Field(default_factory=TimeBehaviorProfile, description="时间行为画像")

    # 主动对话
    proactive_config: ProactiveConfig = Field(default_factory=ProactiveConfig, description="主动对话配置")

    # 关系进展
    relationship_growth_rate: float = Field(default=1.0, ge=0.1, le=3.0, description="关系进展速率倍率")

    # 回复频率差异化
    talk_value_modifier: float = Field(default=1.0, ge=0.1, le=3.0, description="回复频率修正倍率，>1更活跃，<1更安静")


    # 群事件反应
    event_reaction_rules: list[EventReactionRule] = Field(default_factory=list, description="群事件反应规则")

    # 记忆偏好
    memory_focus_areas: list[str] = Field(default_factory=list, description="记忆焦点领域")

    # 内部关系网
    internal_relationships: list[InternalRelationship] = Field(default_factory=list, description="内部关系网")

    # 反机械化规则
    anti_mechanization_rules: list[str] = Field(default_factory=list, description="反机械化规则")

    # 权限配置
    permission: list[PermissionRule] = Field(default_factory=list, description="权限规则集")
    hard_permission: list[PermissionRule] = Field(default_factory=list, description="不可覆盖的硬权限")

    # 工具白名单
    tool_allowlist: list[str] = Field(default_factory=list, description="工具白名单（空=全部允许）")

    # 提示词覆盖
    planner_prompt_override: str = Field(default="", description="Planner提示词覆盖（空=使用默认模板）")
    replyer_prompt_override: str = Field(default="", description="Replyer提示词覆盖（空=使用默认模板）")

    # 模型配置
    model_config_override: Optional[dict[str, object]] = Field(default=None, description="模型配置覆盖")

    # DeepSeek优化配置
    deepseek: DeepSeekOptimizationConfig = Field(
        default_factory=DeepSeekOptimizationConfig,
        description="DeepSeek深度优化配置",
    )

    # 显示配置
    color: str = Field(default="#9b59b6", description="智能体代表色")

    # 记忆性格（lab v0.7 八参数模型）
    memory_personality: MemoryPersonalityV2 = Field(
        default_factory=MemoryPersonalityV2, description="记忆性格参数"
    )

    # 内心声音（lab v0.9 角色驱动的多声音系统）
    inner_voices: list[InnerVoiceConfig] = Field(
        default_factory=list, description="内心声音配置列表"
    )
    inner_voice_template_text: str = Field(
        default="", description="内心声音模板文本（兼容模式，支持{emotion}/{need}/{situation}占位符）"
    )

    # 偏爱描述（替代硬编码的 favor_map）
    favor_descriptions: FavorDescriptions = Field(
        default_factory=FavorDescriptions, description="偏爱行为描述"
    )

    # 管家配置（第14个智能体——客厅的守护者）
    is_butler: bool = Field(default=False, description="是否为管家智能体")
    butler_config: dict = Field(default_factory=dict, description="管家配置（see_all_messages/coordinate_interjection/handle_reminders/can_switch_primary/can_speak）")

    # LS-7/LS-8: 性格分层
    layered_personality: Optional[LayeredPersonality] = Field(
        default=None, description="四层性格模型（优先于 personality 字段）"
    )
    layered_personality_config: LayeredPersonalityConfig = Field(
        default_factory=LayeredPersonalityConfig, description="六算法公共参数"
    )
    inner_speech_style: InnerSpeechStyleConfig = Field(
        default_factory=InnerSpeechStyleConfig, description="内言语风格配置"
    )

    @property
    def identity_prompt(self) -> str:
        """构建完整的人格提示词。

        从 layered_personality 四层组合（expression→experience→identity→constraints）。
        当 layered_personality 为 None 时 fallback 到 deprecated personality 字段。
        """
        if self.layered_personality is not None:
            parts: list[str] = []
            if self.layered_personality.expression_layer:
                parts.append(self.layered_personality.expression_layer)
            if self.layered_personality.experience_layer:
                parts.append(self.layered_personality.experience_layer)
            if self.layered_personality.identity_layer:
                parts.append(self.layered_personality.identity_layer)
            if self.layered_personality.self_constraints:
                parts.append(f"自我约束：{self.layered_personality.self_constraints}")
            return "\n\n".join(parts)

        logger.warning("identity_prompt: layered_personality 为 None，fallback 到 deprecated personality 字段")
        return self.personality

    @property
    def anti_mechanization_prompt(self) -> str:
        """构建反机械化规则提示词"""
        if not self.anti_mechanization_rules:
            return ""
        lines = ["## 反机械化规则", "", "以下规则用于防止机械化重复，请严格遵守：", ""]
        for i, rule in enumerate(self.anti_mechanization_rules, 1):
            lines.append(f"{i}. {rule}")
        return "\n".join(lines)

    @property
    def internal_relationships_prompt(self) -> str:
        """构建内部关系网提示词（用于话题关联触发时注入）"""
        if not self.internal_relationships:
            return ""
        lines = ["## 你与其他人的关系", ""]
        for rel in self.internal_relationships:
            line = f"- **{rel.target_agent_id}**（{rel.relationship_type}）：{rel.attitude}"
            if rel.interaction_style:
                line += f"。互动方式：{rel.interaction_style}"
            if rel.anti_mechanization:
                line += f"。注意：{rel.anti_mechanization}"
            lines.append(line)
        return "\n".join(lines)

    def get_favor_injection(
        self,
        user_name: str = "用户",
        is_owner: bool = True,
        is_friend_of_owner: bool = False,
    ) -> str:
        """构建偏爱注入提示词（从配置文件读取，替代硬编码 favor_map）"""
        if is_owner and self.favor_descriptions.owner:
            return self.favor_descriptions.owner.replace("{user_name}", user_name)
        if is_friend_of_owner and self.favor_descriptions.friend:
            return self.favor_descriptions.friend.replace("{user_name}", user_name)
        if not is_owner and not is_friend_of_owner and self.favor_descriptions.stranger:
            return self.favor_descriptions.stranger.replace("{user_name}", user_name)
        return f"你关心{user_name}"

    def get_identity_summary(self) -> str:
        """生成供管家系统使用的身份摘要（≤200字）"""
        parts: list[str] = []
        if self.layered_personality and self.layered_personality.expression_layer:
            parts.append(self.layered_personality.expression_layer[:80])
        if self.internal_relationships:
            rel_strs = [
                f"{rel.target_agent_id}({rel.relationship_type})"
                for rel in self.internal_relationships[:5]
            ]
            parts.append(f"关系: {', '.join(rel_strs)}")
        if self.memory_focus_areas:
            parts.append(f"关注: {', '.join(self.memory_focus_areas[:5])}")
        summary = "；".join(parts)
        if not summary:
            return f"{self.display_name}（无性格描述）"
        return summary[:200]
