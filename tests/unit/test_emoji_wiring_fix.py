"""emoji 接线修复测试 — 验证 main.py set_ports 调用 + emoji_manager 注销逻辑修正。

5 用例：set_ports 调用 / register 调用 / 注销方法纯净 / shutdown 幂等 / 生命周期对称。
前 3 用例用 grep/AST 静态验证；后 2 用例构造 emoji_manager 实例验证（mock port）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_MAIN_PY = Path("src/main.py")
_EMOJI_MANAGER_PY = Path("src/emoji_system/emoji_manager.py")


def _read_func_body(source: str, func_name: str) -> str:
    """提取指定函数体的源代码文本。"""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return ast.get_source_segment(source, node) or ""
    return ""


def _read_method_body(source: str, method_name: str) -> str:
    """提取指定方法体的源代码文本（类内方法）。"""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name:
            return ast.get_source_segment(source, node) or ""
    return ""


class TestEmojiWiringFix:
    """emoji 接线修复验证。"""

    def test_set_ports_called_in_load_emoji(self):
        """main.py _load_emoji 函数体含 set_ports 调用。"""
        source = _MAIN_PY.read_text(encoding="utf-8")
        body = _read_func_body(source, "_load_emoji")
        assert "set_ports" in body, "_load_emoji 函数体未含 set_ports 调用"

    def test_register_callback_called(self):
        """main.py _load_emoji 函数体含 _register_reload_callback 调用。"""
        source = _MAIN_PY.read_text(encoding="utf-8")
        body = _read_func_body(source, "_load_emoji")
        assert "_register_reload_callback" in body, "_load_emoji 函数体未含 _register_reload_callback 调用"

    def test_unregister_method_pure(self):
        """_unregister_reload_callback 方法体仅含 unregister 调用，无 register 调用。"""
        source = _EMOJI_MANAGER_PY.read_text(encoding="utf-8")
        body = _read_method_body(source, "_unregister_reload_callback")
        assert "unregister_reload_callback" in body, "方法体应含 unregister_reload_callback 调用"
        assert "_register_reload_callback" not in body, "方法体不应含 _register_reload_callback 调用（错位注册已删除）"
        assert "启动表情包管理器" not in body, "方法体不应含 logger.info('启动表情包管理器')（错位日志已删除）"

    def test_shutdown_idempotent(self):
        """连续调 shutdown() 2 次，第 2 次无副作用，_reload_callback_registered=False。"""
        from src.emoji_system.emoji_manager import EmojiManager

        mgr = EmojiManager.__new__(EmojiManager)
        mgr._reload_callback_registered = True
        mgr._app_config_port = MagicMock()
        mgr._app_config_port.unregister_reload_callback = MagicMock()
        mgr.reload_runtime_config = MagicMock()
        mgr._maintenance_wakeup_event = MagicMock()

        mgr.shutdown()
        assert mgr._reload_callback_registered is False

        mgr.shutdown()
        assert mgr._reload_callback_registered is False
        assert mgr._app_config_port.unregister_reload_callback.call_count == 1

    def test_lifecycle_symmetric(self):
        """启动注册的回调 == 关闭注销的回调（生命周期对称）。

        main.py 注册 emoji_manager.reload_runtime_config，shutdown() 注销 self.reload_runtime_config，
        两者应为同一方法引用。
        """
        from src.emoji_system.emoji_manager import EmojiManager

        mgr = EmojiManager.__new__(EmojiManager)
        mgr._app_config_port = MagicMock()
        mgr._app_config_port.register_reload_callback = MagicMock()
        mgr._app_config_port.unregister_reload_callback = MagicMock()
        mgr._reload_callback_registered = False
        mgr._maintenance_wakeup_event = MagicMock()

        mgr._register_reload_callback(mgr.reload_runtime_config)
        mgr._reload_callback_registered = True

        mgr.shutdown()
        registered_cb = mgr._app_config_port.register_reload_callback.call_args[0][0]
        unregistered_cb = mgr._app_config_port.unregister_reload_callback.call_args[0][0]
        assert registered_cb == unregistered_cb