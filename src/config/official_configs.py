from typing import Literal, Optional

import re

from .config_base import ConfigBase, Field

"""
须知：
1. 本文件中记录了所有的配置项
2. 所有新增的class都需要继承自ConfigBase
3. 所有新增的class都应在official_configs.py中的Config类中添加字段
4. 对于新增的字段，若为可选项，则应在其后添加Field()并设置default_factory或default
5. 所有的配置项都应该按照如下方法添加字段说明：
class ExampleConfig(ConfigBase):
    example_field: str
    \"""This is an example field\"""
    - 注释前面增加_warp_标记可以实现配置文件中注释在配置项前面单独一行显示
"""
class BotConfig(ConfigBase):
    """机器人配置类"""

    __ui_label__ = "基本信息"
    __ui_icon__ = "bot"

    platform: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "wifi",
        },
    )
    """平台"""

    qq_account: int = Field(
        default=0,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "user",
        },
    )
    """QQ账号"""

    platforms: list[str] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "layers",
        },
    )
    """其他平台"""

    nickname: str = Field(
        default="麦麦",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "user-circle",
        },
    )
    """机器人昵称"""

    alias_names: list[str] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "tags",
        },
    )
    """别名列表"""


class PersonalityConfig(ConfigBase):
    """人格配置类"""

    __ui_label__ = "人格"
    __ui_icon__ = "user-circle"

    personality: str = Field(
        default="是一个大二在读女大学生，现在正在上网和群友聊天，有时有点攻击性，有时比较温柔",
        json_schema_extra={
            "x-widget": "textarea",
            "x-icon": "user-circle",
        },
    )
    """人格，建议100字以内，描述人格特质和身份特征"""

    reply_style: str = Field(
        default="请不要刻意突出自身学科背景。可以参考贴吧，知乎和微博的回复风格。",
        json_schema_extra={
            "x-widget": "textarea",
            "x-icon": "message-square",
        },
    )
    """默认表达风格，描述麦麦说话的表达风格，表达习惯，如要修改，可以酌情新增内容，建议1-2行"""

    multiple_reply_style: list[str] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "list",
        },
    )
    """可选的多种表达风格列表，当配置不为空时可按概率随机替换 reply_style"""

    multiple_probability: float = Field(
        default=0.3,
        ge=0,
        le=1,
        json_schema_extra={
            "x-widget": "slider",
            "x-icon": "percent",
            "step": 0.1,
        },
    )
    """每次构建回复时，从 multiple_reply_style 中随机替换 reply_style 的概率（0.0-1.0）"""

    states: list[str] = Field(
        default_factory=lambda: [
            "是一个女大学生，喜欢上网聊天，会刷小红书。",
            "是一个大二心理学生，会刷贴吧和中国知网。",
            "是一个赛博网友，最近很想吐槽人。",
        ],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "shuffle",
        },
    )
    """_wrap_状态列表，用于随机替换personality"""

    state_probability: float = Field(
        default=0.3,
        ge=0,
        le=1,
        json_schema_extra={
            "x-widget": "slider",
            "x-icon": "percent",
            "step": 0.1,
        },
    )
    """状态概率，每次构建人格时替换personality的概率"""


class VisualConfig(ConfigBase):
    """视觉配置类"""

    __ui_label__ = "视觉"
    __ui_icon__ = "image"

    multimodal_planner: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "image",
        },
    )
    """是否直接输入图片"""

    multimodal_replyer: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "git-branch",
        },
    )
    """是否启用 Maisaka 多模态 replyer 生成器"""

    visual_style: str = Field(
        default="请用中文描述这张图片的内容。如果有文字，请把文字描述概括出来，请留意其主题，直观感受，输出为一段平文本，最多30字，请注意不要分点，就输出一段文本",
        json_schema_extra={
            "x-widget": "textarea",
            "x-icon": "image",
        },
    )
    """_wrap_识图提示词，不建议修改"""


class RelationshipConfig(ConfigBase):
    """关系配置类"""

    __ui_parent__ = "debug"

    enable_relationship: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "heart",
        },
    )
    """是否启用关系系统，关系系统被移除，此部分配置暂时无效"""


class TalkRulesItem(ConfigBase):
    platform: str = ""
    """平台，与ID一起留空表示全局"""

    item_id: str = ""
    """用户ID，与平台一起留空表示全局"""

    rule_type: Literal["group", "private"] = "group"
    """聊天流类型，group（群聊）或private（私聊）"""

    time: str = ""
    """时间段，格式为 "HH:MM-HH:MM"，支持跨夜区间"""

    value: float = 0.5
    """聊天频率值，范围0-1"""


