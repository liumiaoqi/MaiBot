"""核心接口契约 — 组件兼容核心，核心定义接口，组件实现接口。

本模块定义所有核心 Protocol，核心模块只依赖这些 Protocol，
不直接导入组件具体类（chat_manager、HeartflowManager 等）。

适配器层（src/core/adapters/）是唯一允许导入组件具体类的地方。
"""


from typing import TYPE_CHECKING, Any, Dict, List, Optional

from typing import Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.common.data_models.message_component_data_model import MessageSequence
    from src.config.config import ModelConfig
    from src.config.model_configs import APIProvider, ModelInfo, TaskConfig
    from src.common.memory_types import ProfileView, RecallItem, RecallResult, ReflectResult
    from src.common.data_models.llm_service_data_models import (
        LLMAudioTranscriptionResult,
        LLMGenerationOptions,
        LLMImageOptions,
        LLMResponseResult,
        MessageFactory,
    )
    from src.maisaka.agent.config import AgentConfig
    from src.core.types import (
        AgentAutonomySnapshot,
        AgentInteractionSnapshot,
        AMemorixIntegrationSnapshot,
        CacheCleanupConfig,
        KeywordReactionSnapshot,
        MaimMessageConfigSnapshot,
        MemorySearchResult,
        MemoryWriteResult,
        NoticeKind,
        ObserveRequest,
        PersonDetailSnapshot,
        PersonInfoResult,
        PluginRuntimeRenderSnapshot,
        PluginRuntimeSnapshot,
        ReplyTimingSnapshot,
        ReplyStyleSnapshot,
        SendMessageResult,
        SessionInfo,
        SessionMessage,
        ThinkContext,
        ThinkResult,
    )


@runtime_checkable
class SessionRepository(Protocol):
    """会话查询接口 — 核心通过此接口查询会话信息，不直接依赖 chat_manager。"""

    async def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """查询会话信息，返回不可变快照。

        Args:
            session_id: 会话 ID

        Returns:
            SessionInfo 快照，不存在时返回 None
        """

    async def get_session_name(self, session_id: str) -> str:
        """查询会话展示名称。

        Args:
            session_id: 会话 ID

        Returns:
            群名称或 "xxx的私聊"，不存在时返回 session_id 本身
        """


@runtime_checkable
class AgentRoutingService(Protocol):
    """智能体路由接口 — 核心通过此接口解析会话应使用的智能体。"""

    def resolve_agent(self, session_id: str, group_id: Optional[str] = None) -> AgentConfig:
        """解析会话应使用的智能体。

        Args:
            session_id: 会话 ID
            group_id: 群 ID（可选）

        Returns:
            AgentConfig，解析失败时返回默认智能体
        """

    def bind_session(self, session_id: str, agent_id: str) -> bool:
        """绑定会话到指定智能体。

        Args:
            session_id: 会话 ID
            agent_id: 智能体 ID

        Returns:
            绑定是否成功（智能体不存在或达到上限时返回 False）
        """

    def unbind_session(self, session_id: str, agent_id: Optional[str] = None) -> None:
        """解除会话的智能体绑定。

        Args:
            session_id: 会话 ID
            agent_id: 智能体 ID，None 时清除该会话所有绑定
        """

    def get_primary_agent(self, session_id: str) -> Optional[str]:
        """获取会话的主发言智能体 ID。

        Args:
            session_id: 会话 ID

        Returns:
            主发言智能体 ID，不存在时返回 None
        """

    def get_session_all_agents(self, session_id: str) -> frozenset[str]:
        """获取会话绑定的所有智能体 ID（不可变集合）。

        Args:
            session_id: 会话 ID

        Returns:
            不可变的智能体 ID 集合
        """


