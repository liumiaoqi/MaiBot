from __future__ import annotations

from enum import Enum
from typing import Any

from src.common.logger import get_logger

from ..connectionist.enums import TimeOfDay, Valence
from ..connectionist.memory_field import MemoryField
from ..connectionist.models import Trace
from ..connectionist.models import _time_of_day_from_timestamp

logger = get_logger("MigrationAdapter")


class MigrationPhase(str, Enum):
    LEGACY_ONLY = "legacy_only"
    DUAL_WRITE = "dual_write"
    DUAL_READ = "dual_read"
    DATA_MIGRATION = "data_migration"
    NEW_INDEPENDENT = "new_independent"


class MigrationAdapter:
    """迁移适配层：五阶段渐进式迁移"""

    _PHASE_ORDER: list[MigrationPhase] = [
        MigrationPhase.LEGACY_ONLY,
        MigrationPhase.DUAL_WRITE,
        MigrationPhase.DUAL_READ,
        MigrationPhase.DATA_MIGRATION,
        MigrationPhase.NEW_INDEPENDENT,
    ]

    def __init__(self, memory_field: MemoryField, phase: MigrationPhase = MigrationPhase.LEGACY_ONLY) -> None:
        self._memory_field = memory_field
        self._phase = phase

    @property
    def phase(self) -> MigrationPhase:
        return self._phase

    def set_phase(self, phase: MigrationPhase) -> None:
        current_idx = self._PHASE_ORDER.index(self._phase)
        target_idx = self._PHASE_ORDER.index(phase)
        if target_idx > current_idx + 1:
            logger.warning(
                f"跳过阶段：{self._phase.value} -> {phase.value}，"
                f"跳过了 {self._PHASE_ORDER[current_idx + 1:target_idx]}"
            )
        logger.info(f"迁移阶段切换: {self._phase.value} -> {phase.value}")
        self._phase = phase

    def advance_phase(self) -> MigrationPhase:
        if not self.can_advance():
            raise ValueError(f"已在最终阶段 {self._phase.value}，无法推进")
        current_idx = self._PHASE_ORDER.index(self._phase)
        next_phase = self._PHASE_ORDER[current_idx + 1]
        self._phase = next_phase
        logger.info(f"迁移阶段推进: {self._PHASE_ORDER[current_idx].value} -> {next_phase.value}")
        return next_phase

    def can_advance(self) -> bool:
        return self._phase != MigrationPhase.NEW_INDEPENDENT

    def should_observe(self) -> bool:
        return self._phase in (
            MigrationPhase.DUAL_WRITE,
            MigrationPhase.DUAL_READ,
            MigrationPhase.DATA_MIGRATION,
            MigrationPhase.NEW_INDEPENDENT,
        )

    def should_recall(self) -> bool:
        return self._phase in (
            MigrationPhase.DUAL_READ,
            MigrationPhase.DATA_MIGRATION,
            MigrationPhase.NEW_INDEPENDENT,
        )

    def should_ingest_legacy(self) -> bool:
        return self._phase in (
            MigrationPhase.LEGACY_ONLY,
            MigrationPhase.DUAL_WRITE,
            MigrationPhase.DUAL_READ,
            MigrationPhase.DATA_MIGRATION,
        )

    def should_search_legacy(self) -> bool:
        return self._phase in (
            MigrationPhase.LEGACY_ONLY,
            MigrationPhase.DUAL_WRITE,
            MigrationPhase.DUAL_READ,
            MigrationPhase.DATA_MIGRATION,
        )

    def is_new_independent(self) -> bool:
        return self._phase == MigrationPhase.NEW_INDEPENDENT