class ChatConfig(ConfigBase):
    """聊天配置类"""

    __ui_label__ = "聊天"
    __ui_icon__ = "message-square"

    talk_value: float = Field(
        default=1,
        ge=0,
        le=1,
        json_schema_extra={
            "x-widget": "slider",
            "x-icon": "message-circle",
            "step": 0.1,
        },
    )
    """聊天频率，越小越沉默，范围0-1"""

    mentioned_bot_reply: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "at-sign",
        },
    )
    """是否启用提及必回复"""

    inevitable_at_reply: bool = Field(default=True)
    """是否启用at必回复"""

    max_context_size: int = Field(
        default=30,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "layers",
        },
    )
    """上下文长度"""

    plan_reply_log_max_per_chat: int = Field(
        default=1024,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "file-text",
        },
    )
    """每个聊天流最大保存的Plan/Reply日志数量，超过此数量时会自动删除最老的日志"""
    group_chat_prompt: str = Field(
        default="你需要控制自己发言的频率，如果是一对一聊天，可以以较均匀的频率发言；如果用户较多，不要每句都回复，控制回复频率，不要回复的太频繁！控制回复的频率，不要每个人的消息都回复。",
        json_schema_extra={
            "x-widget": "textarea",
            "x-icon": "users",
        },
    )
    """_wrap_群聊通用注意事项"""

    private_chat_prompts: str = Field(
        default="你需要控制自己发言的频率，可以以较均匀的频率发言。",
        json_schema_extra={
            "x-widget": "textarea",
            "x-icon": "user",
        },
    )
    """_wrap_私聊通用注意事项"""

    chat_prompts: list["ExtraPromptItem"] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "list",
        },
    )

    enable_talk_value_rules: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "settings",
        },
    )
    """是否启用动态发言频率规则"""

    talk_value_rules: list[TalkRulesItem] = Field(
        default_factory=lambda: [
            TalkRulesItem(platform="", item_id="", rule_type="group", time="00:00-08:59", value=0.8),
            TalkRulesItem(platform="", item_id="", rule_type="group", time="09:00-18:59", value=1.0),
        ],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "list",
        },
    )
    """
    _wrap_思考频率规则列表，支持按聊天流/按日内时段配置。
    """


class MessageReceiveConfig(ConfigBase):
    """消息接收配置类"""

    __ui_parent__ = "response_post_process"

    image_parse_threshold: int = Field(
        default=5,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "image",
        },
    )
    """
    当消息中图片数量不超过此阈值时，启用图片解析功能，将图片内容解析为文本后再进行处理。
    当消息中图片数量超过此阈值时，为了避免过度解析导致的性能问题，将跳过图片解析，直接进行处理。
    """

    ban_words: set[str] = Field(
        default_factory=lambda: set(),
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "ban",
        },
    )
    """过滤词列表"""

    ban_msgs_regex: set[str] = Field(
        default_factory=lambda: set(),
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "regex",
        },
    )
    """过滤正则表达式列表"""

    def model_post_init(self, context: Optional[dict] = None) -> None:
        for pattern in self.ban_msgs_regex:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern in ban_msgs_regex: '{pattern}'") from e
        return super().model_post_init(context)


class TargetItem(ConfigBase):
    platform: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "wifi",
        },
    )
    """平台，与ID一起留空表示全局"""

    item_id: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """用户/群ID，与平台一起留空表示全局"""

    rule_type: Literal["group", "private"] = Field(
        default="group",
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "users",
        },
    )
    """聊天流类型，group（群聊）或private（私聊）"""


