from importlib import import_module

from src.common.logger import get_logger
from src.core.model_config_port_registry import get_model_config_port, register_model_config_port

logger = get_logger("llm_models.model_client")

_CLIENT_MODULE_BY_TYPE: dict[str, str] = {
    "openai": ".openai_client",
    "gemini": ".gemini_client",
}

_LOADED_CLIENT_TYPES: set[str] = set()

def set_model_config_port(port: object) -> None:
    """注入模块级 ModelConfigPort（委托全局注册点）。"""
    register_model_config_port(port)


def ensure_client_type_loaded(client_type: str) -> None:
    if client_type in _LOADED_CLIENT_TYPES:
        return
    module_name = _CLIENT_MODULE_BY_TYPE.get(client_type)
    if not module_name:
        logger.warning(f"ensure_client_type_loaded 未知 client_type 静默跳过: client_type={client_type!r}")
        return
    import_module(module_name, package=__name__)
    _LOADED_CLIENT_TYPES.add(client_type)


def ensure_configured_clients_loaded() -> None:
    port = get_model_config_port()
    if port is None:
        return  # 模块导入时端口可能未注入，延迟到首次请求时
    for provider in port.get_model_config().api_providers:
        ensure_client_type_loaded(provider.client_type)
