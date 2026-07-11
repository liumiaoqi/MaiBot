"""A_memorix 外部服务端口容器 — 由 host_service 在启动时注入到 SDKMemoryKernel。

A_memorix/core/ 内部模块禁止直接导入 MaiBot 服务层（src.services / src.config / src.common.database / src.llm_models），
必须通过此容器获取外部能力。host_service 是唯一允许导入 MaiBot 服务层的 A_memorix 模块。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class AMemorixServicePorts:
    llm_service: Any = None
    message_service: Any = None
    config_manager: Any = None
    db_session_factory: Callable[..., Any] | None = None
    db_person_info_model: Any = None
    llm_models_client_registry: Any = None
    llm_models_exceptions: Any = None
    llm_models_base_client: Any = None
    llm_data_models: Any = None

    def require_llm_service(self) -> Any:
        if self.llm_service is None:
            raise RuntimeError("A_memorix: LLM 服务未注入，无法执行需要 LLM 的操作")
        return self.llm_service

    def require_message_service(self) -> Any:
        if self.message_service is None:
            raise RuntimeError("A_memorix: 消息服务未注入")
        return self.message_service

    def require_config_manager(self) -> Any:
        if self.config_manager is None:
            raise RuntimeError("A_memorix: 配置管理器未注入")
        return self.config_manager

    def require_db_session_factory(self) -> Callable[..., Any]:
        if self.db_session_factory is None:
            raise RuntimeError("A_memorix: 数据库会话工厂未注入")
        return self.db_session_factory

    def require_db_person_info_model(self) -> Any:
        if self.db_person_info_model is None:
            raise RuntimeError("A_memorix: PersonInfo 模型未注入")
        return self.db_person_info_model