class MemoryConfig(ConfigBase):
    """记忆配置类"""

    __ui_parent__ = "emoji"


    global_memory: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "globe",
        },
    )
    """是否允许记忆检索在聊天记录中进行全局查询（忽略当前chat_id，仅对 search_chat_history 等工具生效）"""

    global_memory_blacklist: list[TargetItem] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "shield-off",
        },
    )
    """_wrap_全局记忆黑名单，当启用全局记忆时，不将特定聊天流纳入检索"""

    enable_memory_query_tool: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "database",
        },
    )
    """是否启用 Maisaka 内置长期记忆检索工具 query_memory"""

    memory_query_default_limit: int = Field(
        default=5,
        ge=1,
        le=20,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """Maisaka 内置长期记忆检索工具 query_memory 的默认返回条数"""

    long_term_auto_summary_enabled: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "book-open",
        },
    )
    """是否自动启动聊天总结并导入长期记忆"""

    person_fact_writeback_enabled: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "user-round-pen",
        },
    )
    """是否在发送回复后自动提取并写回人物事实到长期记忆"""
    chat_history_topic_check_message_threshold: int = Field(
        default=80,
        ge=1,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """聊天历史话题检查的消息数量阈值，当累积消息数达到此值时触发话题检查"""

    chat_history_topic_check_time_hours: float = Field(
        default=8.0,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "clock",
        },
    )
    """聊天历史话题检查的时间阈值（小时），当距离上次检查超过此时间且消息数达到最小阈值时触发话题检查"""

    chat_history_topic_check_min_messages: int = Field(
        default=20,
        ge=1,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """聊天历史话题检查的时间触发模式下的最小消息数阈值"""

    chat_history_finalize_no_update_checks: int = Field(
        default=3,
        ge=1,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "check-circle",
        },
    )
    """聊天历史话题打包存储的连续无更新检查次数阈值，当话题连续N次检查无新增内容时触发打包存储"""

    chat_history_finalize_message_count: int = Field(
        default=5,
        ge=1,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "package",
        },
    )
    """聊天历史话题打包存储的消息条数阈值，当话题的消息条数超过此值时触发打包存储"""

    def model_post_init(self, context: Optional[dict] = None) -> None:
        """验证配置值"""
        if self.chat_history_topic_check_message_threshold < 1:
            raise ValueError(
                f"chat_history_topic_check_message_threshold 必须至少为1，当前值: {self.chat_history_topic_check_message_threshold}"
            )
        if self.chat_history_topic_check_time_hours <= 0:
            raise ValueError(
                f"chat_history_topic_check_time_hours 必须大于0，当前值: {self.chat_history_topic_check_time_hours}"
            )
        if self.chat_history_topic_check_min_messages < 1:
            raise ValueError(
                f"chat_history_topic_check_min_messages 必须至少为1，当前值: {self.chat_history_topic_check_min_messages}"
            )
        if self.chat_history_finalize_no_update_checks < 1:
            raise ValueError(
                f"chat_history_finalize_no_update_checks 必须至少为1，当前值: {self.chat_history_finalize_no_update_checks}"
            )
        if self.chat_history_finalize_message_count < 1:
            raise ValueError(
                f"chat_history_finalize_message_count 必须至少为1，当前值: {self.chat_history_finalize_message_count}"
            )
        return super().model_post_init(context)


class LearningItem(ConfigBase):
    platform: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "wifi",
        },
    )
    """平台，与ID一起留空表示全局"""

    item_id: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """用户ID，与平台一起留空表示全局"""

    rule_type: Literal["group", "private"] = Field(
        default="group",
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "users",
        },
    )
    """聊天流类型，group（群聊）或private（私聊）"""

    use_expression: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "message-square",
        },
    )
    """是否启用表达学习"""

    enable_learning: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "graduation-cap",
        },
    )
    """是否启用表达优化学习"""

    enable_jargon_learning: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "book",
        },
    )
    """是否启用jargon学习"""


class ExpressionGroup(ConfigBase):
    """表达互通组配置类，若列表为空代表全局共享"""

    expression_groups: list[TargetItem] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "users",
        },
    )
    """_wrap_表达学习互通组"""


class ExpressionConfig(ConfigBase):
    """表达配置类"""

    __ui_label__ = "表达"
    __ui_icon__ = "pen-tool"

    learning_list: list[LearningItem] = Field(
        default_factory=lambda: [
            LearningItem(
                platform="",
                item_id="",
                rule_type="group",
                use_expression=True,
                enable_learning=True,
                enable_jargon_learning=True,
            )
        ],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "list",
        },
    )
    """_wrap_表达学习配置列表，支持按聊天流配置"""

    expression_groups: list[ExpressionGroup] = Field(
        default_factory=list,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "users",
        },
    )
    """_wrap_表达学习互通组"""

    expression_checked_only: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "check",
        },
    )
    """是否仅选择已检查且未拒绝的表达方式"""

    expression_self_reflect: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "refresh-cw",
        },
    )
    """是否启用自动表达优化"""

    expression_auto_check_interval: int = Field(
        default=600,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "clock",
        },
    )
    """表达方式自动检查的间隔时间（秒）"""

    expression_auto_check_count: int = Field(
        default=20,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """每次自动检查时随机选取的表达方式数量"""

    expression_auto_check_custom_criteria: list[str] = Field(
        default_factory=list,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "file-text",
        },
    )
    """表达方式自动检查的额外自定义评估标准"""

    all_global_jargon: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "globe",
        },
    )
    """是否开启全局黑话模式，注意，此功能关闭后，已经记录的全局黑话不会改变，需要手动删除"""

class VoiceConfig(ConfigBase):
    """语音识别配置类"""

    __ui_parent__ = "emoji"

    enable_asr: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "mic",
        },
    )
    """是否启用语音识别，启用后麦麦可以识别语音消息"""


