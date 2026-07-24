"""Scope 词汇表 — Phoenix 细粒度授权定义。

三段式格式：资源域:操作:资源类型（如 message:send:text）。
11 个资源域，54 个 scope 条目，覆盖全部 75 个旧 capabilities。
版本：1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ScopeEntry:
    """单个 scope 条目。"""

    scope: str
    description: str
    replaces: str | None
    risk_level: Literal["low", "medium", "high"]
    approval_required: bool


_SCOPE_ENTRIES: frozenset[ScopeEntry] = frozenset({
    # ── message 资源域（9 个） ──
    ScopeEntry("message:send:text", "发送文本消息", "send.text", "low", False),
    ScopeEntry("message:send:image", "发送图片消息", "send.image", "medium", True),
    ScopeEntry("message:send:emoji", "发送表情包", "send.emoji", "medium", True),
    ScopeEntry("message:send:forward", "发送转发消息", "send.forward", "medium", True),
    ScopeEntry("message:send:hybrid", "发送图文混合消息", "send.hybrid", "medium", True),
    ScopeEntry("message:read:recent", "读取最近消息", "message.get_recent", "low", False),
    ScopeEntry("message:read:by_time", "按时间范围读取消息", "message.get_by_time", "low", False),
    ScopeEntry("message:read:by_id", "按 ID 读取消息", "message.get_by_id", "low", False),
    ScopeEntry("message:write:context", "向聊天上下文追加消息", "maisaka.context.append", "high", True),

    # ── database 资源域（8 个） ──
    ScopeEntry("database:read:session_message", "读取会话消息表", "db.query, db.get", "low", False),
    ScopeEntry("database:read:plugin_data", "读取插件数据表", "db.query, db.get", "low", False),
    ScopeEntry("database:write:session_message", "写入会话消息表", "db.save, db.create", "high", True),
    ScopeEntry("database:write:plugin_data", "写入插件数据表", "db.save, db.create", "medium", True),
    ScopeEntry("database:delete:session_message", "删除会话消息", "db.delete", "high", True),
    ScopeEntry("database:delete:plugin_data", "删除插件数据", "db.delete", "medium", True),
    ScopeEntry("database:read:self", "读取自身插件键值存储", "config.get", "low", False),
    ScopeEntry("database:write:self", "写入自身插件键值存储", "config.get", "low", False),

    # ── session 资源域（3 个） ──
    ScopeEntry("session:read:list", "列出所有会话", "chat.get_all_streams", "low", False),
    ScopeEntry("session:read:detail", "查询会话详情", "chat.get_stream_by_group_id", "low", False),
    ScopeEntry("session:write:create", "创建新会话", "chat.open_session", "medium", True),

    # ── memory 资源域（3 个） ──
    ScopeEntry("memory:read:search", "检索记忆", None, "medium", True),
    ScopeEntry("memory:read:profile", "查询人物画像", None, "medium", True),
    ScopeEntry("memory:write:observe", "写入记忆观察", None, "high", True),

    # ── config 资源域（3 个） ──
    ScopeEntry("config:read:self", "读取自身插件配置", "config.get_plugin", "low", False),
    ScopeEntry("config:read:all", "读取全部配置", "config.get_all", "high", True),
    ScopeEntry("config:write:self", "修改自身插件配置", "component.update_plugin_config", "medium", True),

    # ── agent 资源域（3 个） ──
    ScopeEntry("agent:read:emotion", "查询智能体情绪", "agent.emotion.get", "low", False),
    ScopeEntry("agent:read:relationship", "查询智能体关系", "agent.relationship.get", "low", False),
    ScopeEntry("agent:execute:proactive", "触发智能体主动对话", "maisaka.proactive.trigger", "high", True),

    # ── person 资源域（2 个） ──
    ScopeEntry("person:read:id", "查询人物 ID", "person.get_id", "low", False),
    ScopeEntry("person:read:detail", "查询人物详情", "person.get_value", "low", False),

    # ── llm 资源域（5 个） ──
    ScopeEntry("llm:execute:generate", "调用 LLM 生成", "llm.generate", "high", True),
    ScopeEntry("llm:execute:generate_with_tools", "调用 LLM 工具循环", "llm.generate_with_tools", "high", True),
    ScopeEntry("llm:execute:embed", "调用 LLM 嵌入", "llm.embed", "medium", True),
    ScopeEntry("llm:execute:transcribe", "调用 LLM 语音转文字", "llm.transcribe_audio", "medium", True),
    ScopeEntry("llm:read:models", "查询可用模型", "llm.get_available_models", "low", False),

    # ── emoji 资源域（5 个） ──
    ScopeEntry("emoji:read:random", "获取随机表情包", "emoji.get_random", "low", False),
    ScopeEntry("emoji:read:by_description", "按描述搜索表情包", "emoji.get_by_description", "low", False),
    ScopeEntry("emoji:read:list", "列出所有表情包", "emoji.get_all", "low", False),
    ScopeEntry("emoji:write:register", "注册新表情包", "emoji.register", "medium", True),
    ScopeEntry("emoji:write:delete", "删除表情包", "emoji.delete", "high", True),

    # ── plugin 资源域（6 个） ──
    ScopeEntry("plugin:read:list", "列出已加载插件", "component.list_loaded_plugins", "low", False),
    ScopeEntry("plugin:read:info", "查询插件信息", "component.get_plugin_info", "low", False),
    ScopeEntry("plugin:write:config", "修改插件配置", "component.update_plugin_config", "medium", True),
    ScopeEntry("plugin:write:enable", "启用/禁用插件", "component.enable", "medium", True),
    ScopeEntry("plugin:execute:load", "加载/卸载/重载插件", "component.load_plugin", "high", True),
    ScopeEntry("plugin:execute:api", "调用插件 API", "api.call", "medium", True),

    # ── system 资源域（7 个） ──
    ScopeEntry("system:read:statistics", "读取系统统计", "statistics.local.models", "low", False),
    ScopeEntry("system:read:frequency", "读取发言频率", "frequency.get_current_talk_value", "low", False),
    ScopeEntry("system:read:tool_definitions", "读取工具定义", "tool.get_definitions", "low", False),
    ScopeEntry("system:write:frequency", "调整发言频率", "frequency.set_adjust", "medium", True),
    ScopeEntry("system:execute:render", "渲染 HTML 为图片", "render.html2png", "medium", True),
    ScopeEntry("system:execute:command", "发送平台命令", "send.command", "high", True),
    ScopeEntry("system:execute:knowledge", "搜索知识库", "knowledge.search", "low", False),
})

_CAPABILITY_MAP: dict[str, list[str]] = {
    # send.*
    "send.text": ["message:send:text"],
    "send.image": ["message:send:image"],
    "send.emoji": ["message:send:emoji"],
    "send.forward": ["message:send:forward"],
    "send.hybrid": ["message:send:hybrid"],
    "send.command": ["system:execute:command"],
    "send.custom": ["system:execute:command"],

    # db.* / database.*
    "database.query": ["database:read:session_message", "database:read:plugin_data"],
    "database.save": ["database:write:session_message", "database:write:plugin_data"],
    "database.get": ["database:read:session_message", "database:read:plugin_data"],
    "database.delete": ["database:delete:session_message", "database:delete:plugin_data"],
    "database.count": ["database:read:session_message", "database:read:plugin_data"],
    "db.query": ["database:read:session_message", "database:read:plugin_data"],
    "db.save": ["database:write:session_message", "database:write:plugin_data"],
    "db.get": ["database:read:session_message", "database:read:plugin_data"],
    "db.delete": ["database:delete:session_message", "database:delete:plugin_data"],
    "db.count": ["database:read:session_message", "database:read:plugin_data"],
    "db.create": ["database:write:session_message", "database:write:plugin_data"],

    # config.*
    "config.get": ["database:read:self"],
    "config.get_plugin": ["config:read:self"],
    "config.get_all": ["config:read:all"],

    # chat.*
    "chat.get_all_streams": ["session:read:list"],
    "chat.get_group_streams": ["session:read:list"],
    "chat.get_private_streams": ["session:read:list"],
    "chat.open_session": ["session:write:create"],
    "chat.get_stream_by_group_id": ["session:read:detail"],
    "chat.get_stream_by_user_id": ["session:read:detail"],

    # message.*
    "message.get_by_time": ["message:read:by_time"],
    "message.get_by_time_in_chat": ["message:read:by_time"],
    "message.get_by_id": ["message:read:by_id"],
    "message.get_recent": ["message:read:recent"],
    "message.count_new": ["message:read:recent"],
    "message.build_readable": ["message:read:recent"],

    # maisaka.*
    "maisaka.context.append": ["message:write:context"],
    "maisaka.proactive.trigger": ["agent:execute:proactive"],

    # agent.*
    "agent.emotion.get": ["agent:read:emotion"],
    "agent.relationship.get": ["agent:read:relationship"],

    # person.*
    "person.get_id": ["person:read:id"],
    "person.get_value": ["person:read:detail"],
    "person.get_id_by_name": ["person:read:id"],

    # llm.*
    "llm.generate": ["llm:execute:generate"],
    "llm.generate_with_tools": ["llm:execute:generate_with_tools"],
    "llm.embed": ["llm:execute:embed"],
    "llm.transcribe_audio": ["llm:execute:transcribe"],
    "llm.get_available_models": ["llm:read:models"],

    # emoji.*
    "emoji.get_random": ["emoji:read:random"],
    "emoji.get_by_description": ["emoji:read:by_description"],
    "emoji.get_count": ["emoji:read:list"],
    "emoji.get_emotions": ["emoji:read:list"],
    "emoji.get_all": ["emoji:read:list"],
    "emoji.get_info": ["emoji:read:list"],
    "emoji.register": ["emoji:write:register"],
    "emoji.delete": ["emoji:write:delete"],

    # frequency.*
    "frequency.get_current_talk_value": ["system:read:frequency"],
    "frequency.set_adjust": ["system:write:frequency"],
    "frequency.get_adjust": ["system:read:frequency"],

    # tool.*
    "tool.get_definitions": ["system:read:tool_definitions"],

    # api.*
    "api.call": ["plugin:execute:api"],
    "api.get": ["plugin:execute:api"],
    "api.list": ["plugin:execute:api"],
    "api.replace_dynamic": ["plugin:execute:api"],

    # component.*
    "component.get_all_plugins": ["plugin:read:list"],
    "component.get_plugin_info": ["plugin:read:info"],
    "component.get_plugin_config_schema": ["plugin:read:info"],
    "component.update_plugin_config": ["plugin:write:config"],
    "component.list_loaded_plugins": ["plugin:read:list"],
    "component.list_registered_plugins": ["plugin:read:list"],
    "component.enable": ["plugin:write:enable"],
    "component.disable": ["plugin:write:enable"],
    "component.load_plugin": ["plugin:execute:load"],
    "component.unload_plugin": ["plugin:execute:load"],
    "component.reload_plugin": ["plugin:execute:load"],

    # knowledge.*
    "knowledge.search": ["system:execute:knowledge"],

    # statistics.*
    "statistics.local.models": ["system:read:statistics"],
    "statistics.local.model_trend": ["system:read:statistics"],
    "statistics.local.token_trend": ["system:read:statistics"],
    "statistics.local.token_distribution": ["system:read:statistics"],
    "statistics.local.message_trend": ["system:read:statistics"],
    "statistics.local.tool_trend": ["system:read:statistics"],
    "statistics.local.online_time_trend": ["system:read:statistics"],

    # render.*
    "render.html2png": ["system:execute:render"],
}


class ScopeVocabulary:
    """Scope 词汇表 — 细粒度授权的权威定义。"""

    version: str = "1.0.0"
    scopes: frozenset[ScopeEntry] = _SCOPE_ENTRIES

    _SCOPE_INDEX: dict[str, ScopeEntry] = {e.scope: e for e in _SCOPE_ENTRIES}

    @classmethod
    def validate(cls, scope_str: str) -> bool:
        """校验 scope 是否在词汇表中。O(1) 查找。"""
        return scope_str in cls._SCOPE_INDEX

    @classmethod
    def lookup(cls, scope_str: str) -> ScopeEntry:
        """查找 scope 条目。不存在抛出 KeyError。"""
        return cls._SCOPE_INDEX[scope_str]

    @classmethod
    def map_capability(cls, cap: str) -> list[str]:
        """将旧 capability 映射为新 scope 列表。不存在返回空列表。"""
        return _CAPABILITY_MAP.get(cap, [])