@runtime_checkable
class ChatRuntime(Protocol):
    """运行时接口 — 打破 HeartFlow ↔ Maisaka 循环依赖。"""

    @property
    def session_id(self) -> str:
        """运行时所属会话 ID。"""

    @property
    def session_name(self) -> str:
        """运行时所属会话展示名称。"""

    @property
    def agent_id(self) -> str:
        """当前活跃智能体 ID。"""

    @agent_id.setter
    def agent_id(self, value: str) -> None:
        """设置当前活跃智能体 ID。"""

    def get_prompt_template_name(self) -> str:
        """获取当前应使用的提示词模板名。"""

    async def enqueue_proactive_task(
        self,
        *,
        plugin_id: str,
        intent: str,
        reason: str = "",
        priority: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """触发主动对话任务。

        **仅用于插件主动对话，禁止用于多智能体插话。**

        合法调用方：plugin_runtime（插件主动对话触发）
        禁止用途：多智能体插话应通过 ThinkingOrgan 直接触发，
                  管家/提醒/Orchestrator 不得调用此方法。
        违反约束的后果：CI 不通过（grep 守卫 + code review）。

        Args:
            plugin_id: 触发来源标识
            intent: 触发意图描述
            reason: 触发原因
            priority: 优先级标识
            metadata: 附加元数据

        Returns:
            任务执行结果
        """

    def append_context_message(self, message: Any, *, source_kind: str = "plugin") -> int:
        """向聊天历史追加上下文消息。"""

    def get_talk_frequency_adjust(self) -> float:
        """获取当前回复频率倍率。"""

    def adjust_talk_frequency(self, frequency: float) -> None:
        """调整当前回复频率倍率。"""

    async def start(self) -> None:
        """启动运行时。"""

    async def stop(self) -> None:
        """停止运行时。"""


@runtime_checkable
class MessageIngestionPort(Protocol):
    """消息入站端口 — 外部系统通过此接口向主链路投递消息，不直接依赖 chat_bot 全局单例。"""

    async def receive_message(self, message: SessionMessage) -> None:
        """接收并处理入站消息。"""
        ...

    async def message_process(self, message_data: Dict[str, Any]) -> None:
        """处理 Platform IO 入站封装。"""
        ...


@runtime_checkable
class ChatRuntimeRegistry(Protocol):
    """运行时注册表接口 — 核心通过此接口查询运行时实例。"""

    async def get_runtime(self, session_id: str) -> Optional[ChatRuntime]:
        """获取指定会话的运行时实例。

        Args:
            session_id: 会话 ID

        Returns:
            ChatRuntime 实例，不存在时返回 None
        """

    async def get_or_create_runtime(self, session_id: str) -> ChatRuntime:
        """获取或创建指定会话的运行时实例。

        Args:
            session_id: 会话 ID

        Returns:
            ChatRuntime 实例

        Raises:
            RuntimeCreationError: 创建失败时抛出
        """

    def list_runtimes(self) -> list[ChatRuntime]:
        """列出所有活跃的运行时实例。

        Returns:
            ChatRuntime 实例列表
        """

    def get_runtime_sync(self, session_id: str) -> Optional[ChatRuntime]:
        """同步获取指定会话的运行时实例。

        Args:
            session_id: 会话 ID

        Returns:
            ChatRuntime 实例，不存在时返回 None
        """

    def remove_runtime(self, session_id: str) -> Optional[ChatRuntime]:
        """移除并返回指定会话的运行时实例。

        Args:
            session_id: 会话 ID

        Returns:
            被移除的 ChatRuntime 实例，不存在时返回 None
        """


@runtime_checkable
class ChatRuntimeFactory(Protocol):
    """运行时工厂接口 — heartflow_manager 通过此接口创建运行时，不依赖具体类。

    打破 heartflow_manager → maisaka 的物理依赖：
    heartflow_manager 通过工厂创建运行时，不再知道 MaisakaHeartFlowChatting。
    """

    def create_runtime(self, session_id: str) -> ChatRuntime:
        """创建指定会话的运行时实例。

        Args:
            session_id: 会话 ID

        Returns:
            ChatRuntime 实例（未启动，调用方负责 start()）
        """


@runtime_checkable
class NoticeClassifier(Protocol):
    """通知分类接口 — 平台无关的通知分类机制。"""

    def classify(self, message: Any) -> NoticeKind:
        """分类通知消息。

        Args:
            message: 原始消息对象（平台特定）

        Returns:
            NoticeKind 枚举值，非通知消息返回 NoticeKind.UNKNOWN
        """


@runtime_checkable
class MemoryServicePort(Protocol):
    """记忆服务接口 — 核心通过此接口访问 A_memorix。"""

    async def observe_experience(self, request: ObserveRequest) -> MemoryWriteResult:
        """观察智能体的体验并写入连接主义记忆。

        统一入口，接受 ObserveRequest 对象（所有字段有默认值）。

        Returns:
            MemoryWriteResult 写入结果（含 observation_id 和 concept_names）
        """

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        mode: str = "search",
        chat_id: str = "",
        person_id: str = "",
        agent_id: str = "",
        time_start: str | float | None = None,
        time_end: str | float | None = None,
        respect_filter: bool = True,
        user_id: str = "",
        group_id: str = "",
    ) -> MemorySearchResult:
        """检索记忆。

        Args:
            query: 检索查询
            limit: 返回结果上限
            mode: 检索模式（search/time/hybrid/episode/aggregate）
            chat_id: 聊天流 ID
            person_id: 人物 ID
            time_start: 时间范围起点
            time_end: 时间范围终点
            respect_filter: 是否遵守过滤规则
            user_id: 用户 ID
            group_id: 群组 ID

        Returns:
            MemorySearchResult 检索结果
        """

    async def get_person_profile(self, person_id: str, *, limit: int = 4) -> dict[str, Any]:
        """查询人物画像。

        Args:
            person_id: 人物 ID
            limit: 返回段落数上限

        Returns:
            画像数据字典，不存在时返回 None
        """

    async def profile_admin(self, *, action: str, **kwargs: Any) -> dict[str, Any]:
        """画像管理操作。

        Args:
            action: 操作类型（query/update/delete）
            **kwargs: 操作参数（person_id/person_keyword/limit 等）

        Returns:
            操作结果字典
        """

    async def maintain_memory(
        self,
        *,
        action: str,
        target: str = "",
        hours: Optional[float] = None,
        reason: str = "",
        limit: int = 50,
    ) -> MemoryWriteResult:
        """记忆维护操作（衰减/强化/冻结/恢复/保护）。

        Args:
            action: 操作类型（decay/reinforce/freeze/restore/protect）
            target: 目标标识
            hours: 时间参数（小时）
            reason: 操作原因
            limit: 批量操作上限

        Returns:
            MemoryWriteResult 操作结果
        """

    async def delete_admin(self, *, action: str, timeout_ms: int = 120000, **kwargs: Any) -> dict[str, Any]:
        """删除管理操作（preview/confirm/cancel）。

        Args:
            action: 操作类型（preview/confirm/cancel）
            timeout_ms: 超时时间（毫秒）
            **kwargs: 操作参数（selector 等）

        Returns:
            操作结果字典
        """

    async def enqueue_feedback_task(
        self,
        *,
        query_tool_id: str,
        session_id: str,
        query_timestamp: Any = None,
        structured_content: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """反馈纠错任务入队。

        Args:
            query_tool_id: 查询工具调用 ID
            session_id: 会话 ID
            query_timestamp: 查询时间戳
            structured_content: 结构化内容

        Returns:
            入队结果字典
        """

    async def build_profile_injection_text(self, raw_text: str) -> str:
        """构建画像注入文本。

        Args:
            raw_text: 原始画像文本

        Returns:
            格式化后的注入文本
        """

    async def set_memory_personality(self, agent_id: str, params: dict[str, Any]) -> None:
        """设置智能体记忆性格参数。

        Args:
            agent_id: 智能体 ID
            params: 记忆性格参数字典
        """

    async def recall(
        self,
        seeds: list[str],
        *,
        agent_id: str = "",
        min_weight: float = 0.05,
        max_results: int = 20,
    ) -> list[RecallItem]:
        """概念激活扩散召回——连接主义原生召回。"""

    async def recall_with_intuition(
        self,
        seeds: list[str],
        context_text: str,
        *,
        agent_id: str = "",
        min_weight: float = 0.05,
        max_results: int = 20,
        max_tokens: int = 800,
    ) -> RecallResult:
        """直觉召回——概念激活 + 认知和叙事深度。"""

    async def derive_profile(
        self,
        subject: str,
        *,
        observer: str = "",
    ) -> ProfileView:
        """画像实时视图——连接主义原生画像。"""

    async def reflect(
        self,
        subject: str,
        *,
        agent_id: str = "",
    ) -> ReflectResult:
        """反思——多声音视角 + 矛盾检测。"""

    async def weave_narrative(
        self,
        *,
        agent_id: str = "",
    ) -> dict[str, Any]:
        """触发叙事编织——Fragment → Episode → Saga。"""

    async def heartbeat_maintenance(
        self,
        *,
        agent_id: str = "",
        elapsed_hours: float = 1.0,
    ) -> dict[str, Any]:
        """完整心跳维护——granular_decay + advance_lifecycle + process_cognitive_decay。"""


@runtime_checkable
class SessionInfoPort(Protocol):
    """会话信息查询接口 — 供组件反向查询会话信息。"""

    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """查询会话信息（仅内存缓存）。

        Args:
            session_id: 会话 ID

        Returns:
            SessionInfo 快照，不存在时返回 None
        """

    def get_existing_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """查询会话信息（内存未命中时从数据库加载）。

        Args:
            session_id: 会话 ID

        Returns:
            SessionInfo 快照，不存在时返回 None
        """


@runtime_checkable
class ThinkingOrgan(Protocol):
    """思维管道接口 — 每个智能体拥有自己的思维管道。

    Orchestrator 只协调"谁在思考"，不关心"怎么思考"。
    这是 Agent-owns-Thinking 架构的核心接口。
    """

    @property
    def agent_id(self) -> str:
        """所属智能体 ID。"""

    @property
    def is_degraded(self) -> bool:
        """是否降级（提示词构建失败等）。"""

    async def think(self, context: ThinkContext) -> ThinkResult:
        """执行一次思考。

        Args:
            context: 思考上下文（消息、内心状态、记忆片段）

        Returns:
            思考结果（回复文本、工具调用、或不回复）
        """

    async def think_proactive(self, reason: str, context: ThinkContext) -> ThinkResult:
        """执行一次主动思考（无外部消息触发）。

        Args:
            reason: 主动思考原因（欲望/提醒/管家协调）
            context: 思考上下文

        Returns:
            思考结果
        """


@runtime_checkable
class ThinkingOrganFactory(Protocol):
    """思维管道工厂 — 为智能体创建 ThinkingOrgan 实例。"""

    def create(self, agent_id: str, session_id: str) -> ThinkingOrgan:
        """为指定智能体创建思维管道。

        Args:
            agent_id: 智能体 ID
            session_id: 会话 ID

        Returns:
            ThinkingOrgan 实例
        """


@runtime_checkable
class MessagePortV2(Protocol):
    """统一消息端口协议 — 回复系统 v2。

    核心转变：7 个碎片化方法 → 1 个统一方法 send_message()。
    MessageSequence 直接传递，不做 dict 序列化/反序列化。
    引用回复通过 reply_to_id 传递，找不到时降级为不引用（不丢弃消息）。

    迁移已完成（阶段1-5），旧 MessagePort Protocol 已移除。
    """

    async def send_message(
        self,
        session_id: str,
        message: MessageSequence,
        *,
        reply_to_id: str = "",
        agent_id: str = "",
        source: str = "core",
    ) -> SendMessageResult:
        """发送消息 — 统一接口，覆盖所有消息类型。

        Args:
            session_id: 目标会话 ID
            message: MessageSequence 消息序列（直接传递，不做序列化）
            reply_to_id: 被引用消息的 ID（可选，找不到时降级为不引用）
            agent_id: 发言智能体 ID
            source: 消息来源标识（reply/interjection/reminder/proactive）

        Returns:
            SendMessageResult 包含发送结果
        """


@runtime_checkable
class SessionLifecyclePort(Protocol):
    """会话生命周期接口 — 会话创建/获取、持久化、初始化。"""

    async def get_or_create_session_id(
        self,
        platform: str,
        user_id: str = "",
        group_id: str = "",
        account_id: str = "",
        scope: str = "",
    ) -> str:
        """获取或创建会话，返回 session_id。

        Args:
            platform: 平台标识
            user_id: 用户 ID（私聊）
            group_id: 群 ID（群聊）
            account_id: 平台账号 ID
            scope: 路由作用域

        Returns:
            session_id 字符串
        """

    def save_all_sessions(self) -> None:
        """将所有内存会话持久化到数据库。"""

    async def initialize(self) -> None:
        """初始化会话管理器（从数据库加载会话、恢复绑定等）。"""

    async def regularly_save_sessions(self, interval_seconds: float = 300) -> None:
        """定时持久化循环。

        Args:
            interval_seconds: 保存间隔（秒）
        """


@runtime_checkable
class SessionQueryPort(Protocol):
    """会话查询接口 — 批量解析、消息缓存、会话列表、路由元数据。"""

    def resolve_sessions_by_target(
        self,
        *,
        platform: str,
        target_id: str,
        chat_type: str,
    ) -> List[SessionInfo]:
        """按目标批量解析会话。

        Args:
            platform: 平台标识
            target_id: 目标 ID（群 ID 或用户 ID）
            chat_type: 聊天类型（group/private）

        Returns:
            SessionInfo 列表
        """

    def resolve_session_ids_by_target(
        self,
        *,
        platform: str,
        target_id: str,
        chat_type: str,
    ) -> set[str]:
        """按目标批量解析会话 ID。

        Args:
            platform: 平台标识
            target_id: 目标 ID
            chat_type: 聊天类型

        Returns:
            session_id 集合
        """

    def get_last_message(self, session_id: str) -> Any:
        """获取会话最新消息。

        Args:
            session_id: 会话 ID

        Returns:
            最新消息对象，不存在时返回 None
        """

    def list_sessions(self) -> List[SessionInfo]:
        """获取所有会话列表。

        Returns:
            SessionInfo 列表
        """

    def get_route_metadata(self, session_id: str) -> Dict[str, object]:
        """获取会话路由元数据（account_id/scope 等路由键）。

        Args:
            session_id: 会话 ID

        Returns:
            路由元数据字典
        """

    def get_session_count(self) -> int:
        """获取会话总数。

        Returns:
            会话数量
        """


@runtime_checkable
class MessageRegistryPort(Protocol):
    """消息注册接口 — 入站消息注册到会话管理器。"""

    def register_message(self, message: Any) -> None:
        """注册入站消息。

        Args:
            message: 入站消息对象

        Raises:
            ValueError: 消息缺少必要字段时
        """


@runtime_checkable
class ModelConfigPort(Protocol):
    """模型配置查询接口 — 核心通过此接口查询模型配置，不直接依赖 ConfigManager。

    设计原则：
    1. 消费者通过此 Protocol 查询模型配置，不感知 ConfigManager 具体类
    2. 支持智能体级配置覆盖（agent_id 非空时合并 model_config_override）
    3. 查询为纯内存操作，≤1ms
    """

    def get_task_config(self, task_name: str, *, agent_id: str = "") -> TaskConfig:
        """按任务名查询任务配置，支持智能体级覆盖。

        Args:
            task_name: 任务配置名称（replyer/planner/memory/utils/vlm/embedding 等）
            agent_id: 智能体 ID，非空时应用该智能体的 model_config_override

        Returns:
            TaskConfig 实例（全局配置或智能体覆盖后的配置）

        Raises:
            ValueError: 任务名不存在时
            RuntimeError: 配置未初始化时
        """

    def get_model_info(self, model_name: str) -> ModelInfo:
        """按模型名查询模型信息。

        Args:
            model_name: 模型名称（对应 ModelInfo.name）

        Returns:
            ModelInfo 实例

        Raises:
            ValueError: 模型名不存在时
            RuntimeError: 配置未初始化时
        """

    def get_provider(self, provider_name: str) -> APIProvider:
        """按提供商名查询提供商配置。

        Args:
            provider_name: 提供商名称（对应 APIProvider.name）

        Returns:
            APIProvider 实例

        Raises:
            ValueError: 提供商名不存在时
            RuntimeError: 配置未初始化时
        """

    def get_model_config(self) -> ModelConfig:
        """获取完整模型配置。

        Returns:
            ModelConfig 实例（全局配置，不含智能体覆盖）

        Raises:
            RuntimeError: 配置未初始化时
        """

    def list_model_names(self) -> list[str]:
        """列出所有已配置的模型名称。"""
        ...

    def register_reload_callback(self, callback: Any) -> None:
        """注册配置热重载回调。

        Args:
            callback: 回调函数，支持无参或接收 Sequence[str] 类型的变更范围
        """

    def unregister_reload_callback(self, callback: Any) -> None:
        """注销配置热重载回调。

        Args:
            callback: 先前注册过的回调对象
        """

@runtime_checkable
class ReplyerServicePort(Protocol):
    """回复器服务接口 — maisaka 通过此接口获取回复生成器。"""

    def get_replyer(
        self,
        chat_stream: Optional[SessionInfo] = None,
        chat_id: Optional[str] = None,
        request_type: str = "replyer",
        replyer_type: str = "default",
    ) -> Optional[Any]:
        """获取回复生成器实例。"""


@runtime_checkable
class ImageDescriptionPort(Protocol):
    """图片描述服务接口 — maisaka 通过此接口请求图片描述。"""

    async def get_image_description(
        self,
        image_hash: str,
        image_bytes: bytes,
        wait_for_build: bool = True,
    ) -> str:
        """获取图片描述文本。"""


@runtime_checkable
class AgentConfigProvider(Protocol):
    """智能体配置查询接口 — 核心通过此接口访问智能体配置，不直接依赖 AgentConfigRegistry。"""

    def get_agent(self, agent_id: str) -> AgentConfig:
        """获取指定智能体配置。"""
        ...

    def list_agents(self) -> list[AgentConfig]:
        """返回所有已加载智能体配置列表。"""
        ...

    def get_default_agent(self) -> AgentConfig:
        """返回默认智能体配置。"""
        ...

    def has_agent(self, agent_id: str) -> bool:
        """检查智能体是否存在。"""
        ...

    def reload(self) -> None:
        """全量重载所有智能体配置。"""
        ...

    def reload_agent(self, agent_id: str) -> bool:
        """重载指定智能体配置，不存在或失败返回 False。"""
        ...

    def load(self) -> None:
        """懒加载：首次查询时自动触发。"""
        ...


@runtime_checkable
class LLMService(Protocol):
    """LLM 服务接口 — 核心层和组件层通过此接口访问 LLM 能力，不直接依赖 LLMServiceClient。"""

    async def generate_response(
        self,
        task_name: str,
        prompt: str,
        options: LLMGenerationOptions | None = None,
        *,
        request_type: str = "",
        session_id: str = "",
    ) -> LLMResponseResult:
        """文本生成（单轮）。"""
        ...

    async def generate_response_with_messages(
        self,
        task_name: str,
        message_factory: MessageFactory,
        options: LLMGenerationOptions | None = None,
        *,
        request_type: str = "",
        session_id: str = "",
    ) -> LLMResponseResult:
        """文本生成（消息工厂）。"""
        ...

    async def generate_response_for_image(
        self,
        task_name: str,
        prompt: str,
        image_base64: str,
        image_format: str,
        options: LLMImageOptions | None = None,
        *,
        request_type: str = "",
        session_id: str = "",
    ) -> LLMResponseResult:
        """图像理解。"""
        ...

    async def transcribe_audio(
        self,
        task_name: str,
        voice_base64: str,
        *,
        request_type: str = "",
        session_id: str = "",
    ) -> LLMAudioTranscriptionResult:
        """音频转写。"""
        ...


@runtime_checkable
class PersonInfoPort(Protocol):
    """人物信息查询接口 — 核心通过此接口查询人物信息，不直接依赖 Person 类。"""

    def get_person_info(self, platform: str, user_id: str) -> Optional[PersonInfoResult]:
        """查询人物信息。"""
        ...

    def get_person_id(self, platform: str, user_id: str) -> str:
        """根据平台和用户ID获取 person_id（纯 MD5 哈希计算）。"""
        ...

    def get_person_id_by_name(self, person_name: str) -> str:
        """根据用户名获取 person_id（查数据库）。"""
        ...

    def get_person_attribute(self, person_id: str, field_name: str) -> Any:
        """根据 person_id 获取人物属性值。"""
        ...

    def get_person_detail(self, person_id: str) -> Optional[PersonDetailSnapshot]:
        """根据 person_id 获取人物详情快照。"""
        ...

    async def store_person_memory(
        self,
        person_name: str,
        fact: str,
        session_id: str,
        *,
        person_id: str = "",
        evidence_source: str = "user_supported",
        evidence_message_ids: list[str] | None = None,
    ) -> None:
        """写回人物事实记忆。"""
        ...


@runtime_checkable
class BotConfigPort(Protocol):
    """Bot 配置查询接口 — 替代 global_config.bot 直接访问。"""

    def get_bot_nickname(self) -> str: ...
    def get_bot_alias_names(self) -> list[str]: ...
    def get_bot_platform(self) -> str: ...
    def get_bot_primary_account(self) -> str: ...
    def get_bot_qq_account(self, platform: str) -> str: ...
    def get_bot_platforms(self) -> list[str]: ...
    def get_bot_owner_user_ids(self) -> list[str]: ...


@runtime_checkable
class ChatConfigPort(Protocol):
    """聊天配置查询接口 — 替代 global_config.chat 直接访问。"""

    def get_personality(self) -> str: ...
    def get_reply_style(self) -> ReplyStyleSnapshot: ...
    def get_reply_style_text(self) -> str: ...
    def get_multiple_reply_style(self) -> list[str]: ...
    def get_multiple_reply_probability(self) -> float: ...
    def get_max_context_size(self) -> int: ...
    def get_max_private_context_size(self) -> int: ...
    def get_self_message_special_mark(self) -> str: ...
    def get_mid_term_memory_config(self) -> dict[str, Any]: ...
    def get_reply_timing_config(self) -> ReplyTimingSnapshot: ...
    def get_keyword_reaction(self) -> KeywordReactionSnapshot: ...

    def get_reply_style_chat_prompts(self) -> list[str]:
        """获取聊天风格 prompts 列表。"""
        ...

    def get_reply_timing_talk_value(self) -> float:
        """获取群聊默认发言频率。"""
        ...

    def get_reply_timing_private_talk_value(self) -> float:
        """获取私聊默认发言频率。"""
        ...


@runtime_checkable
class AppConfigPort(Protocol):
    """应用配置查询接口 — 按配置域分组。

    === Expression 域 ===
    === Emoji 域 ===
    === Experimental 域 ===
    === Visual 域 ===
    === Debug 域 ===
    === Agent Autonomy 域 ===
    === A_Memorix 域 ===
    === MCP 域 ===
    === Plugin Runtime 域 ===
    === Response Splitter 域 ===
    === Chinese Typo 域 ===
    === Response Post Process 域 ===
    === Log 域 ===
    === WebUI 域 ===
    === Agent 域 ===
    === Agent Interaction 域 ===
    === Voice 域 ===
    === MaimMessage 域 ===
    === Plugin Runtime V2 域 ===
    === Telemetry 域 ===
    === Message Receive 域 ===
    === Chat 域 ===
    === Jargon 域 ===
    === System 域 ===
    """

    def get_expression_learning_list(self) -> list[str]: ...
    def get_expression_checked_only(self) -> bool: ...
    def get_expression_vector_candidate_pool_size(self) -> int: ...
    def get_emoji_max_reg_num(self) -> int: ...
    def get_emoji_max_size_mb(self) -> float: ...
    def get_emoji_do_replace(self) -> bool: ...
    def get_emoji_check_interval(self) -> int: ...
    def get_emoji_steal_emoji(self) -> bool: ...
    def get_emoji_content_filtration(self) -> bool: ...
    def get_experimental_behavior_learning_list(self) -> list[str]: ...
    def get_experimental_behavior_groups(self) -> list[str]: ...
    def get_experimental_enable_rich_reply(self) -> bool: ...

    def get_experimental_enable_behavior_learning(self) -> bool: ...
    def get_visual_max_image_num(self) -> int: ...
    def get_visual_replyer_mode(self) -> str: ...
    def get_debug_show_maisaka_thinking(self) -> bool: ...
    def get_debug_show_jargon_prompt(self) -> bool: ...
    def get_agent_autonomy_config(self) -> AgentAutonomySnapshot: ...
    def get_a_memorix_integration_config(self) -> AMemorixIntegrationSnapshot: ...
    def get_emoji_send_num(self) -> int: ...
    def get_mcp_enable(self) -> bool: ...
    def get_mcp_sampling_task_name(self) -> str: ...
    def get_response_splitter_enable(self) -> bool: ...
    def get_response_splitter_max_length(self) -> int: ...
    def get_response_splitter_max_sentence_num(self) -> int: ...
    def get_response_splitter_max_split_num(self) -> int: ...
    def get_response_splitter_enable_kaomoji_protection(self) -> bool: ...
    def get_response_splitter_enable_overflow_return_all(self) -> bool: ...
    def get_chinese_typo_enable(self) -> bool: ...
    def get_chinese_typo_error_rate(self) -> float: ...
    def get_chinese_typo_min_freq(self) -> int: ...
    def get_chinese_typo_tone_error_rate(self) -> float: ...
    def get_chinese_typo_word_replace_rate(self) -> float: ...
    def get_response_post_process_enable(self) -> bool: ...
    def get_response_post_process_typing_speed(self) -> float: ...
    def get_log_maisaka_prompt_preview_limit(self) -> int: ...
    def get_log_maisaka_reply_effect_limit(self) -> int: ...
    def get_webui_host(self) -> str: ...
    def get_webui_port(self) -> int: ...
    def get_default_agent_id(self) -> str: ...
    def get_agents_dir(self) -> str: ...
    def get_agent_interaction_config(self) -> AgentInteractionSnapshot: ...
    def get_debug_enable_reply_effect_tracking(self) -> bool: ...
    def get_debug_record_tool_structured_content(self) -> bool: ...
    def get_debug_keep_prompt_preview_json_base64(self) -> bool: ...
    def get_debug_enable_llm_cache_stats(self) -> bool: ...
    def get_log_llm_request_snapshot_limit(self) -> int: ...
    def get_voice_enable_asr(self) -> bool: ...
    def get_maim_message_enable_api_server(self) -> bool: ...
    def get_plugin_runtime_hook_blocking_timeout_sec(self) -> float: ...

    def get_plugin_runtime_v2_enabled(self) -> bool: ...
    def get_plugin_runtime_v2_host_listen_address(self) -> str: ...
    def get_plugin_runtime_v2_runner_spawn_count(self) -> int: ...
    def get_plugin_runtime_v2_runner_spawn_timeout_sec(self) -> float: ...
    def get_plugin_runtime_v2_health_check_interval_sec(self) -> float: ...
    def get_plugin_runtime_v2_max_restart_attempts(self) -> int: ...
    def get_plugin_runtime_v2_scope_approval_file(self) -> str: ...
    def get_plugin_runtime_v2_default_rpm(self) -> int: ...
    def get_telemetry_enable(self) -> bool: ...
    def get_message_receive_ban_words(self) -> list[str]: ...
    def get_message_receive_ban_msgs_regex(self) -> list[str]: ...
    def get_a_memorix_shared_memory_groups(self) -> list[str]: ...
    def get_visual_handle_oversized_images(self) -> bool: ...
    def get_visual_max_image_size_mb(self) -> float: ...
    def get_visual_oversized_image_handle_method(self) -> str: ...
    def get_visual_planner_mode(self) -> str: ...
    def get_visual_image_cache_cleanup_enabled(self) -> bool: ...
    def get_emoji_cache_cleanup_enabled(self) -> bool: ...
    def get_experimental_focus_mode(self) -> bool: ...
    def get_experimental_focus_on_private(self) -> bool: ...
    def get_experimental_focus_chat_whitelist(self) -> list[str]: ...
    def get_experimental_focus_cool_time(self) -> float: ...
    def get_experimental_focus_groups(self) -> list[str]: ...
    def get_chat_mid_term_memory(self) -> bool: ...
    def get_expression_max_expression_learner(self) -> int: ...
    def get_expression_self_reflect(self) -> bool: ...
    def get_expression_selection_mode(self) -> str: ...
    def get_expression_vector_index_path(self) -> str: ...
    def get_expression_groups(self) -> list[Any]: ...
    def get_webui_enforce_public_outbound_url(self) -> bool: ...
    def get_webui_anti_crawler_mode(self) -> str: ...
    def get_webui_allowed_ips(self) -> str: ...
    def get_webui_trusted_proxies(self) -> str: ...
    def get_webui_trust_xff(self) -> bool: ...
    def get_webui_secure_cookie(self) -> bool: ...
    def get_webui_mode(self) -> str: ...

    def get_mmc_version(self) -> str:
        """获取 MMC 版本号常量。"""
        ...

    def get_emoji_cache_cleanup_config(self) -> CacheCleanupConfig:
        """获取表情包缓存清理配置快照。"""
        ...

    def get_image_cache_cleanup_config(self) -> CacheCleanupConfig:
        """获取图片缓存清理配置快照。"""
        ...

    def get_maim_message_config(self) -> MaimMessageConfigSnapshot:
        """获取 MaimMessage 配置快照。"""
        ...

    async def reload_config(self, changed_scopes: tuple[str, ...] = ()) -> bool:
        """热重载配置。适配器委托 config_manager.reload_config()。"""
        ...

    def get_jargon_learning_list(self) -> list[str]:
        """获取行话学习列表。"""
        ...

    def get_jargon_groups(self) -> list[Any]:
        """获取行话分组列表。"""
        ...

    def get_plugin_runtime_config(self) -> PluginRuntimeSnapshot:
        """获取插件运行时配置快照。

        Returns:
            PluginRuntimeSnapshot 不可变快照
        """
        ...

    def get_plugin_runtime_render_config(self) -> PluginRuntimeRenderSnapshot:
        """获取插件运行时浏览器渲染配置快照。

        Returns:
            PluginRuntimeRenderSnapshot 不可变快照
        """
        ...

    def register_reload_callback(self, callback: object) -> None:
        """注册全局配置热重载回调。

        适配器委托 config_manager.register_reload_callback()。
        """
        ...

    def unregister_reload_callback(self, callback: object) -> None:
        """注销全局配置热重载回调。

        适配器委托 config_manager.unregister_reload_callback()。
        """
        ...

    def get_global_config_json(self) -> str:
        """获取全局配置的 JSON 序列化字符串。

        Returns:
            config_manager.get_global_config().model_dump(mode="json") 的结果
        """
        ...

    def get_model_config_json(self) -> str:
        """获取模型配置的 JSON 序列化字符串。

        Returns:
            config_manager.get_model_config().model_dump(mode="json") 的结果
        """
        ...


@runtime_checkable
class AutonomyEventBusPort(Protocol):
    """智能体自主性事件总线接口 — 替代 AutonomyEventBus.get_instance() 单例。"""

    def subscribe(self, event_type: str, handler: Any) -> None: ...
    def unsubscribe(self, event_type: str, handler: Any) -> None: ...
    async def emit(self, event_type: str, data: dict[str, Any]) -> None: ...
    def emit_sync(self, event_type: str, data: dict[str, Any]) -> None: ...