class EmojiConfig(ConfigBase):
    """表情包配置类"""

    __ui_label__ = "功能"
    __ui_icon__ = "puzzle"

    emoji_send_num: int = Field(
        default=25,
        ge=1,
        le=64,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "grid",
        },
    )
    """一次从多少个表情包中选择发送，最大为 64"""

    max_reg_num: int = Field(
        default=64,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """表情包最大注册数量"""

    do_replace: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "refresh-cw",
        },
    )
    """达到最大注册数量时替换旧表情包，关闭则达到最大数量时不会继续收集表情包"""

    check_interval: int = Field(
        default=10,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "clock",
        },
    )
    """表情包检查间隔（分钟）"""

    steal_emoji: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "copy",
        },
    )
    """是否偷取表情包，让麦麦可以将一些表情包据为己有"""

    content_filtration: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "filter",
        },
    )
    """是否启用表情包过滤，只有符合该要求的表情包才会被保存"""

    filtration_prompt: str = Field(
        default="符合公序良俗",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "shield",
        },
    )
    """表情包过滤要求，只有符合该要求的表情包才会被保存"""


class KeywordRuleConfig(ConfigBase):
    """关键词规则配置类"""

    keywords: list[str] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "tag",
        },
    )
    """关键词列表"""

    regex: list[str] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "regex",
        },
    )
    """正则表达式列表"""

    reaction: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "textarea",
            "x-icon": "message-circle",
        },
    )
    """关键词触发的反应"""

    def model_post_init(self, context: Optional[dict] = None) -> None:
        """验证配置"""
        if not self.keywords and not self.regex:
            raise ValueError("关键词规则必须至少包含keywords或regex中的一个")

        if not self.reaction:
            raise ValueError("关键词规则必须包含reaction")

        for pattern in self.regex:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"无效的正则表达式 '{pattern}': {str(e)}") from e
        return super().model_post_init(context)


class KeywordReactionConfig(ConfigBase):
    """关键词配置类"""

    __ui_parent__ = "response_post_process"

    keyword_rules: list[KeywordRuleConfig] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "list",
        },
    )
    """关键词规则列表"""

    regex_rules: list[KeywordRuleConfig] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "list",
        },
    )
    """正则表达式规则列表"""

    def model_post_init(self, context: Optional[dict] = None) -> None:
        """验证配置"""
        for rule in self.keyword_rules + self.regex_rules:
            if not isinstance(rule, KeywordRuleConfig):
                raise ValueError(f"规则必须是KeywordRuleConfig类型，而不是{type(rule).__name__}")
        return super().model_post_init(context)


class ResponsePostProcessConfig(ConfigBase):
    """回复后处理配置类"""

    __ui_label__ = "处理"
    __ui_icon__ = "settings"

    enable_response_post_process: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "settings",
        },
    )
    """是否启用回复后处理，包括错别字生成器，回复分割器"""


class ChineseTypoConfig(ConfigBase):
    """中文错别字配置类"""

    __ui_parent__ = "response_post_process"

    enable: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "type",
        },
    )
    """是否启用中文错别字生成器"""

    error_rate: float = Field(
        default=0.01,
        ge=0,
        le=1,
        json_schema_extra={
            "x-widget": "slider",
            "x-icon": "percent",
            "step": 0.01,
        },
    )
    """单字替换概率"""

    min_freq: int = Field(
        default=9,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """最小字频阈值"""

    tone_error_rate: float = Field(
        default=0.1,
        ge=0,
        le=1,
        json_schema_extra={
            "x-widget": "slider",
            "x-icon": "percent",
            "step": 0.1,
        },
    )
    """声调错误概率"""

    word_replace_rate: float = Field(
        default=0.006,
        ge=0,
        le=1,
        json_schema_extra={
            "x-widget": "slider",
            "x-icon": "percent",
            "step": 0.001,
        },
    )
    """整词替换概率"""


class ResponseSplitterConfig(ConfigBase):
    """回复分割器配置类"""

    __ui_parent__ = "response_post_process"

    enable: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "scissors",
        },
    )
    """是否启用回复分割器"""

    max_length: int = Field(
        default=512,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "ruler",
        },
    )
    """回复允许的最大长度"""

    max_sentence_num: int = Field(
        default=8,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """回复允许的最大句子数"""

    enable_kaomoji_protection: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "smile",
        },
    )
    """是否启用颜文字保护"""

    enable_overflow_return_all: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "maximize",
        },
    )
    """是否在句子数量超出回复允许的最大句子数时一次性返回全部内容"""


class TelemetryConfig(ConfigBase):
    """遥测配置类"""

    __ui_parent__ = "debug"

    enable: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "activity",
        },
    )
    """是否启用遥测"""


class DebugConfig(ConfigBase):
    """调试配置类"""

    __ui_label__ = "其他"
    __ui_icon__ = "more-horizontal"

    show_prompt: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "eye",
        },
    )
    """是否显示prompt"""

    show_maisaka_thinking: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "brain",
        },
    )
    """是否显示回复器推理"""

    fold_maisaka_thinking: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "minimize-2",
        },
    )
    """是否折叠 Maisaka 的 prompt 展示入口"""

    show_jargon_prompt: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "book",
        },
    )
    """是否显示jargon相关提示词"""

    show_memory_prompt: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "database",
        },
    )
    """是否显示记忆检索相关prompt"""

