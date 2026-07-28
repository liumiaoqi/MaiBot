"""Fork Context 数据模型与前缀捕获器。

ForkContext: 冻结父级 LLM 请求前缀的不可变快照。
ForkContextCapturer: 从活跃心流运行时捕获 ForkContext。
"""

from src.common.logger import get_logger
logger = get_logger("auto.fork_context")


import time
from typing import Any, Optional

from pydantic import BaseModel, Field



class ToolDefinition(BaseModel):
    """工具定义快照。"""

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class PermissionRuleset(BaseModel):
    """权限规则集快照。"""

    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    write_paths: list[str] = Field(default_factory=list)


class ModelRef(BaseModel):
    """模型引用快照。"""

    model_id: str = ""
    provider: str = ""
    context_window: int = 0


class ForkContext(BaseModel):
    """Fork 上下文 — 父级 LLM 请求前缀的不可变快照。

    一旦捕获即不可修改（frozen snapshot），
    用于 Checkpoint-Writer 子智能体的 Fork Agent 模式，
    使 LLM 请求前缀与父级完全一致以命中 DeepSeek 前缀缓存。
    """

    model_config = {"frozen": True}

    system: list[str] = Field(default_factory=list, description="父级 system 消息列表")
    tools: dict[str, ToolDefinition] = Field(default_factory=dict, description="父级工具 schema 快照")
    parent_permission: PermissionRuleset = Field(default_factory=PermissionRuleset, description="父级权限规则集快照")
    inherited_messages: list[dict[str, Any]] = Field(default_factory=list, description="继承的父级消息列表")
    watermark_msg_id: str = Field(default="", description="水位线标记（派生时刻的消息边界）")
    model: ModelRef = Field(default_factory=ModelRef, description="父级模型信息")
    agent_id: str = Field(default="", description="父级智能体ID")
    session_id: str = Field(default="", description="关联会话ID")
    captured_at: float = Field(default=0.0, description="捕获时间戳")

    @property
    def is_valid(self) -> bool:
        """检查 ForkContext 是否有效。"""
        return bool(self.system) and bool(self.agent_id)


class ForkContextCapturer:
    """Fork Context 前缀捕获器。

    从活跃心流运行时捕获 ForkContext，
    冻结 system 消息、工具 schema、权限规则集等。
    """

    def __init__(self, runtime: Any = None) -> None:
        self._runtime = runtime

    def capture(self, agent_id: str, session_id: str) -> Optional[ForkContext]:
        """捕获 ForkContext。

        Args:
            agent_id: 父级智能体ID。
            session_id: 关联会话ID。

        Returns:
            ForkContext 或 None（无法捕获时）。
        """
        start = time.monotonic()

        try:
            system_messages = self._capture_system_messages(agent_id, session_id)
            tools = self._capture_tools(agent_id)
            permission = self._capture_permission(agent_id)
            inherited = self._capture_inherited_messages(session_id)
            watermark = self._capture_watermark(session_id)
            model_ref = self._capture_model_ref(agent_id)

            if not system_messages:
                logger.warning(
                    "ForkContext 捕获失败: 无 system 消息 agent=%s session=%s",
                    agent_id,
                    session_id,
                )
                return None

            if not agent_id:
                logger.warning("ForkContext 捕获失败: 无 agent_id")
                return None

            context = ForkContext(
                system=system_messages,
                tools=tools,
                parent_permission=permission,
                inherited_messages=inherited,
                watermark_msg_id=watermark,
                model=model_ref,
                agent_id=agent_id,
                session_id=session_id,
                captured_at=time.time(),
            )

            elapsed_ms = (time.monotonic() - start) * 1000
            logger.info(
                "ForkContext 捕获成功: agent=%s session=%s "
                "system=%d tools=%d inherited=%d 耗时=%.1fms",
                agent_id,
                session_id,
                len(system_messages),
                len(tools),
                len(inherited),
                elapsed_ms,
            )
            return context

        except Exception as e:
            logger.warning("ForkContext 捕获异常: agent=%s error=%s", agent_id, e)
            return None

    def _capture_system_messages(self, agent_id: str, session_id: str) -> list[str]:
        """捕获 system 消息列表。"""
        if self._runtime is None:
            return []

        try:
            from src.core.session_port_registry import get_session_info_port

            session_info = None
            info_port = get_session_info_port()
            if info_port is not None:
                session_info = info_port.get_session_info(session_id)
            if session_info is None:
                return []

            from src.core.adapters.agent_config_port import get_agent_config_provider
            registry = get_agent_config_provider()
            agent_id = getattr(session_info, "primary_agent_id", "")
            if not agent_id or not registry.has_agent(agent_id):
                return []

            template_name = registry.get_agent(agent_id).get_prompt_template_name()
            return [f"[system prompt: {template_name}]"] if template_name else []

        except Exception as exc:
            logger.warning("操作异常 in fork_context.py", exc_info=True)
            return []

    def _capture_tools(self, agent_id: str) -> dict[str, ToolDefinition]:
        """捕获工具 schema 快照。"""
        if self._runtime is None:
            return {}

        try:
            from src.core.adapters.agent_config_port import get_agent_config_provider

            registry = get_agent_config_provider()
            if not registry.has_agent(agent_id):
                return {}

            agent_config = registry.get_agent(agent_id)
            allowlist = agent_config.tool_allowlist or []

            tools: dict[str, ToolDefinition] = {}
            for tool_name in allowlist:
                tools[tool_name] = ToolDefinition(name=tool_name)
            return tools

        except Exception as exc:
            logger.warning("操作异常 in fork_context.py", exc_info=True)
            return {}

    def _capture_permission(self, agent_id: str) -> PermissionRuleset:
        """捕获权限规则集快照。"""
        if self._runtime is None:
            return PermissionRuleset()

        try:
            from src.core.adapters.agent_config_port import get_agent_config_provider

            registry = get_agent_config_provider()
            if not registry.has_agent(agent_id):
                return PermissionRuleset()

            agent_config = registry.get_agent(agent_id)
            return PermissionRuleset(
                allowed_tools=agent_config.tool_allowlist or [],
            )

        except Exception as exc:
            logger.warning("操作异常 in fork_context.py", exc_info=True)
            return PermissionRuleset()

    def _capture_inherited_messages(self, session_id: str) -> list[dict[str, Any]]:
        """捕获继承的父级消息列表（to-watermark）。"""
        return []

    def _capture_watermark(self, session_id: str) -> str:
        """捕获水位线消息ID。"""
        return ""

    def _capture_model_ref(self, agent_id: str) -> ModelRef:
        """捕获模型引用。"""
        return ModelRef()
