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
    """迁移适配层：四阶段渐进式迁移"""

    def __init__(self, memory_field: MemoryField, phase: MigrationPhase = MigrationPhase.LEGACY_ONLY) -> None:
        self._memory_field = memory_field
        self._phase = phase

    @property
    def phase(self) -> MigrationPhase:
        return self._phase

    def set_phase(self, phase: MigrationPhase) -> None:
        logger.info(f"迁移阶段切换: {self._phase.value} -> {phase.value}")
        self._phase = phase

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