class ExtraPromptItem(ConfigBase):
    platform: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "wifi",
        },
    )
    """平台，留空无效"""

    item_id: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """用户ID，留空无效"""

    rule_type: Literal["group", "private"] = Field(
        default="group",
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "users",
        },
    )
    """聊天流类型，group（群聊）或private（私聊）"""

    prompt: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "textarea",
            "x-icon": "file-text",
        },
    )
    """额外的prompt内容"""

    def model_post_init(self, context: Optional[dict] = None) -> None:
        if not self.platform and not self.item_id and not self.prompt:
            return super().model_post_init(context)
        if not self.platform or not self.item_id or not self.prompt:
            raise ValueError("ExtraPromptItem 中 platform, id 和 prompt 不能为空")
        return super().model_post_init(context)


class MaimMessageConfig(ConfigBase):
    """maim_message配置类"""

    __ui_parent__ = "debug"

    ws_server_host: str = Field(
        default="127.0.0.1",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "server",
        },
    )
    """旧版基于WS的服务器主机地址"""

    ws_server_port: int = Field(
        default=8080,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """旧版基于WS的服务器端口号"""

    auth_token: list[str] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "key",
        },
    )
    """认证令牌，用于旧版API验证，为空则不启用验证"""

    enable_api_server: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "server",
        },
    )
    """是否启用额外的新版API Server"""

    api_server_host: str = Field(
        default="0.0.0.0",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "globe",
        },
    )
    """新版API Server主机地址"""

    api_server_port: int = Field(
        default=8090,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """新版API Server端口号"""

    api_server_use_wss: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "lock",
        },
    )
    """新版API Server是否启用WSS"""

    api_server_cert_file: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "file",
        },
    )
    """新版API Server SSL证书文件路径"""

    api_server_key_file: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "key",
        },
    )
    """新版API Server SSL密钥文件路径"""

    api_server_allowed_api_keys: list[str] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "shield",
        },
    )
    """新版API Server允许的API Key列表，为空则允许所有连接"""


class LPMMKnowledgeConfig(ConfigBase):
    """LPMM知识库配置类"""

    __ui_label__ = "知识库"
    __ui_icon__ = "book-open"

    enable: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "database",
        },
    )
    """是否启用LPMM知识库"""

    lpmm_mode: Literal["classic", "agent"] = Field(
        default="classic",
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "brain",
        },
    )
    """LPMM知识库模式，可选：classic经典模式，agent 模式"""

    rag_synonym_search_top_k: int = Field(
        default=10,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """同义检索TopK"""

    rag_synonym_threshold: float = Field(
        default=0.8,
        ge=0,
        le=1,
        json_schema_extra={
            "x-widget": "slider",
            "x-icon": "percent",
            "step": 0.1,
        },
    )
    """同义阈值，相似度高于该值的关系会被当作同义词"""

    info_extraction_workers: int = Field(
        default=3,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "cpu",
        },
    )
    """实体抽取同时执行线程数，非Pro模型不要设置超过5"""

    qa_relation_search_top_k: int = Field(
        default=10,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """关系检索TopK"""

    qa_relation_threshold: float = Field(
        default=0.75,
        ge=0,
        le=1,
        json_schema_extra={
            "x-widget": "slider",
            "x-icon": "percent",
            "step": 0.05,
        },
    )
    """关系阈值，相似度高于该值的关系会被认为是相关关系"""

    qa_paragraph_search_top_k: int = Field(
        default=1000,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """段落检索TopK（不能过小，可能影响搜索结果）"""

    qa_paragraph_node_weight: float = Field(
        default=0.05,
        json_schema_extra={
            "x-widget": "slider",
            "x-icon": "weight",
            "step": 0.01,
        },
    )
    """段落节点权重（在图搜索&PPR计算中的权重，当搜索仅使用DPR时，此参数不起作用）"""

    qa_ent_filter_top_k: int = Field(
        default=10,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """实体过滤TopK"""

    qa_ppr_damping: float = Field(
        default=0.8,
        ge=0,
        le=1,
        json_schema_extra={
            "x-widget": "slider",
            "x-icon": "percent",
            "step": 0.1,
        },
    )
    """PPR阻尼系数"""

    qa_res_top_k: int = Field(
        default=10,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """最终提供段落TopK"""

    embedding_dimension: int = Field(
        default=1024,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """嵌入向量维度,输出维度"""

    max_embedding_workers: int = Field(
        default=3,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "cpu",
        },
    )
    """嵌入/抽取并发线程数"""

    embedding_chunk_size: int = Field(
        default=4,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """每批嵌入的条数"""

    max_synonym_entities: int = Field(
        default=2000,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """同义边参与的实体数上限，超限则跳过"""

    enable_ppr: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "zap",
        },
    )
    """是否启用PPR，低配机器可关闭"""


class WebUIConfig(ConfigBase):
    """WebUI配置类"""

    __ui_label__ = "WebUI"
    __ui_icon__ = "layout"

    enabled: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "monitor",
        },
    )
    """是否启用WebUI"""

    host: str = Field(
        default="127.0.0.1",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "globe",
        },
    )
    """WebUI 绑定主机地址"""

    port: int = Field(
        default=8001,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hash",
        },
    )
    """WebUI 绑定端口"""

    mode: Literal["development", "production"] = Field(
        default="production",
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "settings",
        },
    )
    """运行模式：development(开发) 或 production(生产)"""

    anti_crawler_mode: Literal["false", "strict", "loose", "basic"] = Field(
        default="basic",
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "shield",
        },
    )
    """防爬虫模式：false(禁用) / strict(严格) / loose(宽松) / basic(基础-只记录不阻止)"""

    allowed_ips: str = Field(
        default="127.0.0.1",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "network",
        },
    )
    """IP白名单（逗号分隔，支持精确IP、CIDR格式和通配符）"""

    trusted_proxies: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "server",
        },
    )
    """信任的代理IP列表（逗号分隔），只有来自这些IP的X-Forwarded-For才被信任"""

    trust_xff: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "shield-check",
        },
    )
    """是否启用X-Forwarded-For代理解析（默认false）"""

    secure_cookie: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "cookie",
        },
    )
    """是否启用安全Cookie（仅通过HTTPS传输，默认false）"""

    enable_paragraph_content: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "file-text",
        },
    )
    """是否在知识图谱中加载段落完整内容（需要加载embedding store，会占用额外内存）"""


