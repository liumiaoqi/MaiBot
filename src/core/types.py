from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any, Dict, List, Protocol, TypedDict

import copy
import time
import warnings

from datetime import datetime

from maim_message import Seg

from src.llm_models.payload_content.tool_option import ToolCall

# from src.common.data_models.message_data_model import ReplyContentType as ReplyContentType
# from src.common.data_models.message_data_model import ReplyContent as ReplyContent
# from src.common.data_models.message_data_model import ForwardNode as ForwardNode
# from src.common.data_models.message_data_model import ReplySetModel as ReplySetModel


# 组件类型枚举
class ComponentType(Enum):
    """Host 内部使用的组件类型枚举。"""

    ACTION = "action"  # 动作组件
    COMMAND = "command"  # 命令组件
    TOOL = "tool"  # 工具组件

    def __str__(self) -> str:
        """返回枚举值字符串。

        Returns:
            str: 当前组件类型对应的字符串值。
        """
        return self.value


# 动作激活类型枚举
class ActionActivationType(Enum):
    """动作激活类型枚举。"""

    NEVER = "never"  # 从不激活（默认关闭）
    ALWAYS = "always"  # 默认参与到planner
    RANDOM = "random"  # 随机启用action到planner
    KEYWORD = "keyword"  # 关键词触发启用action到planner

    def __str__(self) -> str:
        """返回枚举值字符串。

        Returns:
            str: 当前激活类型对应的字符串值。
        """
        return self.value


# 事件类型枚举
class EventType(Enum):
    """事件类型枚举。"""

    ON_START = "on_start"  # 启动事件，用于调用按时任务
    ON_STOP = "on_stop"  # 停止事件，用于调用按时任务
    ON_MESSAGE_PRE_PROCESS = "on_message_pre_process"
    ON_MESSAGE = "on_message"
    ON_PLAN = "on_plan"
    POST_LLM = "post_llm"
    AFTER_LLM = "after_llm"
    POST_SEND_PRE_PROCESS = "post_send_pre_process"
    POST_SEND = "post_send"
    AFTER_SEND = "after_send"
    UNKNOWN = "unknown"  # 未知事件类型

    def __str__(self) -> str:
        """返回枚举值字符串。

        Returns:
            str: 当前事件类型对应的字符串值。
        """
        return self.value


@dataclass(slots=True)
class ComponentInfo:
    """Host 内部使用的组件信息快照。"""

    name: str
    """组件名称。"""

    description: str = ""
    """组件描述。"""

    enabled: bool = True
    """组件是否启用。"""

    plugin_name: str = ""
    """所属插件 ID。"""

    component_type: ComponentType = field(init=False)
    """组件类型。"""


@dataclass(slots=True)
class ActionInfo(ComponentInfo):
    """供 Planner 与回复链使用的动作信息快照。"""

    action_parameters: Dict[str, str] = field(
        default_factory=dict
    )  # 动作参数与描述，例如 {"param1": "描述1", "param2": "描述2"}
    action_require: List[str] = field(default_factory=list)  # 动作需求说明
    associated_types: List[str] = field(default_factory=list)  # 关联的消息类型
    activation_type: ActionActivationType = ActionActivationType.ALWAYS
    random_activation_probability: float = 0.0
    activation_keywords: List[str] = field(default_factory=list)  # 激活关键词列表
    keyword_case_sensitive: bool = False
    parallel_action: bool = False
    component_type: ComponentType = field(init=False, default=ComponentType.ACTION)
    """组件类型。"""

    def __post_init__(self) -> None:
        """归一化动作快照中的集合字段。"""
        self.action_parameters = dict(self.action_parameters or {})
        self.action_require = list(self.action_require or [])
        self.associated_types = list(self.associated_types or [])
        self.activation_keywords = list(self.activation_keywords or [])


@dataclass(slots=True)
class CommandInfo(ComponentInfo):
    """供命令处理链使用的命令信息快照。"""

    component_type: ComponentType = field(init=False, default=ComponentType.COMMAND)
    """组件类型。"""


@dataclass(slots=True)
class ToolInfo(ComponentInfo):
    """供工具执行链使用的工具信息快照。"""

    parameters_schema: Dict[str, Any] | None = None
    """对象级工具参数 Schema。"""

    component_type: ComponentType = field(init=False, default=ComponentType.TOOL)
    """组件类型。"""

    def get_llm_definition(self) -> Dict[str, Any]:
        """生成供 LLM 使用的规范化工具定义。

        Returns:
            Dict[str, Any]: 统一工具定义字典。
        """
        definition: Dict[str, Any] = {
            "name": self.name,
            "description": self.description,
        }
        if self.parameters_schema is not None:
            definition["parameters_schema"] = copy.deepcopy(self.parameters_schema)
        return definition


@dataclass(slots=True)
class ModifyFlag:
    """消息修改标记集合。"""

    modify_message_segments: bool = False
    modify_plain_text: bool = False
    modify_llm_prompt: bool = False
    modify_llm_response_content: bool = False
    modify_llm_response_reasoning: bool = False


