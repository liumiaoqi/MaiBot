"""Maisaka 对话循环服务。"""

from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any, List, Optional, Sequence

import asyncio
import json
import random

from pydantic import BaseModel, Field as PydanticField
from rich.console import Group
from rich.panel import Panel

from src.cli.console import console
from src.common.data_models.llm_service_data_models import LLMGenerationOptions
from src.common.logger import get_logger
from src.common.prompt_i18n import load_prompt
from src.common.utils.utils_session import SessionUtils
from src.config.config import global_config
from src.core.tooling import ToolRegistry, ToolSpec
from src.know_u.knowledge import extract_category_ids_from_result
from src.llm_models.model_client.base_client import BaseClient
from src.llm_models.payload_content.message import Message, MessageBuilder, RoleType
from src.llm_models.payload_content.resp_format import RespFormat, RespFormatType
from src.llm_models.payload_content.tool_option import ToolCall, ToolDefinitionInput, ToolOption, normalize_tool_options
from src.plugin_runtime.hook_payloads import (
    deserialize_prompt_messages,
    deserialize_tool_calls,
    serialize_prompt_messages,
    serialize_tool_calls,
    serialize_tool_definitions,
)
from src.plugin_runtime.hook_schema_utils import build_object_schema
from src.plugin_runtime.host.hook_spec_registry import HookSpec, HookSpecRegistry
from src.services.llm_service import LLMServiceClient

from .builtin_tool import get_builtin_tools
from .context_messages import AssistantMessage, LLMContextMessage, ToolResultMessage
from .prompt_cli_renderer import PromptCLIVisualizer


@dataclass(slots=True)
class ChatResponse:
    """LLM 对话循环单步响应。"""

    content: Optional[str]
    tool_calls: List[ToolCall]
    raw_message: AssistantMessage
    selected_history_count: int
    prompt_tokens: int
    built_message_count: int
    completion_tokens: int
    total_tokens: int


class ToolFilterSelection(BaseModel):
    """工具筛选响应。"""

    selected_tool_names: list[str] = PydanticField(default_factory=list)
    """经过预筛后保留的候选工具名称列表。"""


logger = get_logger("maisaka_chat_loop")


def register_maisaka_hook_specs(registry: HookSpecRegistry) -> List[HookSpec]:
    """注册 Maisaka 规划器内置 Hook 规格。

    Args:
        registry: 目标 Hook 规格注册中心。

    Returns:
        List[HookSpec]: 实际注册的 Hook 规格列表。
    """

    return registry.register_hook_specs(
        [
            HookSpec(
                name="maisaka.planner.before_request",
                description="在 Maisaka 向模型发起规划请求前触发，可改写消息窗口与工具定义。",
                parameters_schema=build_object_schema(
                    {
                        "messages": {
                            "type": "array",
                            "description": "即将发给模型的 PromptMessage 列表。",
                        },
                        "tool_definitions": {
                            "type": "array",
                            "description": "当前候选工具定义列表。",
                        },
                        "selected_history_count": {
                            "type": "integer",
                            "description": "当前选中的上下文消息数量。",
                        },
                        "built_message_count": {
                            "type": "integer",
                            "description": "实际发送给模型的消息数量。",
                        },
                        "selection_reason": {
                            "type": "string",
                            "description": "上下文选择说明。",
                        },
                        "session_id": {
                            "type": "string",
                            "description": "当前会话 ID。",
                        },
                    },
                    required=[
                        "messages",
                        "tool_definitions",
                        "selected_history_count",
                        "built_message_count",
                        "selection_reason",
                        "session_id",
                    ],
                ),
                default_timeout_ms=6000,
                allow_abort=False,
                allow_kwargs_mutation=True,
            ),
            HookSpec(
                name="maisaka.planner.after_response",
                description="在 Maisaka 收到模型响应后触发，可调整文本结果与工具调用列表。",
                parameters_schema=build_object_schema(
                    {
                        "response": {
                            "type": "string",
                            "description": "模型返回的文本内容。",
                        },
                        "tool_calls": {
                            "type": "array",
                            "description": "模型返回的工具调用列表。",
                        },
                        "selected_history_count": {
                            "type": "integer",
                            "description": "当前选中的上下文消息数量。",
                        },
                        "built_message_count": {
                            "type": "integer",
                            "description": "实际发送给模型的消息数量。",
                        },
                        "selection_reason": {
                            "type": "string",
                            "description": "上下文选择说明。",
                        },
                        "session_id": {
                            "type": "string",
                            "description": "当前会话 ID。",
                        },
                        "prompt_tokens": {
                            "type": "integer",
                            "description": "输入 Token 数。",
                        },
                        "completion_tokens": {
                            "type": "integer",
                            "description": "输出 Token 数。",
                        },
                        "total_tokens": {
                            "type": "integer",
                            "description": "总 Token 数。",
                        },
                    },
                    required=[
                        "response",
                        "tool_calls",
                        "selected_history_count",
                        "built_message_count",
                        "selection_reason",
                        "session_id",
                        "prompt_tokens",
                        "completion_tokens",
                        "total_tokens",
                    ],
                ),
                default_timeout_ms=6000,
                allow_abort=False,
                allow_kwargs_mutation=True,
            ),
        ]
    )