class DatabaseConfig(ConfigBase):
    """数据库配置类"""

    __ui_parent__ = "debug"

    save_binary_data: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "save",
        },
    )
    """
    是否将消息中的二进制数据保存为独立文件
    若启用，消息中的语音等二进制数据将会保存为独立文件，并在消息中以特殊标记替代。启用会导致数据文件夹体积增大，但可以实现二次识别等功能。
    若禁用，则消息中的二进制将会在识别后删除，并在消息中使用识别结果替代，无法二次识别
    该配置项仅影响新存储的消息，已有消息不会受到影响
    """


class MaiSakaConfig(ConfigBase):
    """MaiSaka 对话系统配置类"""

    __ui_label__ = "MaiSaka"
    __ui_icon__ = "message-circle"

    enable_knowledge_module: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "book",
        },
    )
    """启用知识库模块"""
    cli_user_name: str = Field(
        default="用户",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "user",
        },
    )
    """MaiSaka 使用的用户名称"""

    planner_interrupt_max_consecutive_count: int = Field(
        default=2,
        ge=0,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "pause-circle",
        },
    )
    """Planner 连续被新消息打断的最大次数，0 表示不启用打断"""

    tool_filter_task_name: str = Field(
        default="utils",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "sparkles",
        },
    )
    """工具筛选预判使用的模型任务名"""

    tool_filter_threshold: int = Field(
        default=20,
        ge=1,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "filter",
        },
    )
    """当可用工具总数超过该阈值时，先进行一轮工具筛选"""

    tool_filter_max_keep: int = Field(
        default=5,
        ge=1,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "list-filter",
        },
    )
    """工具筛选阶段最多保留的非内置工具数量"""

    show_image_path: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "image",
        },
    )
    """是否显示图片本地路径"""


class MCPAuthorizationConfig(ConfigBase):
    """MCP HTTP 认证配置。"""

    mode: Literal["none", "bearer"] = Field(
        default="none",
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "shield",
        },
    )
    """认证模式，当前支持无认证和静态 Bearer Token"""

    bearer_token: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "password",
            "x-icon": "key",
        },
    )
    """静态 Bearer Token，仅在 `mode=\"bearer\"` 时使用"""

    def model_post_init(self, context: Optional[dict] = None) -> None:
        """验证 MCP 认证配置。

        Args:
            context: Pydantic 传入的上下文对象。

        Returns:
            None
        """

        if self.mode == "bearer" and not self.bearer_token.strip():
            raise ValueError("MCP 使用 bearer 认证时必须填写 bearer_token")
        return super().model_post_init(context)


class MCPRootItemConfig(ConfigBase):
    """单个 MCP Root 配置。"""

    enabled: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "power",
        },
    )
    """是否启用当前 Root"""

    uri: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "folder",
        },
    )
    """Root URI，通常为 `file://` 路径 URI"""

    name: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "tag",
        },
    )
    """Root 的显示名称"""

    def model_post_init(self, context: Optional[dict] = None) -> None:
        """验证单个 Root 配置。

        Args:
            context: Pydantic 传入的上下文对象。

        Returns:
            None
        """

        if self.enabled and not self.uri.strip():
            raise ValueError("启用的 MCP Root 必须填写 uri")
        return super().model_post_init(context)


