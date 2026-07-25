"""Session Token 签发服务。

签发一次性 session_token，绑定 plugin_id，握手后立即失效。
纯内存存储，Host 重启后全部 token 失效。
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from src.common.logger import get_logger

logger = get_logger("plugin_runtime_v2.scope.token_service")


@dataclass
class _TokenEntry:
    plugin_id: str
    created_at: float
    used: bool = False


class TokenService:
    """Session Token 签发/验证/清理服务。"""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._tokens: dict[str, _TokenEntry] = {}

    def issue(self, plugin_id: str) -> str:
        """签发一次性 session_token，绑定 plugin_id。

        Returns:
            32 字节 urlsafe base64 编码的 token 字符串。
        """
        token = secrets.token_urlsafe(32)
        self._tokens[token] = _TokenEntry(
            plugin_id=plugin_id,
            created_at=time.time(),
        )
        logger.info("Token 已签发: plugin=%s", plugin_id)
        return token

    def validate(self, token: str) -> tuple[bool, str]:
        """验证 token 有效性。

        验证通过后立即删除 token（一次性使用）。
        过期或已使用的 token 返回 (False, "")。

        Returns:
            (valid, plugin_id) — valid=False 时 plugin_id 为空字符串。
        """
        entry = self._tokens.get(token)
        if entry is None:
            logger.warning("Token 验证失败: 未知 token")
            return False, ""

        if entry.used:
            logger.warning("Token 验证失败: token 已被使用")
            del self._tokens[token]
            return False, ""

        if time.time() - entry.created_at > self._ttl:
            logger.warning("Token 验证失败: token 已过期")
            del self._tokens[token]
            return False, ""

        plugin_id = entry.plugin_id
        del self._tokens[token]
        logger.info("Token 验证成功: plugin=%s", plugin_id)
        return True, plugin_id

    def validate_session(self, token: str) -> tuple[bool, str]:
        """可重复验证 session_token（不删除 token）。

        用于 SDK RPC 调用时的身份校验。
        Connect 握手用 validate()（一次性），SDK RPC 用 validate_session()（可重复）。

        Returns:
            (valid, plugin_id) — valid=False 时 plugin_id 为空字符串。
        """
        entry = self._tokens.get(token)
        if entry is None:
            return False, ""
        if entry.used:
            return False, ""
        if time.time() - entry.created_at > self._ttl:
            return False, ""
        return True, entry.plugin_id

    def cleanup_expired(self) -> int:
        """清理过期 token，返回清理数量。"""
        now = time.time()
        expired = [
            t for t, e in self._tokens.items()
            if now - e.created_at > self._ttl
        ]
        for t in expired:
            del self._tokens[t]
        if expired:
            logger.debug("清理 %d 个过期 token", len(expired))
        return len(expired)
