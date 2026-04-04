"""独立的 WebUI 服务器。"""

from typing import Any, Optional

import asyncio
import sys

from uvicorn import Config
from uvicorn import Server as UvicornServer

from src.common.logger import get_logger
from src.common.utils.port_checker import assert_port_available, is_port_conflict_error, log_port_conflict
from src.config.startup_bindings import resolve_webui_bind_address
from src.webui.app import create_app, show_access_token

logger = get_logger("webui_server")


def _get_loaded_config_manager() -> Optional[Any]:
    config_module = sys.modules.get("src.config.config")
    if config_module is None:
        return None
    return getattr(config_module, "config_manager", None)


class _ASGIProxy:
    def __init__(self, app):
        self._app = app

    def set_app(self, app) -> None:
        self._app = app

    async def __call__(self, scope, receive, send):
        await self._app(scope, receive, send)


class WebUIServer:
    """独立的 WebUI 服务器"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8001):
        self.host = host
        self.port = port
        self._app = create_app(host=host, port=port, enable_static=True)
        self.app = _ASGIProxy(self._app)
        self._server: Optional[UvicornServer] = None
        self._reload_callback_registered = False

        show_access_token()
        self._maybe_register_reload_callback()

    def _maybe_register_reload_callback(self) -> None:
        if self._reload_callback_registered:
            return

        config_manager = _get_loaded_config_manager()
        if config_manager is None:
            return

        config_manager.register_reload_callback(self.reload_app)
        self._reload_callback_registered = True

    def _maybe_unregister_reload_callback(self) -> None:
        if not self._reload_callback_registered:
            return

        config_manager = _get_loaded_config_manager()
        if config_manager is None:
            return

        config_manager.unregister_reload_callback(self.reload_app)
        self._reload_callback_registered = False

    async def reload_app(self) -> None:
        self._app = create_app(host=self.host, port=self.port, enable_static=True)
        self.app.set_app(self._app)
        logger.info("WebUI 应用已热重载")

    async def start(self):
        """启动服务器"""
        self._maybe_register_reload_callback()
        assert_port_available(
            host=self.host,
            port=self.port,
            service_name="WebUI 服务器",
            logger=logger,
            config_hint="webui.port (config/bot_config.toml)",
            allow_reuse_addr=True,
        )

        config = Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_config=None,
            access_log=False,
        )
        self._server = UvicornServer(config=config)

        logger.info("🌐 WebUI 服务器启动中...")

        # 根据地址类型显示正确的访问地址
        if ":" in self.host:
            # IPv6 地址需要用方括号包裹
            logger.info(f"🌐 访问地址: http://[{self.host}]:{self.port}")
            if self.host == "::":
                logger.info(f"💡 IPv6 本机访问: http://[::1]:{self.port}")
                logger.info(f"💡 IPv4 本机访问: http://127.0.0.1:{self.port}")
            elif self.host == "::1":
                logger.info("💡 仅支持 IPv6 本地访问")
        else:
            # IPv4 地址
            logger.info(f"🌐 访问地址: http://{self.host}:{self.port}")
            if self.host == "0.0.0.0":
                logger.info(f"💡 本机访问: http://localhost:{self.port} 或 http://127.0.0.1:{self.port}")

        try:
            await self._server.serve()
        except OSError as e:
            if is_port_conflict_error(e):
                log_port_conflict(
                    logger,
                    service_name="WebUI 服务器",
                    host=self.host,
                    port=self.port,
                    config_hint="webui.port (config/bot_config.toml)",
                )
            else:
                logger.error(f"❌ WebUI 服务器启动失败 (网络错误): {e}")
            raise
        except Exception as e:
            logger.error(f"❌ WebUI 服务器运行错误: {e}", exc_info=True)
            raise
        finally:
            self._maybe_unregister_reload_callback()

    async def shutdown(self):
        """关闭服务器"""
        if self._server:
            logger.info("正在关闭 WebUI 服务器...")
            self._server.should_exit = True
            try:
                await asyncio.wait_for(self._server.shutdown(), timeout=3.0)
                logger.info("✅ WebUI 服务器已关闭")
            except asyncio.TimeoutError:
                logger.warning("⚠️ WebUI 服务器关闭超时")
            except Exception as e:
                logger.error(f"❌ WebUI 服务器关闭失败: {e}")
            finally:
                self._server = None


# 全局 WebUI 服务器实例
_webui_server = None


def get_webui_server() -> WebUIServer:
    """获取全局 WebUI 服务器实例"""
    global _webui_server
    if _webui_server is None:
        bind_address = resolve_webui_bind_address()
        _webui_server = WebUIServer(host=bind_address.host, port=bind_address.port)
    return _webui_server