class MCPRootsConfig(ConfigBase):
    """MCP Roots 能力配置。"""

    enable: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "folder-tree",
        },
    )
    """是否向 MCP 服务器暴露 Roots 能力"""

    items: list[MCPRootItemConfig] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "folder",
        },
    )
    """Roots 列表"""


class MCPSamplingConfig(ConfigBase):
    """MCP Sampling 能力配置。"""

    enable: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "brain",
        },
    )
    """是否启用 Sampling 能力声明"""

    task_name: str = Field(
        default="planner",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "sparkles",
        },
    )
    """执行 Sampling 请求时使用的主程序模型任务名"""

    include_context_support: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "layers",
        },
    )
    """是否声明支持 `includeContext` 非 `none` 语义"""

    tool_support: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "wrench",
        },
    )
    """是否声明支持在 Sampling 中继续使用工具"""


class MCPElicitationConfig(ConfigBase):
    """MCP Elicitation 能力配置。"""

    enable: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "message-circle-question",
        },
    )
    """是否启用 Elicitation 能力声明"""

    allow_form: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "form-input",
        },
    )
    """是否允许表单模式 Elicitation"""

    allow_url: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "link",
        },
    )
    """是否允许 URL 模式 Elicitation"""

    def model_post_init(self, context: Optional[dict] = None) -> None:
        """验证 Elicitation 配置。

        Args:
            context: Pydantic 传入的上下文对象。

        Returns:
            None
        """

        if self.enable and not (self.allow_form or self.allow_url):
            raise ValueError("启用 MCP Elicitation 时至少需要允许一种模式")
        return super().model_post_init(context)


class MCPClientConfig(ConfigBase):
    """MCP 客户端宿主能力配置。"""

    client_name: str = Field(
        default="MaiBot",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "bot",
        },
    )
    """MCP 客户端实现名称"""

    client_version: str = Field(
        default="1.0.0",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "info",
        },
    )
    """MCP 客户端实现版本"""

    roots: MCPRootsConfig = Field(default_factory=MCPRootsConfig)
    """Roots 能力配置"""

    sampling: MCPSamplingConfig = Field(default_factory=MCPSamplingConfig)
    """Sampling 能力配置"""

    elicitation: MCPElicitationConfig = Field(default_factory=MCPElicitationConfig)
    """Elicitation 能力配置"""


class MCPServerItemConfig(ConfigBase):
    """单个 MCP 服务器配置。"""

    name: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "tag",
        },
    )
    """服务器名称，必须唯一"""

    enabled: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "power",
        },
    )
    """是否启用当前 MCP 服务器"""

    transport: Literal["stdio", "streamable_http"] = Field(
        default="stdio",
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "shuffle",
        },
    )
    """传输方式，可选 `stdio` 或 `streamable_http`"""

    command: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "terminal",
        },
    )
    """stdio 模式下启动服务器的命令"""

    args: list[str] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "list",
        },
    )
    """stdio 模式下的命令参数列表"""

    env: dict[str, str] = Field(
        default_factory=lambda: {},
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "variable",
        },
    )
    """stdio 模式下附加的环境变量"""

    url: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "link",
        },
    )
    """`streamable_http` 模式下的 MCP 端点地址"""

    headers: dict[str, str] = Field(
        default_factory=lambda: {},
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "file-json",
        },
    )
    """HTTP 模式下附加的请求头"""

    http_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        json_schema_extra={
            "x-widget": "number",
            "x-icon": "clock-3",
        },
    )
    """HTTP 请求超时时间，单位秒"""

    read_timeout_seconds: float = Field(
        default=300.0,
        gt=0,
        json_schema_extra={
            "x-widget": "number",
            "x-icon": "timer",
        },
    )
    """会话读取超时时间，单位秒"""

    authorization: MCPAuthorizationConfig = Field(default_factory=MCPAuthorizationConfig)
    """HTTP 认证配置"""

    def model_post_init(self, context: Optional[dict] = None) -> None:
        """验证 MCP 服务器配置。

        Args:
            context: Pydantic 传入的上下文对象。

        Returns:
            None
        """

        if not self.name.strip():
            raise ValueError("MCPServerItemConfig.name 不能为空")

        if self.transport == "stdio" and not self.command.strip():
            raise ValueError(f"MCP 服务器 {self.name} 使用 stdio 时必须填写 command")

        if self.transport == "streamable_http" and not self.url.strip():
            raise ValueError(f"MCP 服务器 {self.name} 使用 streamable_http 时必须填写 url")

        return super().model_post_init(context)


