from __future__ import annotations

from typing import Any, Optional

from src.common.logger import get_logger
from src.core.types import MemorySearchResult, MemoryWriteResult

from ..connectionist.memory_field import MemoryField
from ..connectionist.models import ObserveResult
from .migration_adapter import MigrationAdapter, MigrationPhase
from .translator import ConnectionistTranslator

logger = get_logger("MigrationRouter")


class MigrationRouter:
    """迁移感知路由：根据迁移阶段将请求路由到分类学或连接主义"""

    def __init__(
        self,
        migration_adapter: MigrationAdapter,
        memory_field: MemoryField,
        kernel: Any,
        translator: ConnectionistTranslator,
        coerce_search_result: Any = None,
        coerce_write_result: Any = None,
    ) -> None:
        self._adapter = migration_adapter
        self._memory_field = memory_field
        self._kernel = kernel
        self._translator = translator
        self._coerce_search_result = coerce_search_result
        self._coerce_write_result = coerce_write_result

    async def search(self, query: str, *, agent_id: str = "", **kwargs) -> MemorySearchResult:
        phase = self._adapter.phase

        if phase in (MigrationPhase.LEGACY_ONLY, MigrationPhase.DUAL_WRITE):
            return await self._legacy_search(query, **kwargs)

        if phase == MigrationPhase.DUAL_READ:
            legacy_result = await self._legacy_search(query, **kwargs)
            seeds = self._translator.query_to_seeds(query, self._memory_field._concept_index)
            try:
                recall_items = self._memory_field.recall(seeds, agent_id=agent_id)
                connectionist_result = self._translator.recall_to_search_result(recall_items, query)
                logger.info(
                    f"DUAL_READ 差异: 分类学 {len(legacy_result.hits)} 条, "
                    f"连接主义 {len(connectionist_result.hits)} 条"
                )
            except Exception as e:
                logger.warning(f"DUAL_READ 连接主义 recall 失败: {e}")
            return legacy_result

        seeds = self._translator.query_to_seeds(query, self._memory_field._concept_index)
        recall_items = self._memory_field.recall(seeds, agent_id=agent_id)
        return self._translator.recall_to_search_result(recall_items, query)

    async def get_person_profile(
        self, person_id: str, *, agent_id: str = "", limit: int = 4
    ) -> Optional[dict[str, Any]]:
        phase = self._adapter.phase

        if phase in (MigrationPhase.LEGACY_ONLY, MigrationPhase.DUAL_WRITE):
            return await self._kernel.get_person_profile(person_id=person_id, limit=limit)

        if phase == MigrationPhase.DUAL_READ:
            legacy_profile = await self._kernel.get_person_profile(person_id=person_id, limit=limit)
            try:
                profile_view = await self._memory_field.derive_profile(person_id, agent_id)
                logger.info(
                    f"DUAL_READ 画像差异: 分类学 evidence={len(legacy_profile.get('evidence', [])) if legacy_profile else 0}, "
                    f"连接主义 associations={len(profile_view.associations)}"
                )
            except Exception as e:
                logger.warning(f"DUAL_READ 连接主义 derive_profile 失败: {e}")
            return legacy_profile

        profile_view = await self._memory_field.derive_profile(person_id, agent_id)
        return self._translator.profile_view_to_dict(profile_view)

    async def ingest_text(self, text: str, **kwargs) -> MemoryWriteResult:
        phase = self._adapter.phase

        if phase == MigrationPhase.LEGACY_ONLY:
            return await self._legacy_ingest(text, **kwargs)

        if phase in (MigrationPhase.DUAL_WRITE, MigrationPhase.DUAL_READ, MigrationPhase.DATA_MIGRATION):
            legacy_result = await self._legacy_ingest(text, **kwargs)
            try:
                await self._memory_field.observe(
                    text=text,
                    source_id=kwargs.get("source_id", ""),
                    session_id=kwargs.get("session_id", ""),
                )
            except Exception as e:
                logger.warning(f"连接主义 observe 失败（不影响分类学写入）: {e}")
            return legacy_result

        observe_result = await self._memory_field.observe(
            text=text,
            source_id=kwargs.get("source_id", ""),
            session_id=kwargs.get("session_id", ""),
        )
        return self._observe_to_write_result(observe_result)

    async def build_profile_injection_text(self, raw_text: str, *, agent_id: str = "") -> str:
        if self._adapter.phase == MigrationPhase.NEW_INDEPENDENT:
            profile_view = await self._memory_field.derive_profile(raw_text, agent_id)
            return self._translator.profile_view_to_injection_text(profile_view)
        from src.A_memorix.host_service import a_memorix_host_service
        return a_memorix_host_service.build_profile_injection_text(raw_text)

    async def _legacy_search(self, query: str, **kwargs) -> MemorySearchResult:
        from ..runtime.services.types import KernelSearchRequest
        request = KernelSearchRequest(
            query=query,
            limit=kwargs.get("limit", 5),
            mode=kwargs.get("mode", "search"),
            chat_id=kwargs.get("chat_id", ""),
            person_id=kwargs.get("person_id", ""),
            time_start=kwargs.get("time_start"),
            time_end=kwargs.get("time_end"),
            respect_filter=kwargs.get("respect_filter", True),
            user_id=kwargs.get("user_id", ""),
            group_id=kwargs.get("group_id", ""),
        )
        raw = await self._kernel.search_memory(request)
        if self._coerce_search_result is not None:
            return self._coerce_search_result(raw)
        from src.services.memory_service import MemoryService
        return MemoryService._coerce_search_result(raw)

    async def _legacy_ingest(self, text: str, **kwargs) -> MemoryWriteResult:
        raw = await self._kernel.ingest_text(
            external_id=kwargs.get("external_id", ""),
            source_type=kwargs.get("source_type", ""),
            text=text,
            chat_id=kwargs.get("chat_id", ""),
            person_ids=kwargs.get("person_ids"),
            participants=kwargs.get("participants"),
            timestamp=kwargs.get("timestamp"),
            time_start=kwargs.get("time_start"),
            time_end=kwargs.get("time_end"),
            tags=kwargs.get("tags"),
            metadata=kwargs.get("metadata"),
            entities=kwargs.get("entities"),
            relations=kwargs.get("relations"),
            respect_filter=kwargs.get("respect_filter", True),
            user_id=kwargs.get("user_id", ""),
            group_id=kwargs.get("group_id", ""),
        )
        if self._coerce_write_result is not None:
            return self._coerce_write_result(raw)
        from src.services.memory_service import MemoryService
        return MemoryService._coerce_write_result(raw)

    @staticmethod
    def _observe_to_write_result(result: ObserveResult) -> MemoryWriteResult:
        trace_ids = []
        for mr in result.memory_results:
            if mr.remembered:
                trace_ids.append(mr.agent_id)
        return MemoryWriteResult(
            success=True,
            stored_ids=trace_ids,
        )
