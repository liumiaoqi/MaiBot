"""核心适配器层 — 唯一允许导入组件具体类的地方。

适配器将组件的具体实现包装为核心 Protocol 接口，
核心模块只依赖 Protocol，不直接导入组件。
"""

from src.core.adapters.agent_config_port import get_agent_config_provider, reset_agent_config_provider  # noqa: F401
from src.core.adapters.chat_manager_adapter import ChatManagerAdapter
from src.core.adapters.control_message_adapter import ControlMessageAdapter
from src.core.adapters.core_readiness_port import CoreReadinessPortAdapter
from src.core.adapters.llm_service_port import get_llm_service, reset_llm_service  # noqa: F401
from src.core.adapters.memory_service import get_memory_service_port, reset_memory_service_port  # noqa: F401
from src.core.adapters.message_ingestion_port import get_message_ingestion_port, reset_message_ingestion_port  # noqa: F401
from src.core.adapters.notice_classifier import NapCatNoticeClassifier
from src.core.adapters.person_info_port import PersonInfoPortAdapter  # noqa: F401
from src.core.person_info_port_registry import get_person_info_port, reset_person_info_port  # noqa: F401
from src.core.adapters.resource_limit_adapter import ResourceLimitAdapter  # noqa: F401
from src.core.adapters.routing_adapter import ChatManagerRoutingAdapter
from src.core.adapters.runtime_registry import HeartflowRuntimeRegistry
from src.core.adapters.service_manager_adapter import ServiceManagerAdapter
from src.core.adapters.watchdog_adapter import WatchdogAdapter
from src.core.bot_config_port_registry import get_bot_config_port  # noqa: F401
from src.core.chat_config_port_registry import get_chat_config_port  # noqa: F401
from src.core.app_config_port_registry import get_app_config_port  # noqa: F401

__all__ = [
    "AMemorixMemoryServicePort",
    "ChatManagerAdapter",
    "ControlMessageAdapter",
    "CoreReadinessPortAdapter",
    "ChatManagerRoutingAdapter",
    "HeartflowRuntimeRegistry",
    "ServiceManagerAdapter",
    "WatchdogAdapter",
    "get_agent_config_provider",
    "get_llm_service",
    "get_message_ingestion_port",
    "get_person_info_port",
    "NapCatNoticeClassifier",
    "PersonInfoPortAdapter",
    "reset_agent_config_provider",
    "reset_llm_service",
    "reset_message_ingestion_port",
    "reset_person_info_port",
    "get_bot_config_port",
    "get_chat_config_port",
    "get_app_config_port",
]