class MCPConfig(ConfigBase):
    """MCP 总配置。"""

    __ui_parent__ = "maisaka"

    enable: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "zap",
        },
    )
    """是否启用 MCP（Model Context Protocol）"""

    client: MCPClientConfig = Field(default_factory=MCPClientConfig)
    """MCP 客户端宿主能力配置"""

    servers: list[MCPServerItemConfig] = Field(
        default_factory=lambda: [],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "server",
        },
    )
    """_wrap_MCP 服务器配置列表"""

    def model_post_init(self, context: Optional[dict] = None) -> None:
        """验证 MCP 总配置。

        Args:
            context: Pydantic 传入的上下文对象。

        Returns:
            None
        """

        server_names = [server.name.strip() for server in self.servers if server.name.strip()]
        if len(server_names) != len(set(server_names)):
            raise ValueError("MCP 配置中的服务器名称不能重复")
        return super().model_post_init(context)


class PluginRuntimeRenderConfig(ConfigBase):
    """插件运行时浏览器渲染配置。"""

    enabled: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "image",
        },
    )
    """是否启用插件运行时浏览器渲染能力"""

    browser_ws_endpoint: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "link",
        },
    )
    """优先复用的现有 Chromium CDP 地址，可填写 ws/http 端点"""

    executable_path: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "folder",
        },
    )
    """浏览器可执行文件路径，留空时自动探测本机 Chrome/Chromium"""

    browser_install_root: str = Field(
        default="data/playwright-browsers",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "hard-drive",
        },
    )
    """Playwright 托管浏览器目录，自动下载 Chromium 时会复用该目录"""

    headless: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "monitor",
        },
    )
    """是否以无头模式启动浏览器"""

    launch_args: list[str] = Field(
        default_factory=lambda: [
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--no-sandbox",
            "--no-zygote",
        ],
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "terminal",
        },
    )
    """浏览器启动参数列表"""

    concurrency_limit: int = Field(
        default=2,
        ge=1,
        json_schema_extra={
            "x-widget": "number",
            "x-icon": "layers",
        },
    )
    """同时允许进行的最大渲染任务数"""

    startup_timeout_sec: float = Field(
        default=20.0,
        gt=0,
        json_schema_extra={
            "x-widget": "number",
            "x-icon": "clock",
        },
    )
    """浏览器连接或启动超时时间（秒）"""

    render_timeout_sec: float = Field(
        default=15.0,
        gt=0,
        json_schema_extra={
            "x-widget": "number",
            "x-icon": "timer",
        },
    )
    """单次渲染默认超时时间（秒）"""

    auto_download_chromium: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "download",
        },
    )
    """未检测到可用浏览器时，是否自动下载 Playwright Chromium"""

    download_connection_timeout_sec: float = Field(
        default=120.0,
        gt=0,
        json_schema_extra={
            "x-widget": "number",
            "x-icon": "cloud-lightning",
        },
    )
    """自动下载 Chromium 时的连接超时时间（秒）"""

    restart_after_render_count: int = Field(
        default=200,
        ge=0,
        json_schema_extra={
            "x-widget": "number",
            "x-icon": "refresh-cw",
        },
    )
    """累计渲染指定次数后自动重建本地浏览器，0 表示关闭该策略"""


class PluginRuntimeConfig(ConfigBase):
    """插件运行时配置类"""

    __ui_label__ = "插件运行时"
    __ui_icon__ = "puzzle"

    enabled: bool = Field(
        default=True,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "power",
        },
    )
    """启用插件系统"""

    health_check_interval_sec: float = Field(
        default=30.0,
        json_schema_extra={
            "x-widget": "number",
            "x-icon": "activity",
        },
    )
    """健康检查间隔（秒）"""

    max_restart_attempts: int = Field(
        default=3,
        json_schema_extra={
            "x-widget": "number",
            "x-icon": "refresh-cw",
        },
    )
    """Runner 崩溃后最大自动重启次数"""

    runner_spawn_timeout_sec: float = Field(
        default=30.0,
        json_schema_extra={
            "x-widget": "number",
            "x-icon": "clock",
        },
    )
    """等待 Runner 子进程启动并注册的超时时间（秒）"""

    hook_blocking_timeout_sec: float = Field(
        default=30,
        json_schema_extra={
            "x-widget": "number",
            "x-icon": "timer",
        },
    )
    """Hook 阻塞步骤的全局超时上限（秒）"""

    ipc_socket_path: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "link",
        },
    )
    """
    自定义 IPC Socket 路径（仅 Linux/macOS 生效）
    留空则自动生成临时路径
    """

    render: PluginRuntimeRenderConfig = Field(default_factory=PluginRuntimeRenderConfig)
    """浏览器渲染能力配置"""
