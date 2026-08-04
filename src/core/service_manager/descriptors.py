"""组件描述符与依赖声明 — 33 个组件的 ServiceDescriptor + DependencyRelation。

identifier 与 main.py 中 @startup_item 的 name 完全一致。
"""


from src.core.service_manager.types import (
    DependencyKind,
    DependencyRelation,
    HealthCheckMode,
    ServiceDescriptor,
)


def get_service_descriptors() -> list[ServiceDescriptor]:
    """返回全部 33 个组件的 ServiceDescriptor。"""
    return [
        # 阶段 0: CONFIG_LOAD
        ServiceDescriptor(
            identifier="config_manager",
            display_name="配置管理器",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="config_validator",
            display_name="配置校验器",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        # 阶段 1: INFRASTRUCTURE
        ServiceDescriptor(
            identifier="file_watcher",
            display_name="文件监视器",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="tool_record_vacuum",
            display_name="工具记录清理",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        # 阶段 2: CORE_SERVICES
        ServiceDescriptor(
            identifier="agent_registry",
            display_name="智能体注册表",
            health_mode=HealthCheckMode.ACTIVE_PROBE,
            core_readiness_flag="agent_thinking_ready",
            oom_protected=True,
        ),
        ServiceDescriptor(
            identifier="session_submodules",
            display_name="会话子模块",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="chat_manager_adapter",
            display_name="聊天管理器",
            health_mode=HealthCheckMode.ACTIVE_PROBE,
            core_readiness_flag="message_pipeline_ready",
            oom_protected=True,
        ),
        ServiceDescriptor(
            identifier="replyer_port",
            display_name="回复器",
            health_mode=HealthCheckMode.ACTIVE_PROBE,
            core_readiness_flag="reply_capability_ready",
            oom_protected=True,
        ),
        ServiceDescriptor(
            identifier="image_port",
            display_name="图像服务",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="runtime_port",
            display_name="运行时端口",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="model_config_port",
            display_name="模型配置端口",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="llm_service_port",
            display_name="LLM服务",
            health_mode=HealthCheckMode.ACTIVE_PROBE,
        ),
        ServiceDescriptor(
            identifier="message_ingestion_port",
            display_name="消息接入端口",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="person_info_port",
            display_name="人物信息端口",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="bot_config_port",
            display_name="机器人配置端口",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="chat_config_port",
            display_name="聊天配置端口",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="app_config_port",
            display_name="应用配置端口",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="event_bus_port",
            display_name="事件总线",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="prompt_manager",
            display_name="提示词管理器",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="message_port_v2",
            display_name="消息端口V2",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        # 阶段 3: SUBSYSTEMS
        ServiceDescriptor(
            identifier="plugin_runtime",
            display_name="插件运行时",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="ipc_bridge_port",
            display_name="IPC桥接端口",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="plugin_runtime_v2",
            display_name="插件运行时V2",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="a_memorix",
            display_name="记忆服务",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
            oom_protected=True,
        ),
        ServiceDescriptor(
            identifier="emoji_manager",
            display_name="表情管理器",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="model_config_port_inject",
            display_name="模型配置注入",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        # 阶段 4: SESSION_RESTORE
        ServiceDescriptor(
            identifier="session_lifecycle",
            display_name="会话生命周期",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="memory_automation",
            display_name="记忆自动化",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        # 阶段 5: READY
        ServiceDescriptor(
            identifier="message_handlers",
            display_name="消息处理器",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="on_start_event",
            display_name="启动事件",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="webui_server",
            display_name="WebUI服务器",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="scheduled_tasks",
            display_name="定时任务",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
        ServiceDescriptor(
            identifier="interaction_scheduler",
            display_name="交互调度器",
            health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
        ),
    ]


def get_dependency_relations() -> tuple[DependencyRelation, ...]:
    """返回关键运行时依赖关系。

    强依赖：被依赖方停止时，依赖方必须级联停止
    弱依赖：被依赖方停止时，依赖方降级而非停止
    """
    return (
        # 回复器强依赖消息管道和智能体
        DependencyRelation("replyer_port", "chat_manager_adapter", DependencyKind.STRONG),
        DependencyRelation("replyer_port", "agent_registry", DependencyKind.STRONG),
        # 消息处理器强依赖消息管道和回复器
        DependencyRelation("message_handlers", "chat_manager_adapter", DependencyKind.STRONG),
        DependencyRelation("message_handlers", "replyer_port", DependencyKind.STRONG),
        # 消息接入强依赖消息管道
        DependencyRelation("message_ingestion_port", "chat_manager_adapter", DependencyKind.STRONG),
        # 交互调度器强依赖消息处理器
        DependencyRelation("interaction_scheduler", "message_handlers", DependencyKind.STRONG),
        # 会话生命周期强依赖消息管道
        DependencyRelation("session_lifecycle", "chat_manager_adapter", DependencyKind.STRONG),
        # 记忆自动化弱依赖记忆服务
        DependencyRelation("memory_automation", "a_memorix", DependencyKind.WEAK),
        # 表情管理器弱依赖LLM服务
        DependencyRelation("emoji_manager", "llm_service_port", DependencyKind.WEAK),
        # 插件弱依赖LLM服务
        DependencyRelation("plugin_runtime", "llm_service_port", DependencyKind.WEAK),
        DependencyRelation("plugin_runtime_v2", "llm_service_port", DependencyKind.WEAK),
    )
