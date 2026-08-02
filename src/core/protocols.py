"""核心接口契约 — 组件兼容核心，核心定义接口，组件实现接口。

本模块定义所有核心 Protocol，核心模块只依赖这些 Protocol，
不直接导入组件具体类（chat_manager、HeartflowManager 等）。

适配器层（src/core/adapters/）是唯一允许导入组件具体类的地方。
"""


import asyncio

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

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
    from src.core.service_manager.types import (
        AdoptionResult,
        DependencyRelation,
        FaultRecord,
        HealthCheckResult,
        LifecycleActionResult,
        ServiceDescriptor,
        ServiceState,
        ServiceStateSnapshot,
        SystemHealthView,
    )
    from src.core.startup.types import CoreReadiness, StartupResult
    from src.core.control_message.types import (
        ControlMessage,
        ControlMessageDeliveryResult,
        ControlMessageEffectiveMask,
        ControlMessageKind,
        ControlMessagePendingView,
        DeliveryDecisionRecord,
        FatalDiffuseRecord,
        MaskOperation,
        MaskScope,
        UnkillableDeclaration,
    )
    from src.core.resource_limit.types import (
        ChargeResult,
        OOMDecision,
        OOMDecisionRecord,
        PressureHistoryEntry,
        PressureLevel,
        ResourceDimension,
        ResourceLimitConfigData,
        ResourceTreeView,
        ResourceUsageSnapshot,
    )
    from src.core.watchdog.config import WatchdogConfig
    from src.core.watchdog.types import RunnerBridgeStatus, WatchdogStatus
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
    === Message Receive 域 ===
    === Chat 域 ===
    === Jargon 域 ===
    === Watchdog 域 ===
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
    def get_experimental_enable_rich_reply(self) -> bool: ...

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

    def get_watchdog_config(self) -> WatchdogConfig:
        """获取看门狗配置快照（事件循环阻塞检测 + Runner 健康桥接）。

        Returns:
            WatchdogConfig 不可变快照（8 项，来自配置文件 [watchdog] 域）
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

    # === Resource Limit 域 ===

    def get_resource_limit_global_enabled(self) -> bool:
        """资源限制全局开关（默认 false，渐进启用）。"""
        ...

    def get_resource_limit_plugin_config(
        self, plugin_id: str
    ) -> Optional["ResourceLimitConfigData"]:
        """获取插件资源配置（四档阈值 + oom_group + events_local）。"""
        ...

    def get_resource_limit_pressure_window_size(self) -> int:
        """压力检测窗口大小（默认 512）。"""
        ...

    def get_resource_limit_oom_lock_timeout(self) -> float:
        """OOM 锁超时秒数（默认 5.0）。"""
        ...

    def get_resource_limit_event_dedup_window_ms(self) -> int:
        """事件去重窗口毫秒（默认 1000）。"""
        ...

    def get_resource_limit_event_max_depth(self) -> int:
        """事件传播最大深度（默认 32）。"""
        ...


@runtime_checkable
class AutonomyEventBusPort(Protocol):
    """智能体自主性事件总线接口 — 替代 AutonomyEventBus.get_instance() 单例。"""

    def subscribe(self, event_type: str, handler: Any) -> None: ...
    def unsubscribe(self, event_type: str, handler: Any) -> None: ...
    async def emit(self, event_type: str, data: dict[str, Any]) -> None: ...
    def emit_sync(self, event_type: str, data: dict[str, Any]) -> None: ...


@runtime_checkable
class ServiceManagerPort(Protocol):
    """服务管理器接口 — 运行时组件生命周期管理、健康检查、故障恢复、状态聚合。

    核心通过此接口管理组件运行时状态，不直接依赖具体实现。
    适配器层（ServiceManagerAdapter）是唯一允许导入具体引擎类的地方。
    """

    async def adopt_from_startup(
        self,
        result: "StartupResult",
        descriptors: dict[str, "ServiceDescriptor"],
        dependencies: list["DependencyRelation"] = (),
    ) -> "AdoptionResult":
        """从 StartupOrchestrator 结果接管组件。

        前置条件：仅在 StartupOrchestrator.run() 返回后调用一次。
        后置条件：全部 status=success 组件状态为"运行中"。
        """

    async def stop(
        self, component_id: str, *, force: bool = False, confirmed: bool = False
    ) -> "LifecycleActionResult":
        """停止组件（级联停止依赖方，核心就绪贡献组件需 confirmed）。

        后置条件：组件及强依赖方状态为"已停止"，弱依赖方状态为"降级"。
        """

    async def start(self, component_id: str) -> "LifecycleActionResult":
        """启动组件（校验依赖就绪，未就绪拒绝）。

        后置条件：组件状态为"运行中"或"降级"（依赖缺失时）。
        """

    async def restart(self, component_id: str, *, confirmed: bool = False) -> "LifecycleActionResult":
        """重启组件（停止后启动，限时 30s）。"""

    def get_state(self, component_id: str) -> Optional["ServiceStateSnapshot"]:
        """查询单个组件状态（内存，≤100ms）。"""

    def list_states(
        self, *, filter_state: Optional["ServiceState"] = None
    ) -> list["ServiceStateSnapshot"]:
        """查询全部组件状态，可按状态过滤。"""

    def get_system_health_view(self) -> "SystemHealthView":
        """查询系统健康视图（内存聚合，≤100ms，无 I/O）。"""

    def get_fault_history(
        self, component_id: str, *, limit: int = 100
    ) -> list["FaultRecord"]:
        """查询组件故障历史（环形缓冲，最近 limit 条）。"""

    async def report_heartbeat(self, component_id: str, timestamp: float) -> None:
        """接收组件心跳上报（被动心跳模式）。"""

    async def report_external_fault(
        self, component_id: str, reason: str, detail: str = ""
    ) -> None:
        """接收外部故障事件（ZG-3 看门狗等上报）。"""

    def subscribe_health_change(self, callback: Callable[["SystemHealthView"], None]) -> None:
        """订阅系统健康等级变更事件。"""

    def unsubscribe_health_change(self, callback: Callable[["SystemHealthView"], None]) -> None:
        """取消订阅。"""


@runtime_checkable
class CoreReadinessPort(Protocol):
    """运行时核心就绪判定接口 — 复用 CoreReadiness 三标志语义，持续更新。

    CoreReadinessPortAdapter 是 CoreReadiness 的运行时权威源——
    update_flag() 优先于 StartupOrchestrator._update_core_readiness() 的初始设定。
    """

    def get_core_readiness(self) -> "CoreReadiness":
        """查询核心就绪三标志快照。"""

    def is_core_ready(self) -> bool:
        """查询核心是否就绪（三标志与运算）。"""

    def update_flag(self, flag_name: str, value: bool) -> None:
        """更新单个就绪标志（组件状态变更时由 StateAggregator 调用）。

        Args:
            flag_name: message_pipeline_ready / agent_thinking_ready / reply_capability_ready
            value: 就绪状态

        Raises:
            ValueError: flag_name 不为三标志之一
        """


@runtime_checkable
class HealthProbePort(Protocol):
    """受管组件存活探针契约 — 组件实现此接口供管理器主动探测。"""

    async def health_probe(self) -> "HealthCheckResult":
        """存活探针，管理器调用以判定组件是否存活。

        Returns:
            HealthCheckResult，实现应快速返回（≤5s），超时由管理器判定
        """


@runtime_checkable
class WatchdogPort(Protocol):
    """看门狗接口 — 事件循环阻塞检测与 Runner 健康结果桥接上报。

    核心通过此接口管理看门狗生命周期、刷新存活信号、查询检测状态、
    订阅状态变更、注册/取消注册 Runner 桥接源。
    适配器层（WatchdogAdapter）是唯一允许导入具体引擎类的地方。
    """

    async def start(self, main_loop: asyncio.AbstractEventLoop) -> None:
        """启动看门狗：启动检测线程 + 桥接轮询。

        前置条件：ServiceManagerPort 已注册（上报目标就绪）。
        后置条件：检测线程运行、桥接轮询运行。

        Raises:
            ServiceManagerPortNotReadyError: ServiceManagerPort 未注册
            WatchdogAlreadyRunningError: 看门狗已在运行
        """

    async def stop(self) -> None:
        """停止看门狗：停止检测线程 + 桥接轮询。

        后置条件：全部检测任务停止，状态保留供最后查询。
        """

    def touch(self, delay: bool = False) -> None:
        """刷新事件循环存活时间戳（由主事件循环内协程周期调用）。

        Args:
            delay: 是否标记延迟报告（ZG-3 补强 S1，对标 Linux
                SOFTLOCKUP_DELAY_REPORT）。True 时下一检测周期跳过严重阻塞
                上报，但仍刷新时间戳。默认 False（向后兼容）。

        后置条件：last_touch 更新为 time.monotonic()。
        """

    def get_status(self) -> "WatchdogStatus":
        """查询事件循环检测状态快照（内存，无 I/O）。

        Returns:
            WatchdogStatus 不可变快照
        """

    def get_runner_bridge_status(self, runner_id: str) -> Optional["RunnerBridgeStatus"]:
        """查询单个 Runner 桥接状态快照。

        Args:
            runner_id: Runner 标识

        Returns:
            RunnerBridgeStatus 快照，未注册时返回 None
        """

    def list_runner_bridge_status(self) -> list["RunnerBridgeStatus"]:
        """查询全部 Runner 桥接状态快照。

        Returns:
            RunnerBridgeStatus 列表
        """

    def subscribe_status_change(self, callback: Callable[["WatchdogStatus"], None]) -> None:
        """订阅检测状态变更事件（供 WebUI 内省）。

        Args:
            callback: 状态变更回调函数
        """

    def unsubscribe_status_change(self, callback: Callable[["WatchdogStatus"], None]) -> None:
        """取消订阅。

        Args:
            callback: 先前注册过的回调函数
        """

    def register_v2_supervisor(
        self,
        runner_id: str,
        supervisor: Any,
        heartbeat_manager: Any,
        component_id: str = "",
    ) -> None:
        """注册 V2 RunnerSupervisor + HeartbeatManager 供桥接订阅。

        前置条件：supervisor 提供 get_health_status() 方法。
        后置条件：桥接方订阅其 timeout_callback + 定时轮询 get_health_status。

        Args:
            runner_id: Runner 标识
            supervisor: V2 RunnerSupervisor 实例
            heartbeat_manager: HeartbeatManager 实例
            component_id: ZG-1 受管组件标识，空时用 runner_id

        Raises:
            ValueError: supervisor 不提供 get_health_status() 方法
        """

    def register_v1_supervisor(
        self,
        runner_id: str,
        supervisor: Any,
        component_id: str = "",
    ) -> None:
        """注册 V1 PluginRunnerSupervisor 供旁路轮询。

        前置条件：supervisor 持有 _runner_process 和 _restart_count 属性。
        后置条件：桥接方定时轮询其进程存活 + 重启计数 diff。

        Args:
            runner_id: Runner 标识
            supervisor: V1 PluginRunnerSupervisor 实例
            component_id: ZG-1 受管组件标识，空时用 runner_id

        Raises:
            ValueError: supervisor 不持有 _runner_process 或 _restart_count 属性
        """

    def unregister_runner(self, runner_id: str) -> None:
        """取消注册 Runner（停止对该 Runner 的桥接）。

        Args:
            runner_id: Runner 标识

        Raises:
            UnknownRunnerError: runner_id 未注册
        """

    def list_blocked_runners(self) -> list["RunnerBridgeStatus"]:
        """查询当前所有阻塞 Runner（ZG-5 OOM 受害者选择消费）。

        判定条件：cooldown_until > now。

        Returns:
            阻塞中的 RunnerBridgeStatus 列表
        """


@runtime_checkable
class ResourceLimitPort(Protocol):
    """资源限制接口 — 插件资源计量、四档限制、压力分级、OOM 处理、事件传播。

    核心通过此接口管理插件资源，不直接依赖具体实现。
    适配器层（ResourceLimitAdapter）是唯一允许导入资源限制引擎类的地方。

    对标 Linux cgroup memory controller v2 + vmpressure + OOM killer。
    """

    def charge(
        self, plugin_id: str, dimension: "ResourceDimension", amount: int
    ) -> "ChargeResult":
        """投机充值（同步，热路径纯内存无 I/O）。

        沿父链逐级投机累加，任一级超该级 max 则回滚已充级别。

        Args:
            plugin_id: 插件标识
            dimension: 资源维度
            amount: 充值量（正整数）

        Returns:
            ChargeResult，accepted=True 时父链已全部累加

        Raises:
            KeyError: plugin_id 未注册
            ValueError: dimension 非法或 amount 非正
        """

    def uncharge(
        self, plugin_id: str, dimension: "ResourceDimension", amount: int
    ) -> None:
        """递减计量（同步，热路径纯内存无 I/O）。

        沿父链向上递减，用 max(0, current - amount) 保证非负。

        Args:
            plugin_id: 插件标识
            dimension: 资源维度
            amount: 递减量（正整数）
        """

    def get_usage_snapshot(
        self, plugin_id: str
    ) -> Optional["ResourceUsageSnapshot"]:
        """查询单插件资源计量快照（同步，内存）。"""

    async def register_plugin(
        self, plugin_id: str, parent_id: Optional[str] = None
    ) -> None:
        """注册插件到资源计量树。

        Args:
            plugin_id: 插件标识
            parent_id: 父插件标识，None 则挂根
        """

    async def unregister_plugin(self, plugin_id: str) -> None:
        """注销插件，孤儿子节点挂根。"""

    async def reload_config(self) -> None:
        """热更新配置，≤5s 生效。"""

    def record_pressure_sample(
        self, scanned: int, reclaimed: int, scan_priority: int = 12
    ) -> Optional["PressureLevel"]:
        """记录压力采样（同步，热路径）。

        窗口累计 + 三重判定（窗口累计 + 比率算法 + 优先级兜底）。
        等级变更时通过 emit_sync 发布 resource.pressure.{level} 事件。

        Args:
            scanned: 窗口内请求量增量（charge 拒绝时 +1）
            reclaimed: 窗口内成功量增量（charge 成功时 +1）
            scan_priority: 扫描优先级，≤3 强制 CRITICAL

        Returns:
            等级变更时返回新等级，未变更或窗口未满时返回 None
        """

    async def trigger_oom(
        self,
        trigger_plugin_id: str,
        dimension: "ResourceDimension",
        usage: int,
        limit: int,
    ) -> Optional["OOMDecision"]:
        """触发 OOM 处理（单锁串行 + 异步处置）。

        Args:
            trigger_plugin_id: 触发插件标识
            dimension: 触发维度
            usage: 触发时用量
            limit: 触发时限值

        Returns:
            OOMDecision，无可用受害者时返回 None
        """

    def get_resource_tree_view(self) -> "ResourceTreeView":
        """查询资源计量树全貌快照（内存，≤100ms）。"""

    def get_pressure_history(
        self, limit: int = 100
    ) -> list["PressureHistoryEntry"]:
        """查询压力等级历史（环形缓冲，最近 limit 条）。"""

    def get_oom_history(
        self, limit: int = 100
    ) -> list["OOMDecisionRecord"]:
        """查询 OOM 决策历史（环形缓冲，最近 limit 条）。"""


@runtime_checkable
class ControlMessagePort(Protocol):
    """控制消息优先级接口 — 控制消息的优先级投递、屏蔽、UNKILLABLE 保护、force 强制投递。

    核心通过此接口管理控制消息优先级，不直接依赖 ZG-8 具体实现。
    适配器层（ControlMessageAdapter）是唯一允许导入控制消息引擎类的地方。

    对标 Linux 内核信号机制（signal.c）：带优先级、可屏蔽、有不可捕获特权通道的事件投递系统。

    接口分类：
    - 投递类（热路径）：send / force_send / dequeue_next
    - 屏蔽管理类：set_blocked / set_ignored / get_effective_mask
    - UNKILLABLE 管理类：declare_unkillable / clear_unkillable / list_unkillable_entities
    - 会话生命周期类：on_session_created / on_session_destroyed
    - 内省查询类：get_pending_view / get_delivery_history / get_diffuse_history
    """

    # === 投递类（热路径）===

    async def send(
        self,
        kind: "ControlMessageKind",
        payload: dict[str, Any],
        target_session_id: str = "",
        target_entity: str = "",
        source: str = "",
        trace_id: str = "",
    ) -> "ControlMessageDeliveryResult":
        """投递控制消息（非 force，走完整优先级链）。

        前置：kind 在 1-16 范围内（越界抛 ValueError）；target_session_id 非空时
        会话必须存在（不存在返回 TARGET_GONE）。
        后置：被忽略的消息不入队（REJECTED_IGNORED）；被 UNKILLABLE 保护拒绝
        （REJECTED_UNKILLABLE）；其余入队（QUEUED），类别为致命时触发异步扩散。

        Args:
            kind: 控制消息类别
            payload: 类别特定数据（如 error 描述、配置路径）
            target_session_id: 目标会话 ID，空表示系统级
            target_entity: 目标实体标识，如 "agent:primary"、"component:orchestrator"
            source: 投递来源标识，如 "watchdog"、"service_manager"、"webui"
            trace_id: 链路追踪 ID

        Returns:
            投递结果（已入队/被忽略/被保护拒绝/目标不存在）

        Raises:
            ValueError: kind 编号越界（CONTROL_KIND_UNKNOWN）
        """

    async def force_send(
        self,
        kind: "ControlMessageKind",
        target_session_id: str = "",
        target_entity: str = "",
        reason: str = "",
        caller: str = "",
    ) -> "ControlMessageDeliveryResult":
        """force 强制投递（绕过屏蔽/忽略/UNKILLABLE 保护）。

        前置：caller 必须在 force_caller_whitelist 中（系统核心层）；
        kind 必须为系统级强制类别（编号 1-3）。
        后置：清除目标该类别屏蔽/忽略位与 UNKILLABLE 标志（若为致命），
        直接入队并记录审计。

        Args:
            kind: 控制消息类别（必须 1-3）
            target_session_id: 目标会话 ID
            target_entity: 目标实体标识
            reason: 强制投递原因（审计）
            caller: 调用方标识（白名单校验）

        Returns:
            投递结果（FORCE_DELIVERED / 权限拒绝 / 类别非法 / 目标不存在）

        Raises:
            ValueError: kind 编号越界或非系统级强制类别
        """

    def dequeue_next(self, session_id: str) -> Optional["ControlMessage"]:
        """出队下一个可投递控制消息（同步，热路径）。

        前置：无。后置：按固定优先级链（系统级强制 → 引擎致命 → 会话控制 →
        调试 → 普通 → 实时）先私后共出队；无可投递消息返回 None（放行用户消息）。
        被屏蔽/忽略的消息不出队，留在 pending 队列。

        Args:
            session_id: 出队会话 ID

        Returns:
            ControlMessage，无可投递控制消息时返回 None
        """

    # === 屏蔽管理类 ===

    async def set_blocked(
        self,
        how: "MaskOperation",
        kinds: set["ControlMessageKind"],
        scope: "MaskScope",
        session_id: str = "",
    ) -> set["ControlMessageKind"]:
        """设置屏蔽集（BLOCK 并集 / UNBLOCK 差集 / SETMASK 直接设置）。

        前置：scope=SESSION 时 session_id 必填。
        后置：不可屏蔽类别（编号 1-3）被强制剔除（第一道防线）；
        返回操作后的屏蔽集。屏蔽 ≠ 丢弃：被屏蔽消息留 pending 队列。

        Args:
            how: 操作类型
            kinds: 涉及的类别集合
            scope: 作用域（SYSTEM 全局 / SESSION 会话级）
            session_id: 会话 ID（SESSION 作用域必填）

        Returns:
            操作后该作用域屏蔽集

        Raises:
            ValueError: SESSION 作用域缺 session_id
        """

    async def set_ignored(
        self,
        kinds: set["ControlMessageKind"],
        scope: "MaskScope",
        session_id: str = "",
    ) -> set["ControlMessageKind"]:
        """设置忽略集（覆盖式）。

        前置：scope=SESSION 时 session_id 必填。
        后置：不可屏蔽类别（编号 1-3）被强制剔除（第二道防线拒绝）；
        被忽略类别的消息直接丢弃不入队（忽略 = 永久丢弃）。

        Args:
            kinds: 涉及的类别集合
            scope: 作用域
            session_id: 会话 ID（SESSION 作用域必填）

        Returns:
            操作后该作用域忽略集

        Raises:
            ValueError: SESSION 作用域缺 session_id
        """

    def get_effective_mask(
        self, session_id: str
    ) -> "ControlMessageEffectiveMask":
        """查询有效屏蔽集（系统级 ∪ 会话级，同步）。

        Args:
            session_id: 会话 ID

        Returns:
            有效屏蔽/忽略位图快照（不可变）
        """

    # === UNKILLABLE 管理类 ===

    async def declare_unkillable(
        self, entity_id: str, entity_type: str = "agent"
    ) -> None:
        """声明实体为 UNKILLABLE（受保护，不可被普通致命控制消息淘汰）。

        前置：仅 Orchestrator 调用（约定受信，组件不可自行声明）。
        后置：实体保护标志置位；force 通道可清除（软保护，ADR-05）。

        Args:
            entity_id: 实体标识，如 "agent:primary"、"component:orchestrator"
            entity_type: 实体类型（agent / component）

        Raises:
            ValueError: entity_id 已声明
        """

    async def clear_unkillable(self, entity_id: str) -> None:
        """清除实体的 UNKILLABLE 标志（force 通道使用）。

        后置：声明保留（is_active=False，审计记录不销毁）。
        """

    def list_unkillable_entities(self) -> list["UnkillableDeclaration"]:
        """查询全部 UNKILLABLE 声明（同步，含已清除的审计记录）。"""

    # === 会话生命周期类 ===

    async def on_session_created(self, session_id: str) -> None:
        """会话创建通知：创建该会话的私有 pending 队列。

        后置：定向控制消息可入私有队列；内存不足时降级共享队列。
        """

    async def on_session_destroyed(self, session_id: str) -> None:
        """会话销毁通知：清理私有 pending 队列并触发致命扩散。

        后置：私有队列节点清零（防内存泄漏）；向关联异步任务扩散取消信号。
        """

    # === 内省查询类（WebUI）===

    def get_pending_view(
        self, session_id: str = ""
    ) -> "ControlMessagePendingView":
        """查询待处理队列快照（同步；session_id 空时查询共享队列）。

        Args:
            session_id: 会话 ID，空表示系统共享队列

        Returns:
            pending 队列快照（节点元组 + 类别位图 + 节点数）
        """

    def get_delivery_history(
        self, limit: int = 100
    ) -> list["DeliveryDecisionRecord"]:
        """查询投递决策历史（环形缓冲，最近 limit 条，同步）。"""

    def get_diffuse_history(
        self, limit: int = 100
    ) -> list["FatalDiffuseRecord"]:
        """查询致命扩散历史（环形缓冲，最近 limit 条，同步）。"""
