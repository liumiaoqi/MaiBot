"""Focus mode state shared by Maisaka chat runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Optional

import time

from src.chat.message_receive.chat_manager import BotChatSession
from src.config.config import global_config

FOCUS_SLOT_LIMIT = 1


@dataclass(slots=True)
class FocusTargetResolution:
    """Resolved chat target for focus-mode tools."""

    session: Optional[BotChatSession]
    error: str = ""


class FocusModeManager:
    """Track which chat sessions are currently allowed to make Maisaka decisions."""

    def __init__(self) -> None:
        self._focused_session_ids: list[str] = []
        self._last_cycle_at_by_session_id: dict[str, float] = {}
        self._last_read_at_by_session_id: dict[str, datetime] = {}

    def is_enabled(self) -> bool:
        """Return whether focus mode is enabled in the live chat config."""

        return bool(global_config.experimental.focus_mode)

    def get_focus_cool_time(self) -> float:
        """Return the focus wake-up cool time in seconds."""

        try:
            return max(1.0, float(global_config.experimental.focus_cool_time))
        except (TypeError, ValueError):
            return 120.0

    def _normalize_state(self) -> None:
        if not self.is_enabled():
            self._focused_session_ids.clear()
            return

        if len(self._focused_session_ids) > FOCUS_SLOT_LIMIT:
            del self._focused_session_ids[FOCUS_SLOT_LIMIT:]

    def is_in_focus_set(self, session_id: str) -> bool:
        """Return whether a session is explicitly occupying a focus slot."""

        self._normalize_state()
        normalized_session_id = str(session_id or "").strip()
        return bool(normalized_session_id) and normalized_session_id in self._focused_session_ids

    def can_decide(self, session_id: str) -> bool:
        """Return whether the session may run Maisaka decision loops right now."""

        if not self.is_enabled():
            return True
        return self.is_in_focus_set(session_id)

    def try_enter_focus(self, session_id: str) -> bool:
        """Try to put a session into the single active focus slot."""

        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return False
        if not self.is_enabled():
            return True

        self._normalize_state()
        if normalized_session_id in self._focused_session_ids:
            return True
        if len(self._focused_session_ids) >= FOCUS_SLOT_LIMIT:
            return False

        self._focused_session_ids.append(normalized_session_id)
        self._last_cycle_at_by_session_id[normalized_session_id] = time.time()
        return True

    def release_focus(self, session_id: str) -> None:
        """Remove a session from the focus set."""

        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return
        self._focused_session_ids = [
            focused_session_id
            for focused_session_id in self._focused_session_ids
            if focused_session_id != normalized_session_id
        ]
        self._last_cycle_at_by_session_id.pop(normalized_session_id, None)

    def switch_focus(self, from_session_id: str, to_session_id: str) -> str:
        """Move one focus slot from the current session to another existing session.

        Returns an empty string on success; otherwise returns a user-facing error.
        """

        if not self.is_enabled():
            return "focus_mode 未启用，不能切换关注聊天。"

        self._normalize_state()
        normalized_from_session_id = str(from_session_id or "").strip()
        normalized_to_session_id = str(to_session_id or "").strip()
        if not normalized_to_session_id:
            return "缺少要切换到的 chat_id。"
        if normalized_to_session_id in self._focused_session_ids:
            return f"chat_id={normalized_to_session_id} 已经处于关注状态，不能切换到已关注聊天。"
        if normalized_from_session_id not in self._focused_session_ids:
            return f"当前 chat_id={normalized_from_session_id} 不在关注状态，不能发起切换。"

        self.release_focus(normalized_from_session_id)
        self._focused_session_ids.append(normalized_to_session_id)
        self._last_cycle_at_by_session_id[normalized_to_session_id] = time.time()
        self._normalize_state()
        return ""

    def mark_cycle(self, session_id: str, when: Optional[float] = None) -> None:
        """Record that a focused chat has started a Maisaka loop."""

        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return
        self._last_cycle_at_by_session_id[normalized_session_id] = when if when is not None else time.time()

    def get_last_cycle_at(self, session_id: str) -> Optional[float]:
        """Return the last Maisaka loop start time for a focused chat."""

        return self._last_cycle_at_by_session_id.get(str(session_id or "").strip())

    def is_cycle_cool_time_elapsed(self, session_id: str, now: Optional[float] = None) -> bool:
        """Return whether a focused chat has exceeded the configured cool time."""

        if not self.is_enabled() or not self.is_in_focus_set(session_id):
            return False
        current_time = now if now is not None else time.time()
        last_cycle_at = self.get_last_cycle_at(session_id)
        if last_cycle_at is None:
            return True
        return current_time - last_cycle_at >= self.get_focus_cool_time()

    def mark_read(self, session_id: str, when: Optional[datetime] = None) -> None:
        """Record that Maisaka inspected messages from a chat."""

        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return
        self._last_read_at_by_session_id[normalized_session_id] = when or datetime.now()

    def get_last_read_at(self, session_id: str) -> Optional[datetime]:
        """Return the last time Maisaka read a chat in focus mode."""

        return self._last_read_at_by_session_id.get(str(session_id or "").strip())

    def resolve_session_from_args(
        self,
        arguments: dict[str, Any],
        available_sessions: Iterable[BotChatSession],
    ) -> FocusTargetResolution:
        """Resolve tool arguments to a currently running chat session."""

        session_by_id = {
            session.session_id: session
            for session in available_sessions
            if str(session.session_id or "").strip()
        }

        chat_id = str(arguments.get("chat_id") or arguments.get("session_id") or "").strip()
        if chat_id:
            session = session_by_id.get(chat_id)
            if session is None:
                return FocusTargetResolution(None, f"未找到 chat_id={chat_id} 对应的运行中已创建聊天。")
            return FocusTargetResolution(session)

        platform = str(arguments.get("platform") or "").strip()
        target_id = str(
            arguments.get("id")
            or arguments.get("target_id")
            or arguments.get("item_id")
            or ""
        ).strip()
        chat_type = str(arguments.get("type") or arguments.get("chat_type") or "").strip().lower()
        if not platform or not target_id or chat_type not in {"group", "private"}:
            return FocusTargetResolution(None, "需要提供 chat_id，或提供 platform、id、type(group/private) 组合。")

        matched_sessions: list[BotChatSession] = []
        for session in session_by_id.values():
            if str(session.platform or "").strip() != platform:
                continue
            session_target_id = session.group_id if chat_type == "group" else session.user_id
            if str(session_target_id or "").strip() == target_id:
                matched_sessions.append(session)
        if not matched_sessions:
            return FocusTargetResolution(
                None,
                f"未找到 platform={platform} id={target_id} type={chat_type} 对应的运行中已创建聊天。",
            )
        if len(matched_sessions) > 1:
            matched_ids = ", ".join(session.session_id for session in matched_sessions)
            return FocusTargetResolution(None, f"匹配到多个聊天，请改用 chat_id 指定：{matched_ids}")
        return FocusTargetResolution(matched_sessions[0])


focus_mode_manager = FocusModeManager()
