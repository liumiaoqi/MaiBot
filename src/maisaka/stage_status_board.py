"""Maisaka 阶段状态看板。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import json
import os
import subprocess
import sys
import threading
import time


class MaisakaStageStatusBoard:
    """维护 Maisaka 阶段状态，并在独立终端中展示。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._enabled = False
        self._entries: dict[str, dict[str, Any]] = {}
        self._viewer_process: Optional[subprocess.Popen[Any]] = None
        self._state_file = Path("temp") / "maisaka_stage_status.json"
        self._state_file.parent.mkdir(parents=True, exist_ok=True)

    def enable(self) -> None:
        """启用阶段状态看板。"""

        with self._lock:
            if self._enabled:
                return
            self._enabled = True
            self._write_state_locked()
            self._ensure_viewer_process_locked()

    def disable(self) -> None:
        """禁用阶段状态看板。"""

        with self._lock:
            self._enabled = False
            self._entries.clear()
            self._write_state_locked()
            process = self._viewer_process
            self._viewer_process = None

        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass

    def update(
        self,
        *,
        session_id: str,
        session_name: str,
        stage: str,
        detail: str = "",
        round_text: str = "",
        agent_state: str = "",
    ) -> None:
        """更新一个会话的阶段状态。"""

        with self._lock:
            if not self._enabled:
                return
            now = time.time()
            current = self._entries.get(session_id, {})
            previous_stage = str(current.get("stage") or "").strip()
            stage_started_at = float(current.get("stage_started_at") or now)
            if previous_stage != stage:
                stage_started_at = now
            self._entries[session_id] = {
                "session_id": session_id,
                "session_name": session_name,
                "stage": stage,
                "detail": detail,
                "round_text": round_text,
                "agent_state": agent_state,
                "stage_started_at": stage_started_at,
                "updated_at": now,
            }
            self._write_state_locked()

    def remove(self, session_id: str) -> None:
        """移除一个会话的阶段状态。"""

        with self._lock:
            if not self._enabled:
                return
            self._entries.pop(session_id, None)
            self._write_state_locked()

    def _write_state_locked(self) -> None:
        payload = {
            "enabled": self._enabled,
            "host_pid": os.getpid(),
            "updated_at": time.time(),
            "entries": list(self._entries.values()),
        }
        tmp_file = self._state_file.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_file.replace(self._state_file)

    def _ensure_viewer_process_locked(self) -> None:
        if not sys.platform.startswith("win"):
            return
        if self._viewer_process is not None and self._viewer_process.poll() is None:
            return
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        viewer_script = Path(__file__).resolve().with_name("stage_status_viewer.py")
        self._viewer_process = subprocess.Popen(
            [
                sys.executable,
                str(viewer_script),
                str(self._state_file.resolve()),
            ],
            creationflags=creationflags,
            cwd=str(Path.cwd()),
        )


_stage_board = MaisakaStageStatusBoard()


def enable_stage_status_board() -> None:
    """启用控制台阶段状态看板。"""

    _stage_board.enable()


def disable_stage_status_board() -> None:
    """禁用控制台阶段状态看板。"""

    _stage_board.disable()


def update_stage_status(
    *,
    session_id: str,
    session_name: str,
    stage: str,
    detail: str = "",
    round_text: str = "",
    agent_state: str = "",
) -> None:
    """更新控制台阶段状态。"""

    _stage_board.update(
        session_id=session_id,
        session_name=session_name,
        stage=stage,
        detail=detail,
        round_text=round_text,
        agent_state=agent_state,
    )


def remove_stage_status(session_id: str) -> None:
    """移除控制台阶段状态。"""

    _stage_board.remove(session_id)
