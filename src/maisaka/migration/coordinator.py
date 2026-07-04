"""插件迁移协调器。

管理5个插件的三阶段迁移状态：
  1. 未开始 (not_started)
  2. 共存 (coexistence) — 兼容层运行
  3. 替代 (replacement) — SDK 原生 API
  4. 已完成 (completed)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MigrationPhase(str, Enum):
    """迁移阶段。"""

    NOT_STARTED = "not_started"
    COEXISTENCE = "coexistence"
    REPLACEMENT = "replacement"
    COMPLETED = "completed"


@dataclass
class PluginMigrationState:
    """插件迁移状态。"""

    plugin_id: str
    plugin_name: str = ""
    current_phase: MigrationPhase = MigrationPhase.NOT_STARTED
    previous_phase: MigrationPhase = MigrationPhase.NOT_STARTED
    last_updated: float = field(default_factory=time.time)
    notes: str = ""


_MIGRATION_PLUGINS = [
    {"plugin_id": "time-awareness", "plugin_name": "时间感知", "superseded_by": "time_awareness模块"},
    {"plugin_id": "qq-user-memory", "plugin_name": "QQ用户记忆", "superseded_by": "A_Memorix+relationship模块"},
    {"plugin_id": "proactive-chat", "plugin_name": "主动对话", "superseded_by": "proactive模块"},
    {"plugin_id": "group-event-sensor", "plugin_name": "群事件感知", "superseded_by": "event_sensor模块"},
    {"plugin_id": "cross-chat-context", "plugin_name": "跨聊上下文", "superseded_by": "cross_chat模块"},
]

_PHASE_ORDER = [
    MigrationPhase.NOT_STARTED,
    MigrationPhase.COEXISTENCE,
    MigrationPhase.REPLACEMENT,
    MigrationPhase.COMPLETED,
]

_DEFAULT_STORE_PATH = Path("data/plugin_migration_states.jsonl")


class MigrationCoordinator:
    """插件迁移协调器。"""

    def __init__(self, store_path: Path | None = None) -> None:
        self._store_path = store_path or _DEFAULT_STORE_PATH
        self._states: dict[str, PluginMigrationState] = {}
        self._load_states()

        for plugin_info in _MIGRATION_PLUGINS:
            pid = plugin_info["plugin_id"]
            if pid not in self._states:
                self._states[pid] = PluginMigrationState(
                    plugin_id=pid,
                    plugin_name=plugin_info["plugin_name"],
                    current_phase=MigrationPhase.COMPLETED,
                    previous_phase=MigrationPhase.REPLACEMENT,
                    notes=f"功能已由主程序{plugin_info.get('superseded_by', '')}替代",
                )

    def get_all_states(self) -> list[PluginMigrationState]:
        """获取所有插件的迁移状态。"""
        return list(self._states.values())

    def get_state(self, plugin_id: str) -> PluginMigrationState | None:
        """获取指定插件的迁移状态。"""
        return self._states.get(plugin_id)

    def advance(self, plugin_id: str) -> PluginMigrationState | None:
        """推进指定插件的迁移阶段。"""
        state = self._states.get(plugin_id)
        if state is None:
            return None

        current_idx = _PHASE_ORDER.index(state.current_phase)
        if current_idx >= len(_PHASE_ORDER) - 1:
            logger.debug("插件已处于最终阶段: %s", plugin_id)
            return state

        state.previous_phase = state.current_phase
        state.current_phase = _PHASE_ORDER[current_idx + 1]
        state.last_updated = time.time()

        self._save_states()

        logger.info(
            "插件迁移推进: %s %s → %s",
            plugin_id,
            state.previous_phase.value,
            state.current_phase.value,
        )
        return state

    def rollback(self, plugin_id: str) -> PluginMigrationState | None:
        """回退指定插件的迁移阶段。"""
        state = self._states.get(plugin_id)
        if state is None:
            return None

        current_idx = _PHASE_ORDER.index(state.current_phase)
        if current_idx <= 0:
            logger.debug("插件已处于初始阶段: %s", plugin_id)
            return state

        state.previous_phase = state.current_phase
        state.current_phase = _PHASE_ORDER[current_idx - 1]
        state.last_updated = time.time()

        self._save_states()

        logger.info(
            "插件迁移回退: %s %s → %s",
            plugin_id,
            state.previous_phase.value,
            state.current_phase.value,
        )
        return state

    def _load_states(self) -> None:
        """从 JSONL 文件加载状态。"""
        if not self._store_path.exists():
            return

        try:
            with open(self._store_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        self._states[data["plugin_id"]] = PluginMigrationState(
                            plugin_id=data["plugin_id"],
                            plugin_name=data.get("plugin_name", ""),
                            current_phase=MigrationPhase(data.get("current_phase", "not_started")),
                            previous_phase=MigrationPhase(data.get("previous_phase", "not_started")),
                            last_updated=data.get("last_updated", time.time()),
                            notes=data.get("notes", ""),
                        )
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        except Exception as e:
            logger.warning("加载迁移状态失败: %s", e)

    def _save_states(self) -> None:
        """保存状态到 JSONL 文件。"""
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._store_path, "w", encoding="utf-8") as f:
                for state in self._states.values():
                    data = {
                        "plugin_id": state.plugin_id,
                        "plugin_name": state.plugin_name,
                        "current_phase": state.current_phase.value,
                        "previous_phase": state.previous_phase.value,
                        "last_updated": state.last_updated,
                        "notes": state.notes,
                    }
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error("保存迁移状态失败: %s", e)