class MaisakaChatLoopService:
    """负责 Maisaka 主对话循环、系统提示词和终端渲染。"""

    def __init__(
        self,
        chat_system_prompt: Optional[str] = None,
        session_id: Optional[str] = None,
        is_group_chat: Optional[bool] = None,
        temperature: float = 0.5,
        max_tokens: int = 2048,
    ) -> None:
        """初始化 Maisaka 对话循环服务。

        Args:
            chat_system_prompt: 可选的系统提示词。
            session_id: 当前会话 ID，用于匹配会话级额外提示。
            is_group_chat: 当前会话是否为群聊。
            temperature: 规划器温度参数。
            max_tokens: 规划器最大输出长度。
        """

        self._temperature = temperature
        self._max_tokens = max_tokens
        self._is_group_chat = is_group_chat
        self._session_id = session_id or ""
        self._extra_tools: List[ToolOption] = []
        self._interrupt_flag: asyncio.Event | None = None
        self._tool_registry: ToolRegistry | None = None
        self._prompts_loaded = chat_system_prompt is not None
        self._prompt_load_lock = asyncio.Lock()
        self._personality_prompt = self._build_personality_prompt()
        if chat_system_prompt is None:
            self._chat_system_prompt = f"{self._personality_prompt}\n\nYou are a helpful AI assistant."
        else:
            self._chat_system_prompt = chat_system_prompt
        self._llm_chat = LLMServiceClient(task_name="planner", request_type="maisaka_planner")
        self._tool_filter_llm = LLMServiceClient(
            task_name=global_config.maisaka.tool_filter_task_name,
            request_type="maisaka_tool_filter",
        )

    @property
    def personality_prompt(self) -> str:
        """返回当前人格提示词。"""

        return self._personality_prompt

    @staticmethod
    def _get_runtime_manager() -> Any:
        """获取插件运行时管理器。

        Returns:
            Any: 插件运行时管理器单例。
        """

        from src.plugin_runtime.integration import get_plugin_runtime_manager

        return get_plugin_runtime_manager()

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        """将任意值安全转换为整数。

        Args:
            value: 待转换的输入值。
            default: 转换失败时的默认值。

        Returns:
            int: 转换后的整数结果。
        """

        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _build_personality_prompt(self) -> str:
        """构造人格提示词。"""

        try:
            bot_name = global_config.bot.nickname
            if global_config.bot.alias_names:
                bot_nickname = f", also known as {','.join(global_config.bot.alias_names)}"
            else:
                bot_nickname = ""

            prompt_personality = global_config.personality.personality
            if (
                hasattr(global_config.personality, "states")
                and global_config.personality.states
                and hasattr(global_config.personality, "state_probability")
                and global_config.personality.state_probability > 0
                and random.random() < global_config.personality.state_probability
            ):
                prompt_personality = random.choice(global_config.personality.states)

            return f"Your name is {bot_name}{bot_nickname}; persona: {prompt_personality};"
        except Exception:
            return "Your name is MaiMai; persona: lively and cute AI assistant."

    async def ensure_chat_prompt_loaded(self, tools_section: str = "") -> None:
        """确保主聊天提示词已经加载完成。

        Args:
            tools_section: 额外注入到提示词中的工具说明片段。
        """
        async with self._prompt_load_lock:
            try:
                self._chat_system_prompt = load_prompt("maisaka_chat", **self.build_prompt_template_context(tools_section))
            except Exception:
                self._chat_system_prompt = f"{self._personality_prompt}\n\nYou are a helpful AI assistant."

            self._prompts_loaded = True

    def build_prompt_template_context(self, tools_section: str = "") -> dict[str, str]:
        """构造 Maisaka prompt 模板的公共渲染参数。"""

        return {
            "bot_name": global_config.bot.nickname,
            "file_tools_section": tools_section,
            "group_chat_attention_block": self._build_group_chat_attention_block(),
            "identity": self._personality_prompt,
        }

    def _build_group_chat_attention_block(self) -> str:
        """构建当前聊天场景下的额外注意事项块。"""

        prompt_lines: List[str] = []

        if self._is_group_chat is True:
            if group_chat_prompt := str(global_config.chat.group_chat_prompt or "").strip():
                prompt_lines.append(f"通用注意事项：\n{group_chat_prompt}")
        elif self._is_group_chat is False:
            if private_chat_prompt := str(global_config.chat.private_chat_prompts or "").strip():
                prompt_lines.append(f"通用注意事项：\n{private_chat_prompt}")

        if self._session_id:
            if chat_prompt := self._get_chat_prompt_for_chat(self._session_id, self._is_group_chat).strip():
                prompt_lines.append(f"当前聊天额外注意事项：\n{chat_prompt}")

        if not prompt_lines:
            return ""

        return "在该聊天中的注意事项：\n" + "\n\n".join(prompt_lines) + "\n"

    @staticmethod
    def _get_chat_prompt_for_chat(chat_id: str, is_group_chat: Optional[bool]) -> str:
        """根据聊天流 ID 获取匹配的额外提示。"""

        if not global_config.chat.chat_prompts:
            return ""

        for chat_prompt_item in global_config.chat.chat_prompts:
            if hasattr(chat_prompt_item, "platform"):
                platform = str(chat_prompt_item.platform or "").strip()
                item_id = str(chat_prompt_item.item_id or "").strip()
                rule_type = str(chat_prompt_item.rule_type or "").strip()
                prompt_content = str(chat_prompt_item.prompt or "").strip()
            elif isinstance(chat_prompt_item, str):
                parts = chat_prompt_item.split(":", 3)
                if len(parts) != 4:
                    continue

                platform, item_id, rule_type, prompt_content = parts
                platform = platform.strip()
                item_id = item_id.strip()
                rule_type = rule_type.strip()
                prompt_content = prompt_content.strip()
            else:
                continue

            if not platform or not item_id or not prompt_content:
                continue

            if rule_type == "group":
                config_is_group = True
                config_chat_id = SessionUtils.calculate_session_id(platform, group_id=item_id)
            elif rule_type == "private":
                config_is_group = False
                config_chat_id = SessionUtils.calculate_session_id(platform, user_id=item_id)
            else:
                continue

            if is_group_chat is not None and config_is_group != is_group_chat:
                continue

            if config_chat_id == chat_id:
                logger.debug(f"匹配到 Maisaka 聊天额外提示，chat_id: {chat_id}, prompt: {prompt_content[:50]}...")
                return prompt_content

        return ""

    def set_extra_tools(self, tools: Sequence[ToolDefinitionInput]) -> None:
        """设置额外工具定义。

        Args:
            tools: 兼容旧接口的额外工具定义列表。
        """

        self._extra_tools = normalize_tool_options(list(tools)) or []

    def set_tool_registry(self, tool_registry: ToolRegistry | None) -> None:
        """设置统一工具注册表。

        Args:
            tool_registry: 统一工具注册表；传入 ``None`` 时退回旧工具列表模式。
        """

        self._tool_registry = tool_registry

    def set_interrupt_flag(self, interrupt_flag: asyncio.Event | None) -> None:
        """设置当前 planner 请求使用的中断标记。"""
        self._interrupt_flag = interrupt_flag

    def _build_request_messages(
        self,
        selected_history: List[LLMContextMessage],
        *,
        system_prompt: Optional[str] = None,
    ) -> List[Message]:
        """构造发给大模型的消息列表。

        Args:
            selected_history: 已选中的上下文消息列表。

        Returns:
            List[Message]: 发送给大模型的消息列表。
        """

        messages: List[Message] = []
        system_msg = MessageBuilder().set_role(RoleType.System)
        system_msg.add_text_content(system_prompt if system_prompt is not None else self._chat_system_prompt)
        messages.append(system_msg.build())

        for msg in selected_history:
            llm_message = msg.to_llm_message()
            if llm_message is not None:
                messages.append(llm_message)

        return messages

    @staticmethod
    def _is_builtin_tool_spec(tool_spec: ToolSpec) -> bool:
        """判断一个工具是否属于默认内置工具。

        Args:
            tool_spec: 待判断的工具声明。

        Returns:
            bool: 是否为默认内置工具。
        """

        return tool_spec.provider_type == "builtin" or tool_spec.provider_name == "maisaka_builtin"

    @classmethod
    def _split_builtin_and_candidate_tools(
        cls,
        tool_specs: List[ToolSpec],
    ) -> tuple[List[ToolSpec], List[ToolSpec]]:
        """拆分内置工具与可筛选工具列表。

        Args:
            tool_specs: 当前全部工具声明。

        Returns:
            tuple[List[ToolSpec], List[ToolSpec]]: `(内置工具, 可筛选工具)`。
        """

        builtin_tool_specs: List[ToolSpec] = []
        candidate_tool_specs: List[ToolSpec] = []
        for tool_spec in tool_specs:
            if cls._is_builtin_tool_spec(tool_spec):
                builtin_tool_specs.append(tool_spec)
            else:
                candidate_tool_specs.append(tool_spec)
        return builtin_tool_specs, candidate_tool_specs

    @staticmethod
    def _truncate_tool_filter_text(text: str, max_length: int = 180) -> str:
        """截断工具筛选阶段展示的文本。

        Args:
            text: 原始文本。
            max_length: 最长保留字符数。

        Returns:
            str: 截断后的文本。
        """

        normalized_text = text.strip()
        if len(normalized_text) <= max_length:
            return normalized_text
        return f"{normalized_text[: max_length - 1]}…"

    def _build_tool_filter_prompt(
        self,
        selected_history: List[LLMContextMessage],
        candidate_tool_specs: List[ToolSpec],
        max_keep: int,
    ) -> str:
        """构造小模型工具预筛选提示词。

        Args:
            selected_history: 已选中的对话上下文。
            candidate_tool_specs: 非内置候选工具列表。
            max_keep: 最多保留的候选工具数量。

        Returns:
            str: 用于工具预筛的小模型提示词。
        """

        history_lines: List[str] = []
        for message in selected_history[-10:]:
            plain_text = message.processed_plain_text.strip()
            if not plain_text:
                continue
            history_lines.append(
                f"- {message.role}: {self._truncate_tool_filter_text(plain_text, max_length=200)}"
            )

        if history_lines:
            history_section = "\n".join(history_lines)
        else:
            history_section = "- 当前没有可用的对话上下文。"

        tool_lines = [
            f"- {tool_spec.name}: {tool_spec.brief_description.strip() or '无简要描述'}"
            for tool_spec in candidate_tool_specs
        ]
        tool_section = "\n".join(tool_lines) if tool_lines else "- 当前没有候选工具。"

        return (
            "你是 Maisaka 的工具预筛选器。\n"
            "你的任务是在正式进入 planner 前，根据当前情景从候选工具中挑出最可能马上会用到的工具。\n"
            "默认内置工具已经自动保留，不在候选列表中，你不需要再次选择它们。\n"
            "你只能参考工具的简要描述，不要假设未描述的隐藏能力。\n"
            f"最多保留 {max_keep} 个候选工具；如果都不合适，可以返回空数组。\n"
            "请严格返回 JSON 对象，格式为："
            '{"selected_tool_names":["工具名1","工具名2"]}\n\n'
            f"【最近对话】\n{history_section}\n\n"
            f"【候选工具（仅简要描述）】\n{tool_section}"
        )

    @staticmethod
    def _parse_tool_filter_response(
        response_text: str,
        candidate_tool_specs: List[ToolSpec],
        max_keep: int,
    ) -> List[ToolSpec] | None:
        """解析工具预筛选响应。

        Args:
            response_text: 小模型返回的原始文本。
            candidate_tool_specs: 非内置候选工具列表。
            max_keep: 最多保留的候选工具数量。

        Returns:
            List[ToolSpec] | None: 成功解析时返回筛选后的工具列表；解析失败时返回 ``None``。
        """

        normalized_response = response_text.strip()
        if not normalized_response:
            return None

        selected_tool_names: List[str]
        try:
            selected_tool_names = ToolFilterSelection.model_validate_json(normalized_response).selected_tool_names
        except Exception:
            try:
                parsed_payload = json.loads(normalized_response)
            except json.JSONDecodeError:
                return None

            if isinstance(parsed_payload, dict):
                raw_tool_names = parsed_payload.get("selected_tool_names", [])
            elif isinstance(parsed_payload, list):
                raw_tool_names = parsed_payload
            else:
                return None

            if not isinstance(raw_tool_names, list):
                return None

            selected_tool_names = []
            for item in raw_tool_names:
                normalized_name = str(item).strip()
                if normalized_name:
                    selected_tool_names.append(normalized_name)

        candidate_map = {tool_spec.name: tool_spec for tool_spec in candidate_tool_specs}
        filtered_tool_specs: List[ToolSpec] = []
        seen_names: set[str] = set()
        for tool_name in selected_tool_names:
            normalized_name = tool_name.strip()
            if not normalized_name or normalized_name in seen_names:
                continue
            tool_spec = candidate_map.get(normalized_name)
            if tool_spec is None:
                continue

            seen_names.add(normalized_name)
            filtered_tool_specs.append(tool_spec)
            if len(filtered_tool_specs) >= max_keep:
                break

        return filtered_tool_specs

    async def _filter_tool_specs_for_planner(
        self,
        selected_history: List[LLMContextMessage],
        tool_specs: List[ToolSpec],
    ) -> List[ToolSpec]:
        """在将工具交给 planner 前进行快速预筛选。

        Args:
            selected_history: 已选中的对话上下文。
            tool_specs: 当前全部可用工具声明。

        Returns:
            List[ToolSpec]: 最终交给 planner 的工具声明列表。
        """

        threshold = max(1, int(global_config.maisaka.tool_filter_threshold))
        max_keep = max(1, int(global_config.maisaka.tool_filter_max_keep))
        if len(tool_specs) <= threshold:
            return tool_specs

        builtin_tool_specs, candidate_tool_specs = self._split_builtin_and_candidate_tools(tool_specs)
        if not candidate_tool_specs:
            return tool_specs
        if len(candidate_tool_specs) <= max_keep:
            return [*builtin_tool_specs, *candidate_tool_specs]

        filter_prompt = self._build_tool_filter_prompt(selected_history, candidate_tool_specs, max_keep)
        logger.info(
            "工具预筛选开始: "
            f"总工具数={len(tool_specs)} "
            f"内置工具数={len(builtin_tool_specs)} "
            f"候选工具数={len(candidate_tool_specs)} "
            f"最多保留候选数={max_keep}"
        )

        try:
            generation_result = await self._tool_filter_llm.generate_response(
                prompt=filter_prompt,
                options=LLMGenerationOptions(
                    temperature=0.0,
                    max_tokens=256,
                    response_format=RespFormat(
                        format_type=RespFormatType.JSON_SCHEMA,
                        schema=ToolFilterSelection,
                    ),
                ),
            )
        except Exception as exc:
            logger.warning(f"工具预筛选失败，保留全部工具。错误={exc}")
            return tool_specs

        filtered_candidate_tool_specs = self._parse_tool_filter_response(
            generation_result.response or "",
            candidate_tool_specs,
            max_keep,
        )
        if filtered_candidate_tool_specs is None:
            logger.warning(
                "工具预筛选返回结果无法解析，保留全部工具。"
                f" 原始返回={generation_result.response or ''!r}"
            )
            return tool_specs

        filtered_tool_specs = [*builtin_tool_specs, *filtered_candidate_tool_specs]
        if not filtered_tool_specs:
            logger.warning("工具预筛选得到空结果，保留全部工具以避免主流程失去工具能力。")
            return tool_specs

        logger.info(
            "工具预筛选完成: "
            f"筛选前总数={len(tool_specs)} "
            f"筛选后总数={len(filtered_tool_specs)} "
            f"保留候选工具={[tool_spec.name for tool_spec in filtered_candidate_tool_specs]}"
        )
        return filtered_tool_specs

    async def analyze_knowledge_need(
        self,
        chat_history: List[LLMContextMessage],
        categories_summary: str,
    ) -> List[str]:
        """分析当前对话是否需要检索知识库分类。"""
        visible_history: List[str] = []
        for message in chat_history[-8:]:
            if not message.processed_plain_text:
                continue
            visible_history.append(f"{message.role}: {message.processed_plain_text}")

        if not visible_history or not categories_summary.strip():
            return []

        prompt = (
            "你需要判断当前对话是否需要查询知识库。\n"
            "请只返回最相关的分类编号，多个编号用空格分隔；如果完全不需要，返回 none。\n\n"
            f"【可用分类】\n{categories_summary}\n\n"
            f"【最近对话】\n{chr(10).join(visible_history)}"
        )

        try:
            generation_result = await self._llm_chat.generate_response(
                prompt=prompt,
                options=LLMGenerationOptions(
                    temperature=0.1,
                    max_tokens=64,
                ),
            )
        except Exception:
            return []

        return extract_category_ids_from_result(generation_result.response or "")

    async def chat_loop_step(
        self,
        chat_history: List[LLMContextMessage],
        *,
        request_kind: str = "planner",
        response_format: RespFormat | None = None,
        tool_definitions: Sequence[ToolDefinitionInput] | None = None,
    ) -> ChatResponse:
        """执行一轮 Maisaka 规划器请求。

        Args:
            chat_history: 当前对话历史。

        Returns:
            ChatResponse: 本轮规划器返回结果。
        """

        if not self._prompts_loaded:
            await self.ensure_chat_prompt_loaded()
        selected_history, selection_reason = self.select_llm_context_messages(chat_history)
        built_messages = self._build_request_messages(selected_history)

        def message_factory(_client: BaseClient) -> List[Message]:
            """返回当前轮次已经构建好的请求消息。

            Args:
                _client: 当前模型客户端；此处不依赖客户端能力。

            Returns:
                List[Message]: 已经构建好的消息列表。
            """

            del _client
            return built_messages

        all_tools: List[ToolDefinitionInput]
        if tool_definitions is not None:
            all_tools = list(tool_definitions)
        elif self._tool_registry is not None:
            tool_specs = await self._tool_registry.list_tools()
            filtered_tool_specs = await self._filter_tool_specs_for_planner(selected_history, tool_specs)
            all_tools = [tool_spec.to_llm_definition() for tool_spec in filtered_tool_specs]
        else:
            all_tools = [*get_builtin_tools(), *self._extra_tools]

        before_request_result = await self._get_runtime_manager().invoke_hook(
            "maisaka.planner.before_request",
            messages=serialize_prompt_messages(built_messages),
            tool_definitions=serialize_tool_definitions(all_tools),
            selected_history_count=len(selected_history),
            built_message_count=len(built_messages),
            selection_reason=selection_reason,
            session_id=self._session_id,
        )
        before_request_kwargs = before_request_result.kwargs
        raw_messages = before_request_kwargs.get("messages")
        if isinstance(raw_messages, list):
            try:
                built_messages = deserialize_prompt_messages(raw_messages)
            except Exception as exc:
                logger.warning(f"Hook maisaka.planner.before_request 返回的 messages 无法反序列化，已忽略: {exc}")
        raw_tool_definitions = before_request_kwargs.get("tool_definitions")
        if isinstance(raw_tool_definitions, list):
            all_tools = [item for item in raw_tool_definitions if isinstance(item, dict)]

        if global_config.debug.show_maisaka_thinking:
            panel_title, panel_border_style = PromptCLIVisualizer.get_request_panel_style(request_kind)
            image_display_mode: str = "path_link" if global_config.maisaka.show_image_path else "legacy"
            if global_config.debug.fold_maisaka_thinking:
                prompt_renderable = PromptCLIVisualizer.build_prompt_access_panel(
                    built_messages,
                    request_kind=request_kind,
                    selection_reason=selection_reason,
                    image_display_mode=image_display_mode,
                )
            else:
                ordered_panels = PromptCLIVisualizer.build_prompt_panels(
                    built_messages,
                    image_display_mode=image_display_mode,
                )
                prompt_renderable = Group(*ordered_panels)
            console.print(
                Panel(
                    prompt_renderable,
                    title=panel_title,
                    subtitle=selection_reason,
                    border_style=panel_border_style,
                    padding=(0, 1),
                )
            )

        request_started_at = perf_counter()
        logger.info(
            "规划器请求开始: "
            f"已选上下文消息数={len(selected_history)} "
            f"大模型消息数={len(built_messages)} "
            f"工具数={len(all_tools)} "
            f"启用打断={self._interrupt_flag is not None}"
        )
        generation_result = await self._llm_chat.generate_response_with_messages(
            message_factory=message_factory,
            options=LLMGenerationOptions(
                tool_options=all_tools if all_tools else None,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                response_format=response_format,
                interrupt_flag=self._interrupt_flag,
            ),
        )
        request_elapsed = perf_counter() - request_started_at
        logger.info(f"规划器请求完成，耗时={request_elapsed:.3f} 秒")

        prompt_stats_text = PromptCLIVisualizer.build_prompt_stats_text(
            selected_history_count=len(selected_history),
            built_message_count=len(built_messages),
            prompt_tokens=generation_result.prompt_tokens,
            completion_tokens=generation_result.completion_tokens,
            total_tokens=generation_result.total_tokens,
        )
        logger.info(f"本轮Prompt统计: {prompt_stats_text}")

        final_response = generation_result.response or ""
        final_tool_calls = list(generation_result.tool_calls or [])
        after_response_result = await self._get_runtime_manager().invoke_hook(
            "maisaka.planner.after_response",
            response=final_response,
            tool_calls=serialize_tool_calls(final_tool_calls),
            selected_history_count=len(selected_history),
            built_message_count=len(built_messages),
            selection_reason=selection_reason,
            session_id=self._session_id,
            prompt_tokens=generation_result.prompt_tokens,
            completion_tokens=generation_result.completion_tokens,
            total_tokens=generation_result.total_tokens,
        )
        after_response_kwargs = after_response_result.kwargs
        if "response" in after_response_kwargs:
            final_response = str(after_response_kwargs.get("response") or "")
        raw_tool_calls = after_response_kwargs.get("tool_calls")
        if isinstance(raw_tool_calls, list):
            try:
                final_tool_calls = deserialize_tool_calls(raw_tool_calls)
            except Exception as exc:
                logger.warning(f"Hook maisaka.planner.after_response 返回的 tool_calls 无法反序列化，已忽略: {exc}")
        prompt_tokens = self._coerce_int(after_response_kwargs.get("prompt_tokens"), generation_result.prompt_tokens)
        completion_tokens = self._coerce_int(
            after_response_kwargs.get("completion_tokens"),
            generation_result.completion_tokens,
        )
        total_tokens = self._coerce_int(after_response_kwargs.get("total_tokens"), generation_result.total_tokens)

        raw_message = AssistantMessage(
            content=final_response,
            timestamp=datetime.now(),
            tool_calls=final_tool_calls,
        )
        return ChatResponse(
            content=final_response or None,
            tool_calls=final_tool_calls,
            raw_message=raw_message,
            selected_history_count=len(selected_history),
            prompt_tokens=prompt_tokens,
            built_message_count=len(built_messages),
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def select_llm_context_messages(
        chat_history: List[LLMContextMessage],
        *,
        max_context_size: Optional[int] = None,
    ) -> tuple[List[LLMContextMessage], str]:
        """??????? LLM ???????"""

        effective_context_size = max(1, int(max_context_size or global_config.chat.max_context_size))
        selected_indices: List[int] = []
        counted_message_count = 0

        for index in range(len(chat_history) - 1, -1, -1):
            message = chat_history[index]
            if message.to_llm_message() is None:
                continue

            selected_indices.append(index)
            if message.count_in_context:
                counted_message_count += 1
                if counted_message_count >= effective_context_size:
                    break

        if not selected_indices:
            return [], f"???????? {effective_context_size} ? user/assistant??? 0 ??"

        selected_indices.reverse()
        selected_history = [chat_history[index] for index in selected_indices]
        selected_history, hidden_assistant_count = MaisakaChatLoopService._hide_early_assistant_messages(selected_history)
        selected_history = MaisakaChatLoopService._drop_leading_orphan_tool_results(selected_history)
        selection_reason = (
            f"上下文裁剪：最近 {effective_context_size} 条 user/assistant 消息，"
            f"实际发送 {len(selected_history)} 条"
        )
        if hidden_assistant_count > 0:
            selection_reason += f"，已隐藏最早 {hidden_assistant_count} 条 assistant 消息"
        return (
            selected_history,
            selection_reason,
        )

    @staticmethod
    def _select_llm_context_messages(chat_history: List[LLMContextMessage]) -> tuple[List[LLMContextMessage], str]:
        """选择真正发送给 LLM 的上下文消息。

        Args:
            chat_history: 当前全部对话历史。

        Returns:
            tuple[List[LLMContextMessage], str]: `(已选上下文, 选择说明)`。
        """

        max_context_size = max(1, int(global_config.chat.max_context_size))
        selected_indices: List[int] = []
        counted_message_count = 0

        for index in range(len(chat_history) - 1, -1, -1):
            message = chat_history[index]
            if message.to_llm_message() is None:
                continue

            selected_indices.append(index)
            if message.count_in_context:
                counted_message_count += 1
                if counted_message_count >= max_context_size:
                    break

        if not selected_indices:
            return [], f"上下文判定：最近 {max_context_size} 条 user/assistant（当前 0 条）"

        selected_indices.reverse()
        selected_history = [chat_history[index] for index in selected_indices]
        selected_history, hidden_assistant_count = MaisakaChatLoopService._hide_early_assistant_messages(selected_history)
        selected_history = MaisakaChatLoopService._drop_leading_orphan_tool_results(selected_history)
        return (
            selected_history,
            (
                f"上下文判定：最近 {max_context_size} 条 user/assistant；"
                f"展示并发送窗口内消息 {len(selected_history)} 条"
            ),
        )

    @staticmethod
    def _hide_early_assistant_messages(
        selected_history: List[LLMContextMessage],
    ) -> tuple[List[LLMContextMessage], int]:
        """隐藏上下文中最早 50% 的 assistant 文本消息，但保留工具调用链路。"""

        assistant_indices = [
            index
            for index, message in enumerate(selected_history)
            if isinstance(message, AssistantMessage)
        ]
        hidden_assistant_count = len(assistant_indices) // 2
        if hidden_assistant_count <= 0:
            return selected_history, 0

        removed_assistant_indices = set(assistant_indices[:hidden_assistant_count])

        filtered_history: List[LLMContextMessage] = []
        for index, message in enumerate(selected_history):
            if index in removed_assistant_indices:
                if not message.tool_calls:
                    continue
                filtered_history.append(
                    AssistantMessage(
                        content="",
                        timestamp=message.timestamp,
                        tool_calls=list(message.tool_calls),
                        source_kind=message.source_kind,
                    )
                )
                continue
            filtered_history.append(message)

        return filtered_history, hidden_assistant_count

    @staticmethod
    def _drop_leading_orphan_tool_results(
        selected_history: List[LLMContextMessage],
    ) -> List[LLMContextMessage]:
        """移除窗口前缀中缺少对应 tool_call 的工具结果消息。"""

        if not selected_history:
            return selected_history

        available_tool_call_ids = {
            tool_call.call_id
            for message in selected_history
            if isinstance(message, AssistantMessage)
            for tool_call in message.tool_calls
            if tool_call.call_id
        }

        first_valid_index = 0
        while first_valid_index < len(selected_history):
            message = selected_history[first_valid_index]
            if not isinstance(message, ToolResultMessage):
                break
            if message.tool_call_id in available_tool_call_ids:
                break
            first_valid_index += 1

        if first_valid_index == 0:
            return selected_history
        return selected_history[first_valid_index:]