@dataclass(slots=True)
class MaiMessages:
    """核心事件系统使用的统一消息模型。"""

    message_segments: List[Seg] = field(default_factory=list)
    """消息段列表，支持多段消息"""

    message_base_info: Dict[str, Any] = field(default_factory=dict)
    """消息基本信息，包含平台，用户信息等数据"""

    plain_text: str = ""
    """纯文本消息内容"""

    raw_message: str | None = None
    """原始消息内容"""

    is_group_message: bool = False
    """是否为群组消息"""

    is_private_message: bool = False
    """是否为私聊消息"""

    stream_id: str | None = None
    """流ID，用于标识消息流"""

    llm_prompt: str | None = None
    """LLM提示词"""

    llm_response_content: str | None = None
    """LLM响应内容"""

    llm_response_reasoning: str | None = None
    """LLM响应推理内容"""

    llm_response_model: str | None = None
    """LLM响应模型名称"""

    llm_response_tool_call: List[ToolCall] | None = None
    """LLM使用的工具调用"""

    action_usage: List[str] | None = None
    """使用的Action"""

    additional_data: Dict[Any, Any] = field(default_factory=dict)
    """附加数据，可以存储额外信息"""

    _modify_flags: ModifyFlag = field(default_factory=ModifyFlag)

    def __post_init__(self) -> None:
        """归一化消息段列表。"""
        if self.message_segments is None:
            self.message_segments = []

    def deepcopy(self) -> "MaiMessages":
        """深拷贝当前消息对象。

        Returns:
            MaiMessages: 深拷贝后的消息对象。
        """
        return copy.deepcopy(self)

    def to_transport_dict(self) -> Dict[str, Any]:
        """将消息转换为可通过 IPC 传输的纯字典。"""
        return {
            field_info.name: self._serialize_transport_value(getattr(self, field_info.name))
            for field_info in fields(MaiMessages)
            if field_info.name != "_modify_flags"
        }

    def apply_transport_update(self, modified_dict: Dict[str, Any]) -> "MaiMessages":
        """将 IPC 返回的消息字典回写到当前消息对象。"""
        updated_message = self.deepcopy()
        valid_fields = {field_info.name for field_info in fields(MaiMessages) if field_info.name != "_modify_flags"}

        for key, value in modified_dict.items():
            if key not in valid_fields:
                continue
            deserialized = self._deserialize_transport_field(key, value)
            setattr(updated_message, key, deserialized)

            if key == "message_segments":
                updated_message._modify_flags.modify_message_segments = True
            elif key == "plain_text":
                updated_message._modify_flags.modify_plain_text = True
            elif key == "llm_prompt":
                updated_message._modify_flags.modify_llm_prompt = True
            elif key == "llm_response_content":
                updated_message._modify_flags.modify_llm_response_content = True
            elif key == "llm_response_reasoning":
                updated_message._modify_flags.modify_llm_response_reasoning = True

        return updated_message

    @staticmethod
    def _serialize_transport_value(value: Any) -> Any:
        """递归序列化字段值为可传输结构。

        Args:
            value: 任意字段值。

        Returns:
            Any: 可用于 IPC 传输的纯 Python 值。
        """
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, list):
            return [MaiMessages._serialize_transport_value(item) for item in value]
        if isinstance(value, tuple):
            return [MaiMessages._serialize_transport_value(item) for item in value]
        if isinstance(value, dict):
            return {key: MaiMessages._serialize_transport_value(item) for key, item in value.items()}
        if hasattr(value, "__dict__"):
            return {
                key: MaiMessages._serialize_transport_value(item)
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        return value

    @staticmethod
    def _deserialize_transport_field(field_name: str, value: Any) -> Any:
        """反序列化特定字段的传输值。

        Args:
            field_name: 字段名称。
            value: 传输层返回的字段值。

        Returns:
            Any: 反序列化后的字段值。
        """
        if field_name == "message_segments" and isinstance(value, list):
            deserialized_segments: List[Seg] = []
            for segment in value:
                if isinstance(segment, Seg):
                    deserialized_segments.append(segment)
                elif isinstance(segment, dict) and "type" in segment:
                    deserialized_segments.append(Seg(type=segment.get("type", "text"), data=segment.get("data", "")))
            return deserialized_segments

        if field_name == "llm_response_tool_call" and isinstance(value, list):
            deserialized_tool_calls: List[ToolCall] = []
            for tool_call in value:
                if isinstance(tool_call, ToolCall):
                    deserialized_tool_calls.append(tool_call)
                elif isinstance(tool_call, dict):
                    deserialized_tool_calls.append(
                        ToolCall(
                            call_id=str(tool_call.get("call_id", "")),
                            func_name=str(tool_call.get("func_name", "")),
                            args=tool_call.get("args"),
                            extra_content=tool_call.get("extra_content")
                            if isinstance(tool_call.get("extra_content"), dict)
                            else None,
                        )
                    )
            return deserialized_tool_calls

        return value

    def modify_message_segments(self, new_segments: List[Seg], suppress_warning: bool = False) -> None:
        """修改消息段列表。

        Warning:
            在生成了 ``plain_text`` 的情况下调用此方法，可能会导致文本与消息段不一致。

        Args:
            new_segments: 新的消息段列表。
            suppress_warning: 是否抑制潜在不一致警告。
        """
        if self.plain_text and not suppress_warning:
            warnings.warn(
                "修改消息段后，plain_text可能与消息段内容不一致，建议同时更新plain_text",
                UserWarning,
                stacklevel=2,
            )
        self.message_segments = new_segments
        self._modify_flags.modify_message_segments = True

    def modify_llm_prompt(self, new_prompt: str, suppress_warning: bool = False) -> None:
        """修改 LLM 提示词。

        Warning:
            在没有生成 ``llm_prompt`` 的情况下调用此方法，可能会导致修改无效。

        Args:
            new_prompt: 新的提示词内容。
            suppress_warning: 是否抑制潜在无效修改警告。
        """
        if self.llm_prompt is None and not suppress_warning:
            warnings.warn(
                "当前llm_prompt为空，此时调用方法可能导致修改无效",
                UserWarning,
                stacklevel=2,
            )
        self.llm_prompt = new_prompt
        self._modify_flags.modify_llm_prompt = True

    def modify_plain_text(self, new_text: str, suppress_warning: bool = False) -> None:
        """修改生成的纯文本内容。

        Warning:
            在未生成 ``plain_text`` 的情况下调用此方法，可能会导致修改无效。

        Args:
            new_text: 新的纯文本内容。
            suppress_warning: 是否抑制潜在无效修改警告。
        """
        if not self.plain_text and not suppress_warning:
            warnings.warn(
                "当前plain_text为空，此时调用方法可能导致修改无效",
                UserWarning,
                stacklevel=2,
            )
        self.plain_text = new_text
        self._modify_flags.modify_plain_text = True

    def modify_llm_response_content(self, new_content: str, suppress_warning: bool = False) -> None:
        """修改生成的 LLM 响应正文。

        Warning:
            在未生成 ``llm_response_content`` 的情况下调用此方法，可能会导致修改无效。

        Args:
            new_content: 新的 LLM 响应内容。
            suppress_warning: 是否抑制潜在无效修改警告。
        """
        if not self.llm_response_content and not suppress_warning:
            warnings.warn(
                "当前llm_response_content为空，此时调用方法可能导致修改无效",
                UserWarning,
                stacklevel=2,
            )
        self.llm_response_content = new_content
        self._modify_flags.modify_llm_response_content = True

    def modify_llm_response_reasoning(self, new_reasoning: str, suppress_warning: bool = False) -> None:
        """修改生成的 LLM 推理内容。

        Warning:
            在未生成 ``llm_response_reasoning`` 的情况下调用此方法，可能会导致修改无效。

        Args:
            new_reasoning: 新的 LLM 推理内容。
            suppress_warning: 是否抑制潜在无效修改警告。
        """
        if not self.llm_response_reasoning and not suppress_warning:
            warnings.warn(
                "当前llm_response_reasoning为空，此时调用方法可能导致修改无效",
                UserWarning,
                stacklevel=2,
            )
        self.llm_response_reasoning = new_reasoning
        self._modify_flags.modify_llm_response_reasoning = True


# ============================================================================
# 核心架构变革 — 新增数据模型
# ============================================================================


class NoticeKind(Enum):
    """平台无关的通知分类枚举。"""

    AMBIENT = "ambient"
    """环境信号（如输入状态），不触发 Planner"""

    INTERACTION = "interaction"
    """交互信号（如戳一戳），可能触发 Planner"""

    INPUT_STATUS = "input_status"
    """用户正在输入，纯环境感知"""

    UNKNOWN = "unknown"
    """非通知消息或未知类型"""


@dataclass(frozen=True, slots=True)
class CoreMessage:
    """平台无关的核心消息 — 核心只关心这些字段。"""

    session_id: str
    """消息所属会话 ID"""

    plain_text: str
    """消息纯文本内容"""

    is_notify: bool
    """是否为通知消息"""

    notice_kind: NoticeKind = NoticeKind.UNKNOWN
    """通知分类（仅 is_notify=True 时有意义）"""

    sender_id: str = ""
    """发送者 ID"""

    sender_name: str = ""
    """发送者展示名称"""

    platform: str = ""
    """来源平台标识"""

    timestamp: datetime | None = None
    """消息时间戳"""

    additional_data: Dict[str, Any] = field(default_factory=dict, hash=False)
    """平台特定附加数据（核心不解析此字段）"""


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """不可变会话快照 — SessionRepository 返回此数据类。"""

    session_id: str
    """会话唯一标识"""

    session_name: str
    """会话展示名称"""

    platform: str
    """平台标识"""

    is_group_session: bool
    """是否为群聊"""

    group_id: str = ""
    """群 ID（仅群聊）"""

    group_name: str = ""
    """群名称（仅群聊）"""

    user_id: str = ""
    """用户 ID（仅私聊）"""

    user_nickname: str = ""
    """用户昵称（仅私聊）"""

    primary_agent_id: str = ""
    """主发言智能体 ID"""

    cohabitant_agent_ids: frozenset[str] = frozenset()
    """共居智能体 ID 列表（不可变集合）"""

    created_timestamp: datetime | None = None
    """会话创建时间"""

    last_active_timestamp: datetime | None = None
    """会话最后活跃时间"""

    account_id: str = ""
    """平台账号 ID（多账号路由）"""

    scope: str = ""
    """路由作用域（多账号路由）"""

    user_cardname: str = ""
    """用户备注名/群名片"""


@dataclass(frozen=True, slots=True)
class ThinkContext:
    """思考上下文 — 智能体思考时需要的所有输入。"""

    messages: tuple[CoreMessage, ...]
    """待处理的消息序列（不可变）"""

    emotion_state_text: str = ""
    """当前情绪状态描述（自然语言）"""

    inner_voice_text: str = ""
    """内心声音文本（由 InnerVoiceGenerator 生成）"""

    memory_personality_params: Dict[str, Any] | None = None
    """记忆性格参数（dict 形式，避免核心层依赖 maisaka 模块）"""

    relationship_text: str = ""
    """当前关系描述（自然语言）"""

    memory_snippets: tuple[str, ...] = ()
    """记忆片段（不可变）"""

    intuition_context: IntuitionContext | None = None
    """直觉触发结果（纯规则快速预判，供 prompt_builder 使用）"""

    cohabitant_summary: str = ""
    """共居智能体状态摘要（自然语言）"""

    trigger_reason: str = ""
    """触发思考的原因（user_message / inner_need / butler_interjection / reminder）"""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """附加元数据"""

    session_id: str = ""
    """会话 ID（工具执行需要）"""

    is_group_chat: bool = False
    """是否为群聊"""

    discovered_tools: tuple[str, ...] = ()
    """已发现的 deferred 工具名称（不可变）"""

    # LS-0: 思维连续性
    prev_thought_summary: str = ""
    """上次思考的内心独白摘要"""

    time_since_last_think: float = 0.0
    """距上次思考的秒数"""

    # T5: L1 内言语升级 + 分层性格注入
    expression_layer_text: str = ""
    """表现层性格文本（外显行为模式）"""

    experience_layer_text: str = ""
    """体验层性格文本（真实感受、内心性格）"""

    self_reply_summaries: tuple[str, ...] = ()
    """智能体自己最近说过的话摘要（每条 ≤ 100 字符）"""

    self_reply_visibility: str = "summary_only"
    """自回复可见性: summary_only / disabled / full"""

    lambda_value: float = 0.5
    """A3 λ 参数 — 控制 inner_voice 对 L2 的影响权重"""

    favor_injection_text: str = ""
    """好感度注入文本（ZG-26 b2: 从 system prompt 后移到 injected）"""

    thinking_agent_id: str = ""
    """本次思考的发起角色 id（上下文归属判定的唯一视角）"""


class ThinkAction(Enum):
    """思考动作类型。"""

    REPLY = "reply"
    TOOL_CALL = "tool_call"
    SILENT = "silent"
    ERROR = "error"
    WAIT = "wait"


class SilenceReason(Enum):
    """沉默原因 — 区分"只想不回"和"异常沉默"。"""

    INTENTIONAL = "intentional"
    """深思熟虑后决定不回复"""

    NO_CONTENT = "no_content"
    """LLM 返回空内容"""

    ERROR = "error"
    """LLM 调用出错"""

    TIMEOUT = "timeout"
    """思考超时"""

    REJECTED = "rejected"
    """被编排器拒绝激活"""

    TOOL_FAILED = "tool_failed"
    """工具调用失败"""

    MAX_CYCLES = "max_cycles"
    """循环达到上限"""


class CycleStatus(Enum):
    """思考循环状态。"""

    COMPLETED_REPLY = "completed_reply"
    """正常完成，有回复"""

    COMPLETED_SILENT = "completed_silent"
    """正常完成，无回复"""

    ERROR = "error"
    """异常终止"""

    TIMEOUT = "timeout"
    """超时终止"""


@dataclass(slots=True)
class ThinkCycleLog:
    """思考循环结构化日志 — 区分只想不回和异常沉默。"""

    agent_id: str = ""
    session_name: str = ""
    trigger: str = ""
    status: CycleStatus = CycleStatus.COMPLETED_SILENT
    silence_reason: SilenceReason | None = None
    thought_summary: str = ""
    action_summary: str = ""
    reply_text: str = ""
    cycle_count: int = 0
    tool_calls_made: list[str] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    error_detail: str = ""

    def to_log_line(self) -> str:
        parts = [f"[think] agent={self.agent_id}"]
        if self.trigger:
            parts.append(f"trigger={self.trigger}")
        if self.status == CycleStatus.COMPLETED_REPLY:
            parts.append("status=REPLY")
            parts.append(f'reply="{self.reply_text[:50]}"')
            if self.thought_summary:
                parts.append(f'thought="{self.thought_summary[:50]}"')
        elif self.status == CycleStatus.COMPLETED_SILENT:
            reason = self.silence_reason.value if self.silence_reason else "unknown"
            parts.append("status=SILENT")
            parts.append(f"reason={reason}")
            if self.silence_reason == SilenceReason.INTENTIONAL:
                parts.append(f'why="{self.thought_summary[:80]}"')
            elif self.silence_reason in (SilenceReason.ERROR, SilenceReason.TIMEOUT, SilenceReason.REJECTED, SilenceReason.TOOL_FAILED):
                parts.append(f'detail="{self.error_detail[:80]}"')
        elif self.status == CycleStatus.ERROR:
            parts.append("status=ERROR")
            parts.append(f'detail="{self.error_detail[:80]}"')
        elif self.status == CycleStatus.TIMEOUT:
            parts.append("status=TIMEOUT")
            parts.append(f'detail="{self.error_detail[:80]}"')
        if self.cycle_count > 1:
            parts.append(f"cycles={self.cycle_count}")
        if self.tool_calls_made:
            parts.append(f"tools={','.join(self.tool_calls_made)}")
        if self.elapsed_ms > 0:
            parts.append(f"elapsed={self.elapsed_ms}ms")
        return " ".join(parts)


@dataclass(slots=True)
class ThinkResult:
    """思考结果 — 智能体思考后产生的输出。"""

    action: ThinkAction = ThinkAction.SILENT
    """思考动作类型"""

    text: str = ""
    """回复文本（action=REPLY 时有值，仅来源于 reply 工具调用结果）"""

    tool_calls: List[dict[str, Any]] = field(default_factory=list)
    """工具调用（action=TOOL_CALL 时有值）"""

    emotion_type: str = ""
    """情绪类型（用于情绪感染）"""

    emotion_intensity: float = 0.0
    """情绪强度"""

    error_message: str = ""
    """错误信息（action=ERROR 时有值）"""

    thinking_time_ms: int = 0
    """思考耗时（毫秒）"""

    tool_calls_count: int = 0
    """本轮思考的工具调用总次数"""

    rounds: int = 1
    """工具循环轮次"""

    wait_seconds: float = 0.0
    """等待秒数（action=WAIT 时有效）"""

    silence_reason: SilenceReason | None = None
    """沉默原因（action=SILENT 时有值）"""

    thought_summary: str = ""
    """内心独白摘要（content[:100]，供日志使用）"""

    reply_sent: bool = False
    """reply 工具是否已内部发送消息（Orchestrator 据此避免重复发送）"""


# ============================================================================
# 从 heartFC_utils 迁移的公共数据模型
# ============================================================================


class CyclePlanInfo(TypedDict): ...  # TODO: 根据实际需要补充字段


class CycleActionInfo(TypedDict): ...  # TODO: 根据实际需要补充字段


@dataclass
class CycleDetail:
    """循环信息记录类"""

    cycle_id: int
    thinking_id: str = ""
    """思考ID"""
    start_time: float = field(default_factory=time.time)
    """开始时间，单位为秒"""
    end_time: float | None = None
    """结束时间，单位为秒，None表示未结束"""
    time_records: Dict[str, float] = field(default_factory=dict)
    """计时器记录，key为计时器名称，value为用时，单位为秒"""
    loop_plan_info: CyclePlanInfo | None = None
    """循环计划记录"""
    loop_action_info: CycleActionInfo | None = None
    """循环Action调用记录"""


@dataclass(frozen=True, slots=True)
class SendMessageResult:
    """消息发送结果 — MessagePortV2.send_message() 的统一返回类型。"""

    success: bool
    message_id: str = ""
    error: str = ""

    @classmethod
    def ok(cls, message_id: str = "") -> SendMessageResult:
        return cls(success=True, message_id=message_id)

    @classmethod
    def failed(cls, error: str = "") -> SendMessageResult:
        return cls(success=False, error=error)


@dataclass(frozen=True, slots=True)
class ObserveRequest:
    """连接主义记忆观察请求。

    统一写入入口，承载完整的语义上下文。
    """

    text: str
    valence: str = "neutral"
    timestamp: float | None = None
    source_id: str = ""
    session_id: str = ""
    agent_id: str = ""
    participants: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


# ── 记忆服务异常体系 ──────────────────────────────────


class MemoryServiceError(Exception):
    """记忆服务异常基类"""

    def __init__(self, message: str, original: Exception | None = None):
        super().__init__(message)
        self.message = message
        self.original = original


@dataclass(frozen=True)
class PersonInfoResult:
    """人物信息查询结果 — 不可变数据对象。"""
    is_known: bool
    person_id: str | None = None
    person_name: str | None = None


class TemporaryMemoryError(MemoryServiceError):
    """可重试的临时性错误（网络/超时/服务暂时不可用）"""


class PermanentMemoryError(MemoryServiceError):
    """不可恢复错误（配置错误/数据损坏）"""


class MemoryNotFoundError(MemoryServiceError):
    """查询目标不存在（画像/记忆条目）"""


# SessionMessage 真实定义在 src/common/data_models/session_message_data_model.py。
# 此处 re-export 供 core/maisaka 层使用，不直接依赖 chat 层。
from src.common.data_models.session_message_data_model import SessionMessage as SessionMessage  # noqa: E402, F401

# ── 纯数据类型 re-export（真实定义在 common 层）────────────────
from src.common.memory_types import (  # noqa: E402, F401
    IntuitionContext,
    MemoryHit,
    MemorySearchResult,
    MemoryWriteResult,
    ProfileView,
    RecallItem,
    RecallResult,
    ReflectResult,
)

__all__ = [
    # ... 既有类型 ...
    "MemoryServiceError",
    "TemporaryMemoryError",
    "PermanentMemoryError",
    "MemoryNotFoundError",
    "MemoryHit",
    "MemorySearchResult",
    "MemoryWriteResult",
    "RecallItem",
    "IntuitionContext",
    "RecallResult",
    "ProfileView",
    "ReflectResult",
    "PersonInfoResult",
    "SessionMessage",
    "PluginRuntimeSnapshot",
    "PluginRuntimeRenderSnapshot",
    "PluginRuntimeV2Snapshot",
    "PersonDetailSnapshot",
    "CacheCleanupConfig",
    "MaimMessageConfigSnapshot",
]


@dataclass(frozen=True)
class ReplyStyleSnapshot:
    """回复风格配置快照 — 不可变数据对象。"""
    chat_prompts: list[dict[str, Any]] = field(default_factory=list)
    private_chat_prompts: str = ""
    group_chat_prompt: str = ""
    enable_reply_quote: bool = False


@dataclass(frozen=True)
class AgentAutonomySnapshot:
    """智能体自主性配置快照。"""
    enabled: bool = True
    max_active_agents: int = 13
    auto_exit_timeout_minutes: int = 60
    interjection_enabled: bool = True
    interjection_intent_threshold: float = 60.0
    interjection_cooldown_minutes: int = 5
    max_interjections_per_hour: int = 3
    max_interjections_per_session_per_hour: int = 6
    interaction_signal_intent_bonus: float = 40.0
    embodied_planner_enabled: bool = True
    speaker_tag_format: str = "【{agent_name}】"
    orchestrator_strategy: str = "default"
    intent_expiry_seconds: int = 300
    vitality_base_value: float = 30.0
    vitality_activation_threshold: float = 70.0
    vitality_decay_per_minute: float = 2.0
    vitality_stimulus_message: float = 5.0
    vitality_stimulus_mention: float = 20.0
    vitality_stimulus_topic: float = 10.0
    vitality_tick_interval_seconds: int = 60
    fallback_exit_timeout_minutes: int = 120
    cohabitation_threshold_reduction: float = 10.0
    cohabitation_cooldown_reduction_minutes: float = 1.0
    interjection_threshold_minimum: float = 20.0
    interjection_cooldown_minimum_minutes: float = 1.0
    active_visible_to_active: bool = True
    standby_visible_to_active: bool = True
    standby_emotion_visible_to_active: bool = False
    dormant_visible_to_any: bool = False
    state_awareness_enabled: bool = True
    # ZG-23a: 出站去重 + 发言节流配置
    outbound_dedup_window_seconds: float = 3.0
    outbound_dedup_max_entries: int = 5000
    mention_chain_decay_base: float = 0.6
    mention_chain_max_depth: int = 4
    cohabitation_decay_factor: float = 0.5
    cohabitation_min_max: int = 2
    # ZH-1: 角色参数漂移配置
    zh1_role_drift_enabled: bool = False
    zh1_role_drift_drift_period: int = 500
    zh1_role_drift_regression_rate: float = 0.03
    zh1_role_drift_sigma_max: float = 0.3
    zh1_role_drift_selection_ratio: float = 0.167
    zh1_role_drift_w_interaction: float = 0.4
    zh1_role_drift_w_relation: float = 0.2
    zh1_role_drift_w_uniqueness: float = 0.3
    zh1_role_drift_w_emotion: float = 0.0
    zh1_role_drift_reflection_interval: int = 3600
    # butler_closure：管家收尾能力
    butler_scene_opening_enabled: bool = True
    butler_opening_silence_minutes: int = 30
    butler_topic_budget: int = 2
    butler_opening_max_chars: int = 120
    butler_opening_timeout_seconds: float = 4.0
    butler_closure_round_enabled: bool = True
    # agent_context_identity：上下文发言归属 / 自述第一人称（首发 false 灰度）
    context_identity_enabled: bool = False
    self_narration_first_person: bool = False



@dataclass(frozen=True)
class AMemorixIntegrationSnapshot:
    """A_memorix 集成配置快照。"""
    person_fact_writeback_enabled: bool = False
    chat_summary_writeback_enabled: bool = False
    chat_summary_writeback_message_threshold: int = 10
    chat_summary_writeback_context_length: int = 20
    enable_memory_query_tool: bool = True
    memory_query_default_limit: int = 5
    enable_person_profile_injection: bool = True
    person_profile_injection_max_profiles: int = 3
    heuristic_memory_recall_enabled: bool = False
    heuristic_memory_recall_window_size: int = 20
    heuristic_memory_recall_cache_ttl_seconds: int = 300
    heuristic_memory_recall_min_interval_seconds: int = 60
    heuristic_memory_recall_rate_limit_rpm: int = 10
    heuristic_memory_recall_min_new_messages: int = 60
    heuristic_memory_recall_limit: int = 3
    heuristic_memory_recall_max_chars: int = 900
    heuristic_memory_cross_chat_enabled: bool = False
    heuristic_memory_group_to_private_enabled: bool = False
    heuristic_memory_private_to_group_enabled: bool = False


@dataclass(frozen=True)
class TalkValueRuleSnapshot:
    """发言频率规则快照。"""
    platform: str = ""
    item_id: str = ""
    rule_type: str = ""
    time: str = ""
    value: float = 0.0


@dataclass(frozen=True)
class ReplyTimingSnapshot:
    """回复时序配置快照 — DEPRECATED，将由 vitality 系统替代。"""
    reply_trigger_mode: str = "hybrid"  # DEPRECATED: 将由 vitality + 规则引擎替代
    planner_interrupt_max_consecutive_count: int = 3  # DEPRECATED: 将由 ThinkingOrgan MAX_CYCLES 替代
    max_consecutive_wait_count: int = 3  # DEPRECATED: 将由 ThinkingOrgan MAX_CYCLES 替代
    talk_value: float = 0.5  # DEPRECATED: 将由 vitality 系统替代
    private_talk_value: float = 0.3  # DEPRECATED: 将由 vitality 系统替代
    enable_talk_value_rules: bool = False  # DEPRECATED: 将由 vitality 系统替代
    talk_value_rules: tuple[TalkValueRuleSnapshot, ...] = ()  # DEPRECATED: 将由 vitality 系统替代
    mentioned_bot_reply: bool = True  # DEPRECATED: 将由管家规则过滤替代
    inevitable_at_reply: bool = True  # DEPRECATED: 将由管家规则过滤替代


@dataclass(frozen=True)
class AgentInteractionSnapshot:
    """智能体交互配置快照。"""
    enabled: bool = True
    evaluation_interval_seconds: int = 30
    cooldown_minutes: int = 5
    max_interactions_per_hour: int = 10
    max_interactions_per_day: int = 50
    echo_enabled: bool = True
    echo_max_depth: int = 3
    echo_decay_ratio: float = 0.5
    monologue_enabled: bool = False
    monologue_min_interval_minutes: int = 30
    monologue_idle_threshold_minutes: int = 60
    monologue_emotion_intensity_threshold: int = 5


@dataclass(frozen=True)
class KeywordRuleSnapshot:
    """关键词规则快照。"""
    keywords: tuple[str, ...] = ()
    regex: tuple[str, ...] = ()
    reaction: str = ""


@dataclass(frozen=True)
class KeywordReactionSnapshot:
    """关键词反应配置快照。"""
    keyword_rules: tuple[KeywordRuleSnapshot, ...] = ()
    regex_rules: tuple[KeywordRuleSnapshot, ...] = ()


@dataclass(frozen=True)
class PluginRuntimeSnapshot:
    """插件运行时配置快照 — 替代 global_config.plugin_runtime 整体对象访问。"""

    enabled: bool = False
    ipc_socket_path: str = ""
    health_check_interval_sec: float = 60.0
    max_restart_attempts: int = 3
    runner_spawn_timeout_sec: float = 30.0
    hook_blocking_timeout_sec: float = 5.0


@dataclass(frozen=True)
class PluginRuntimeRenderSnapshot:
    """插件运行时浏览器渲染配置快照 — 替代 global_config.plugin_runtime.render 访问。"""

    enabled: bool = True
    browser_ws_endpoint: str = ""
    executable_path: str = ""
    browser_install_root: str = "data/playwright-browsers"
    headless: bool = True
    concurrency_limit: int = 3


@dataclass(frozen=True)
class PluginRuntimeV2Snapshot:
    """v2 插件运行时配置快照。"""

    enabled: bool = False
    host_listen_address: str = "0.0.0.0:50051"
    runner_spawn_count: int = 0
    runner_spawn_timeout_sec: float = 30.0
    health_check_interval_sec: float = 60.0
    max_restart_attempts: int = 3
    scope_approval_file: str = "data/scope_approvals.json"
    default_rpm: int = 60


@dataclass(frozen=True)
class PersonDetailSnapshot:
    """人物详情快照 — 替代 Person 类直接实例化访问。"""

    is_known: bool = False
    person_id: str = ""
    person_name: str = ""
    nickname: str = ""


@dataclass(frozen=True)
class CacheCleanupConfig:
    """缓存清理配置快照 — emoji/image cache_cleanup 通用。

    emoji 和 image 的 cache_cleanup 结构高度相似，用同一个快照类型。
    适配器从各自配置域映射字段。
    """

    enabled: bool = False
    check_interval_hours: float = 24.0
    emoji_file_retention_days: float = 30.0
    no_file_record_retention_days: float = 90.0
    image_file_retention_days: float = 14.0
    no_file_result_retention_days: float = 30.0


@dataclass(frozen=True)
class MaimMessageConfigSnapshot:
    """MaimMessage 配置快照 — 替代 global_config.maim_message 整体对象。"""

    enable_api_server: bool = False
    api_server_host: str = ""
    api_server_port: int = 0
    api_server_use_wss: bool = False
    api_server_cert_file: str = ""
    api_server_key_file: str = ""
    api_server_allowed_api_keys: tuple[str, ...] = ()
    ws_server_host: str = ""
    ws_server_port: int = 0
    auth_token: tuple[str, ...] = ()


# ============================================================================
# 模型配置接缝的类型视图（`ModelConfigPort` 用）
# ============================================================================
#
# 为什么在 core：`protocols.py` 的 `ModelConfigPort` 原先直接标注配置层的 pydantic
# 实现类（`ModelConfig` / `APIProvider` / `ModelInfo` / `TaskConfig`）。那几行在
# `if TYPE_CHECKING:` 下，运行时没有依赖，但**类型面**把 core 焊在了旧配置系统上——
# 旧配置一删，Protocol 跟着编译不过。契约归 core、实现归配置层，删实现时才不用动契约。
#
# 为什么是 `Protocol` 而不是本文件里既有的 frozen dataclass 快照
# （`PluginRuntimeSnapshot` 那一族）：快照会**换掉运行时对象**，而本接缝的 35 处调用点
# 拿的是 ConfigManager 持有的活配置对象——热重载、注入客户端前的 `model_copy` 副本、
# `BaseClient.client_instance_cache` 按 provider 名缓存，都依赖同一份对象身份。
# 本批只允许动类型面 ⇒ 用结构化视图：真实实例天然满足，运行时零变化。
#
# 字段口径：**只声明本接缝的消费者实际读到的字段**，且每条都注明了消费点，便于下一批
# 按证据收窄/迁移。pydantic 专有 API（`model_dump` / `model_copy`）刻意不声明，见
# `APIProviderLike` 的说明。


class TaskConfigLike(Protocol):
    """任务配置契约 — `ModelConfigPort.get_task_config()` 的返回视图。

    这里不裁字段：`TaskConfig` 的公开字段正好 6 个，且全被消费者读到
    （`LLMRequest._build_task_config_signature` 读满 6 个；`mode_utils` /
    `expression_selector` / `image_manager` / `chat_history_refresher` 读 `model_list`）。
    """

    model_list: list[str]
    """模型名列表（首个为当前任务选中的模型）。"""

    max_tokens: int
    """任务最大输出 token 数。"""

    temperature: float
    """采样温度。"""

    slow_threshold: float
    """慢请求告警阈值（秒）。"""

    selection_strategy: str
    """模型选择策略（balance / random / sequential）。"""

    hard_timeout: float
    """任务硬超时（秒），到点取消请求并换下一个模型。"""


class ModelInfoLike(Protocol):
    """模型信息契约 — `ModelConfigPort.get_model_info()` 的返回视图。

    裁掉了 `category` / `capabilities`：只有适配器 `ConfigManagerModelConfigPort._to_entry()`
    读它们（适配器允许持有具体类，走的是 `ModelRegistry` 建索引），本接缝的消费者不读。
    """

    name: str
    """模型名（配置里的名字，日志/用量统计用）。"""

    model_identifier: str
    """服务商侧模型标识符（请求体 `model` 字段直接用它）。"""

    api_provider: str
    """所属提供商名（再经 `get_provider()` 换连接参数）。"""

    visual: bool
    """是否支持视觉输入（multimodal replyer / planner 判定）。"""

    context_window: int | None
    """上下文窗口（token）；null 时调用方回落全局默认。"""

    temperature: float | None
    """模型级温度；null 表示不覆盖任务配置（`extra_params` 里可能还有一份）。"""

    max_tokens: int | None
    """模型级输出上限；null 表示不覆盖任务配置。"""

    extra_params: dict[str, Any]
    """额外请求参数（`temperature` / `max_tokens` 亦可写在里面作为模型级默认）。"""

    force_stream_mode: bool
    """强制流式输出（模型不支持非流式时开启）。"""

    cache: bool
    """是否启用输入缓存计费。"""

    cache_price_in: float
    """缓存命中输入价格（元 / M token），仅 `cache=True` 时使用。"""

    price_in: float
    """输入价格（元 / M token），用于成本统计。"""

    price_out: float
    """输出价格（元 / M token），用于成本统计。"""


class APIProviderLike(Protocol):
    """API 提供商契约 — `ModelConfigPort.get_provider()` 的返回视图。

    字段没有裁减空间：`llm_models` 的客户端构造链把 18 个字段全读了一遍
    （`openai_compat.build_openai_compatible_client_config` 读鉴权/头/查询参数，
    `openai_client` 读推理与工具参数解析模式、org/project/timeout/max_retry，
    `gemini_client` 读 base_url/timeout/api_key，`plugin_client` 读 timeout，
    `request_snapshot` 读快照全字段）。再窄就是谎报契约。

    **刻意未声明的两处 pydantic API（已知债，随旧配置系统一起清）**：

    - `plugin_client._build_api_provider_snapshot()` 调 `model_dump(mode="json")`；
    - `model_configs.resolve_provider_env_references()` 调 `model_copy(update=...)`。

    两者都要求"provider 是一个 pydantic 模型"。把它们写进本契约等于把 pydantic 焊进
    core，所以不声明——代价是这两处调用点在类型上不满足本契约，这正是删除旧配置前
    必须先改掉它们的原因（改成纯数据描述符 + 在别处解析引用）。

    ``api_key`` 是**盘上原文**（可能是 ``${VAR}`` 引用）：解析发生在"读出配置后、注入
    客户端之前"（`base_client.get_client_class_instance` →
    `resolve_provider_env_references`，且只作用在传给工厂的副本上）。**不要**在本接缝里
    就地解析或改写——就地解析会把明文写回配置文件（3 段实测过的写回洞）。
    """

    name: str
    """提供商名（`get_provider()` 的查询键，也是客户端实例缓存的键）。"""

    base_url: str
    """API BaseURL。"""

    api_key: str
    """盘上原文的 API 密钥（可能是 `${VAR}` 引用，解析位在注入客户端之前）。"""

    client_type: str
    """客户端类型（openai / gemini / 插件提供的类型）。"""

    auth_type: str
    """OpenAI 兼容鉴权方式（bearer / header / query / none）。"""

    auth_header_name: str
    """`auth_type=header` 时的请求头名。"""

    auth_header_prefix: str
    """`auth_type=header` 时的请求头前缀（留空表示直接发送原始密钥）。"""

    auth_query_name: str
    """`auth_type=query` 时的查询参数名。"""

    default_headers: dict[str, str]
    """所有请求默认附带的 HTTP Header。"""

    default_query: dict[str, str]
    """所有请求默认附带的查询参数。"""

    organization: str | None
    """OpenAI 官方接口可选的 organization。"""

    project: str | None
    """OpenAI 官方接口可选的 project。"""

    model_list_endpoint: str
    """模型列表端点路径（OpenAI 兼容接口探测用）。"""

    reasoning_parse_mode: str
    """推理内容解析模式（auto / native / think_tag / none）。"""

    tool_argument_parse_mode: str
    """工具调用参数解析模式（auto / strict / repair / double_decode）。"""

    max_retry: int
    """单个模型调用失败时的最大重试次数。"""

    timeout: int
    """API 调用超时（秒）。"""

    retry_interval: int
    """重试间隔（秒）。"""


class ModelTaskConfigLike(Protocol):
    """任务配置容器契约 — `ModelConfigLike.model_task_config` 的视图。

    .. deprecated::
        ZG-12 组件自治后任务名不再是配置键，新代码走
        :meth:`ModelConfigPort.resolve_by_capability`。

    11 个槽位都要留在契约里：消费者按任务名**动态**取用
    （`chat_loop_service._resolve_model_task_name` 查表、`utils_model._resolve_task_config_name`
    遍历 `dir()`），少声明一个就有一份合法配置被判成类型不符。槽位顺序沿用
    `src.config.model_configs.ModelTaskConfig` 的定义顺序。
    """

    replyer: TaskConfigLike
    """回复模型。"""

    planner: TaskConfigLike
    """规划模型。"""

    memory: TaskConfigLike
    """记忆模型。"""

    mid_memory: TaskConfigLike
    """聊天回想模型。"""

    utils: TaskConfigLike
    """小任务模型（概括/整理）。"""

    learner: TaskConfigLike
    """表达方式与黑话学习模型。"""

    expression_use: TaskConfigLike
    """表达方式使用模型。"""

    emoji: TaskConfigLike
    """表情包发送模型。"""

    vlm: TaskConfigLike
    """视觉模型。"""

    voice: TaskConfigLike
    """语音识别模型。"""

    embedding: TaskConfigLike
    """嵌入模型。"""


class ModelConfigLike(Protocol):
    """模型配置契约 — `ModelConfigPort.get_model_config()` 的返回视图。

    只声明消费者读到的三个属性：`main.py` 启动期声明校验（`models` / `api_providers`）、
    `llm_models/model_client/__init__.py`（`api_providers`）、`chat_loop_service` 与
    `utils_model`（`model_task_config`）、`service_task_resolver` /
    `emoji_manager` / `A_memorix`（整体透传给下游）。

    注意：`get_model_config()` 是**尚未收窄的逃生舱**——22 处调用点里有相当一部分是为了
    摸到整张配置图。它最终应被 `resolve_by_capability` / `get_effective_config` 取代，
    本视图只是让它不再点名配置层实现类。
    """

    models: list[ModelInfoLike]
    """模型列表。"""

    model_task_config: ModelTaskConfigLike
    """任务配置容器（deprecated，见 `ModelTaskConfigLike`）。"""

    api_providers: list[APIProviderLike]
    """API 提供商列表。"""
