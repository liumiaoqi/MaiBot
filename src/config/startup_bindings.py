from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
import sys

import tomlkit


PROJECT_ROOT: Path = Path(__file__).parent.parent.parent.absolute().resolve()
CONFIG_DIR: Path = PROJECT_ROOT / "config"
BOT_CONFIG_PATH: Path = (CONFIG_DIR / "bot_config.toml").resolve().absolute()


@dataclass(frozen=True)
class BindAddress:
    """启动阶段使用的绑定地址。"""

    host: str
    port: int


_DEFAULT_MAIN_BIND_ADDRESS = BindAddress(host="127.0.0.1", port=8080)
_DEFAULT_WEBUI_BIND_ADDRESS = BindAddress(host="127.0.0.1", port=8001)


def _as_mapping(value: Any) -> Optional[Mapping[str, Any]]:
    return value if isinstance(value, Mapping) else None


def _normalize_host(value: Any, default_host: str) -> str:
    if not isinstance(value, str):
        return default_host

    normalized_host = value.strip()
    return normalized_host or default_host


def _normalize_port(value: Any, default_port: int) -> int:
    if isinstance(value, bool):
        return default_port

    try:
        normalized_port = int(value)
    except (TypeError, ValueError):
        return default_port

    if normalized_port <= 0 or normalized_port > 65535:
        return default_port
    return normalized_port


def _load_bootstrap_config_dict(config_path: Path = BOT_CONFIG_PATH) -> Dict[str, Any]:
    """读取启动阶段需要的最小配置，不依赖完整 ConfigManager。"""

    if not config_path.exists():
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as file_obj:
            config_data = tomlkit.load(file_obj).unwrap()
    except Exception:
        return {}

    if not isinstance(config_data, dict):
        return {}
    return config_data


def _resolve_bind_address_from_section(
    section: Mapping[str, Any],
    host_key: str,
    port_key: str,
    default_address: BindAddress,
) -> BindAddress:
    return BindAddress(
        host=_normalize_host(section.get(host_key), default_address.host),
        port=_normalize_port(section.get(port_key), default_address.port),
    )


def _get_loaded_global_config() -> Optional[Any]:
    config_module = sys.modules.get("src.config.config")
    if config_module is None:
        return None
    return getattr(config_module, "global_config", None)


def get_startup_main_bind_address(config_path: Path = BOT_CONFIG_PATH) -> BindAddress:
    """读取主程序消息服务绑定地址。"""

    config_data = _load_bootstrap_config_dict(config_path)
    maim_message_config = _as_mapping(config_data.get("maim_message")) or {}
    return _resolve_bind_address_from_section(
        maim_message_config,
        host_key="ws_server_host",
        port_key="ws_server_port",
        default_address=_DEFAULT_MAIN_BIND_ADDRESS,
    )


def get_startup_webui_bind_address(config_path: Path = BOT_CONFIG_PATH) -> BindAddress:
    """读取 WebUI 绑定地址。"""

    config_data = _load_bootstrap_config_dict(config_path)
    webui_config = _as_mapping(config_data.get("webui")) or {}
    return _resolve_bind_address_from_section(
        webui_config,
        host_key="host",
        port_key="port",
        default_address=_DEFAULT_WEBUI_BIND_ADDRESS,
    )


def resolve_main_bind_address(config_path: Path = BOT_CONFIG_PATH) -> BindAddress:
    """优先读取已初始化的主配置，否则回退到启动阶段配置读取。"""

    global_config = _get_loaded_global_config()
    if global_config is not None:
        return BindAddress(
            host=global_config.maim_message.ws_server_host,
            port=global_config.maim_message.ws_server_port,
        )
    return get_startup_main_bind_address(config_path)


def resolve_webui_bind_address(config_path: Path = BOT_CONFIG_PATH) -> BindAddress:
    """优先读取已初始化的主配置，否则回退到启动阶段配置读取。"""

    global_config = _get_loaded_global_config()
    if global_config is not None:
        return BindAddress(
            host=global_config.webui.host,
            port=global_config.webui.port,
        )
    return get_startup_webui_bind_address(config_path)
