from typing import Any, Optional

from src.common.logger import get_logger
from src.common.memory_utils import coerce_search_result
from src.common.memory_types import MemorySearchResult, MemoryWriteResult

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
        build_profile_injection_text_fn: Any = None,
    ) -> None:
        self._adapter = migration_adapter
        self._memory_field = memory_field
        self._kernel = kernel
        self._translator = translator
        self._build_profile_injection_text_fn = build_profile_injection_text_fn

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

    async def build_profile_injection_text(self, raw_text: str, *, agent_id: str = "") -> str:
        if self._adapter.phase == MigrationPhase.NEW_INDEPENDENT:
            profile_view = await self._memory_field.derive_profile(raw_text, agent_id)
            return self._translator.profile_view_to_injection_text(profile_view)
        if self._build_profile_injection_text_fn is not None:
            return self._build_profile_injection_text_fn(raw_text)
        raise RuntimeError("build_profile_injection_text 回调未注入，无法构建画像注入文本")

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
        return coerce_search_result(raw)

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
