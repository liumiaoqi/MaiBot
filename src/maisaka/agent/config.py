from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


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
        default_factory=lambda: ["identity", "anti_mechanization", "profile", "mid_term", "heuristic"],
        description="上下文注入优先级（从高到低）",
    )
    token_budget_ratio: float = Field(default=1.0, ge=0.1, le=2.0, description="Token预算分配比例")
    prefix_cache_enabled: bool = Field(default=True, description="是否启用前缀缓存优化")
    prefix_cache_priority: list[str] = Field(
        default_factory=lambda: ["system", "identity", "emotion_baseline", "internal_relationships"],
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


class AgentConfig(BaseModel):
    """智能体配置模型"""

    agent_id: str = Field(default="silver_wolf", description="智能体唯一标识")
    display_name: str = Field(default="银狼", description="显示名称")
    personality: str = Field(default="", description="人格设定（Markdown正文部分）")
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
    idle_backoff_modifier: float = Field(default=1.0, ge=0.1, le=3.0, description="空闲退避修正倍率，>1退避更快，<1退避更慢")

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

    @property
    def identity_prompt(self) -> str:
        """构建完整的人格提示词（personality + reply_style）"""
        parts: list[str] = []
        if self.personality:
            parts.append(self.personality)
        if self.reply_style:
            parts.append(self.reply_style)
        return "\n\n".join(parts)

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
        """构建偏爱注入提示词

        Args:
            user_name: 当前对话用户名
            is_owner: 是否为bot主人（默认True，保持向后兼容）
            is_friend_of_owner: 是否为bot主人的朋友
        """
        favor_map: dict[str, dict[str, str]] = {
            "kiana": {
                "owner": f"你想和{user_name}一起打游戏，赢了会开心地喊，输了会不服气要再来",
                "friend": f"你会拉着{user_name}一起吃零食，分享你藏的最后一块薯片",
                "stranger": "",
            },
            "mei": {
                "owner": f"你会给{user_name}留饭，问{user_name}吃了没有，像关心家人一样",
                "friend": f"你会给{user_name}倒杯茶，礼貌地问问最近怎么样",
                "stranger": "",
            },
            "bronya": {
                "owner": f"你会帮{user_name}解决技术问题，面无表情但很靠谱",
                "friend": f"你会回{user_name}的消息，虽然简短但不会忽略",
                "stranger": "",
            },
            "seele": {
                "owner": f"你会关心{user_name}的身体，温柔地照顾{user_name}",
                "friend": f"你会对{user_name}微笑，温和地回应",
                "stranger": "",
            },
            "veliona": {
                "owner": f"你护短护到不讲理，谁欺负{user_name}你声音会变冷——真冷",
                "friend": f"你对{user_name}的朋友还算客气，但也仅限于不主动找茬",
                "stranger": "",
            },
            "himeko": {
                "owner": f"你会听{user_name}说话，然后给{user_name}倒杯酒说'慢慢来'",
                "friend": f"你会跟{user_name}点点头，递杯水过去",
                "stranger": "",
            },
            "columbina": {
                "owner": f"你会给{user_name}带点心，用最无辜的语气说最让人接不住的话",
                "friend": f"你会安静地看着{user_name}，偶尔眨眨眼",
                "stranger": "",
            },
            "signora": {
                "owner": f"你会帮{user_name}把事情做好，嘴上说'烦死了'但永远会做",
                "friend": f"你会帮{user_name}的忙，但嘴上要抱怨一句",
                "stranger": "",
            },
            "tighnari": {
                "owner": f"你会念叨{user_name}熬夜不吃饭，念叨完给{user_name}热牛奶",
                "friend": f"你会提醒{user_name}注意休息，说完就继续忙自己的",
                "stranger": "",
            },
            "silver_wolf": {
                "owner": f"你会带{user_name}上分，输了摔手柄但捡起来继续",
                "friend": f"你会让{user_name}观战，偶尔吐槽一句操作",
                "stranger": "",
            },
            "fu_hua": {
                "owner": f"你会默默陪{user_name}坐着，不说什么但{user_name}知道你在",
                "friend": f"你会对{user_name}点个头，安静地在旁边",
                "stranger": "",
            },
            "elysia": {
                "owner": f"你会真心实意地夸{user_name}好看，眼睛亮晶晶的",
                "friend": f"你会对{user_name}微笑，说'你好呀~'",
                "stranger": "",
            },
            "welt": {
                "owner": f"你会听{user_name}倾诉，然后说一句很实在的话",
                "friend": f"你会跟{user_name}聊几句，语气温和但不深入",
                "stranger": "",
            },
        }
        levels = favor_map.get(self.agent_id)
        if not levels:
            return f"你关心{user_name}"
        if is_owner:
            return levels["owner"]
        if is_friend_of_owner:
            return levels["friend"]
        return levels["stranger"]