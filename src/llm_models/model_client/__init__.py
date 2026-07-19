from importlib import import_module

from src.core.protocols import ModelConfigPort

_CLIENT_MODULE_BY_TYPE: dict[str, str] = {
    "openai": ".openai_client",
    "gemini": ".gemini_client",
}

_LOADED_CLIENT_TYPES: set[str] = set()

_model_config_port: ModelConfigPort | None = None


def set_model_config_port(port: ModelConfigPort) -> None:
    """注入模块级 ModelConfigPort。"""
    global _model_config_port
    _model_config_port = port


def ensure_client_type_loaded(client_type: str) -> None:
    if client_type in _LOADED_CLIENT_TYPES:
        return
    module_name = _CLIENT_MODULE_BY_TYPE.get(client_type)
    if not module_name:
        return
    import_module(module_name, package=__name__)
    _LOADED_CLIENT_TYPES.add(client_type)


def ensure_configured_clients_loaded() -> None:
    if _model_config_port is None:
        return  # 模块导入时端口可能未注入，延迟到首次请求时
    for provider in _model_config_port.get_model_config().api_providers:
        ensure_client_type_loaded(provider.client_type)
