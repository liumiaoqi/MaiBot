"""核心接口契约 — 组件兼容核心，核心定义接口，组件实现接口。

本模块定义所有核心 Protocol，核心模块只依赖这些 Protocol，
不直接导入组件具体类（chat_manager、HeartflowManager 等）。

适配器层（src/core/adapters/）是唯一允许导入组件具体类的地方。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from typing import Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.core.types import AgentConfig, MemorySearchResult, MemoryWriteResult, NoticeKind, SendMessageResult, SessionInfo, ThinkContext, ThinkResult


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
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """触发主动对话任务（仅用于插件主动对话，禁止用于多智能体插话）。

        Args:
            plugin_id: 触发来源标识
            intent: 触发意图描述
            reason: 触发原因
            metadata: 附加元数据

        Returns:
            任务执行结果，失败时返回 None
        """

    async def start(self) -> None:
        """启动运行时。"""

    async def stop(self) -> None:
        """停止运行时。"""


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

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        mode: str = "search",
        chat_id: str = "",
        person_id: str = "",
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

    async def get_person_profile(self, person_id: str, *, limit: int = 4) -> Optional[dict[str, Any]]:
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

    async def ingest_text(
        self,
        *,
        external_id: str,
        source_type: str,
        text: str,
        chat_id: str = "",
        person_ids: Optional[list[str]] = None,
        participants: Optional[list[str]] = None,
        timestamp: Optional[float] = None,
        time_start: Optional[float] = None,
        time_end: Optional[float] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        entities: Optional[list[str]] = None,
        relations: Optional[list[dict[str, Any]]] = None,
        respect_filter: bool = True,
        user_id: str = "",
        group_id: str = "",
    ) -> MemoryWriteResult:
        """摄入文本到记忆系统。

        Args:
            external_id: 外部标识 ID
            source_type: 来源类型
            text: 文本内容
            chat_id: 聊天流 ID
            person_ids: 关联人物 ID 列表
            participants: 参与者列表
            timestamp: 时间戳
            time_start: 时间范围起点
            time_end: 时间范围终点
            tags: 标签列表
            metadata: 元数据字典
            entities: 实体列表
            relations: 关系列表
            respect_filter: 是否遵守过滤规则
            user_id: 用户 ID
            group_id: 群组 ID

        Returns:
            MemoryWriteResult 写入结果
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
class MessagePort(Protocol):
    """核心消息端口协议 — 组件实现此接口。

    send: 核心 → 外部（回复、提醒、插话、主动发言）
    核心模块（管家、提醒、Orchestrator）只通过此接口发消息，
    不直接依赖 send_service / chat_manager / NapCat。
    """

    async def send(
        self,
        session_id: str,
        text: str,
        *,
        agent_id: str = "",
        source: str = "core",
    ) -> bool:
        """向指定会话发送文本消息。

        Args:
            session_id: 目标会话 ID
            text: 消息文本
            agent_id: 发言智能体 ID（用于日志和路由）
            source: 消息来源标识（reply/interjection/reminder/proactive）

        Returns:
            是否发送成功
        """

    async def send_reply(
        self,
        session_id: str,
        text: str,
        *,
        reply_to: str,
        agent_id: str = "",
        source: str = "core",
    ) -> SendMessageResult:
        """发送带引用的文本回复。

        Args:
            session_id: 目标会话 ID
            text: 回复文本
            reply_to: 被回复消息的 ID
            agent_id: 发言智能体 ID
            source: 消息来源标识

        Returns:
            SendMessageResult 包含发送结果和消息 ID
        """

    async def send_image(
        self,
        session_id: str,
        image_base64: str,
        *,
        agent_id: str = "",
        source: str = "core",
    ) -> SendMessageResult:
        """发送 Base64 编码的图片消息。

        Args:
            session_id: 目标会话 ID
            image_base64: Base64 编码的图片数据
            agent_id: 发言智能体 ID
            source: 消息来源标识

        Returns:
            SendMessageResult 包含发送结果
        """

    async def send_emoji(
        self,
        session_id: str,
        emoji_base64: str,
        *,
        reply_to: str = "",
        agent_id: str = "",
        source: str = "core",
    ) -> SendMessageResult:
        """发送 Base64 编码的表情消息，可选附带引用。

        Args:
            session_id: 目标会话 ID
            emoji_base64: Base64 编码的表情数据
            reply_to: 被回复消息的 ID（可选）
            agent_id: 发言智能体 ID
            source: 消息来源标识

        Returns:
            SendMessageResult 包含发送结果和消息 ID
        """

    async def send_hybrid(
        self,
        session_id: str,
        segments: list[dict[str, Any]],
        *,
        reply_to: str = "",
        agent_id: str = "",
        source: str = "core",
    ) -> SendMessageResult:
        """发送混合消息（包含多种组件的消息序列）。

        Args:
            session_id: 目标会话 ID
            segments: 消息组件列表，每项为 {"type": "text/image/emoji/at", ...}
            reply_to: 被回复消息的 ID（可选）
            agent_id: 发言智能体 ID
            source: 消息来源标识

        Returns:
            SendMessageResult 包含发送结果
        """

    async def send_forward(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        *,
        agent_id: str = "",
        source: str = "core",
    ) -> SendMessageResult:
        """发送合并转发消息。

        Args:
            session_id: 目标会话 ID
            messages: 转发节点列表，每项包含 user_id/user_nickname/content 等
            agent_id: 发言智能体 ID
            source: 消息来源标识

        Returns:
            SendMessageResult 包含发送结果
        """

    async def send_custom(
        self,
        session_id: str,
        message_type: str,
        content: Any,
        *,
        agent_id: str = "",
        source: str = "core",
    ) -> SendMessageResult:
        """发送自定义类型消息。

        Args:
            session_id: 目标会话 ID
            message_type: 自定义消息类型（如 "command"）
            content: 消息内容
            agent_id: 发言智能体 ID
            source: 消息来源标识

        Returns:
            SendMessageResult 包含发送结果
        """