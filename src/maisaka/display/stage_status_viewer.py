"""Maisaka 阶段状态看板查看器。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import json
import os
import sys
import time
import traceback


def _clear_screen() -> None:
    os.system("cls" if sys.platform.startswith("win") else "clear")


def _load_state(state_file: Path) -> dict[str, Any]:
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _render(state: dict[str, Any]) -> str:
    entries = state.get("entries")
    if not isinstance(entries, list):
        entries = []

    lines = ["Maisaka 阶段看板", "=" * 72, ""]
    if not entries:
        lines.append("当前没有活跃会话。")
        return "\n".join(lines)

    entries = sorted(
        [entry for entry in entries if isinstance(entry, dict)],
        key=lambda item: str(item.get("session_name") or item.get("session_id") or ""),
    )
    now = time.time()
    for entry in entries:
        session_name = str(entry.get("session_name") or entry.get("session_id") or "").strip() or "unknown"
        session_id = str(entry.get("session_id") or "").strip()
        stage = str(entry.get("stage") or "").strip() or "未知"
        detail = str(entry.get("detail") or "").strip() or "-"
        round_text = str(entry.get("round_text") or "").strip()
        agent_state = str(entry.get("agent_state") or "").strip() or "-"
        stage_started_at = float(entry.get("stage_started_at") or now)
        elapsed = max(0.0, now - stage_started_at)

        lines.append(f"Chat: {session_name}")
        if session_id and session_id != session_name:
            lines.append(f"ID: {session_id}")
        lines.append(f"阶段: {stage}")
        if round_text:
            lines.append(f"轮次: {round_text}")
        lines.append(f"详情: {detail}")
        lines.append(f"状态: {agent_state}")
        lines.append(f"阶段耗时: {elapsed:.1f}s")
        lines.append("-" * 72)

    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        return 1

    state_file = Path(sys.argv[1]).resolve()
    log_file = state_file.with_name("maisaka_stage_status_viewer.log")
    last_render = ""
    while True:
        try:
            state = _load_state(state_file)
            if not state.get("enabled", False):
                return 0

            rendered = _render(state)
            if rendered != last_render:
                _clear_screen()
                print(rendered, flush=True)
                last_render = rendered
            time.sleep(0.5)
        except Exception:
            log_file.write_text(traceback.format_exc(), encoding="utf-8")
            time.sleep(3)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
