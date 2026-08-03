"""FusionRouter — 融合路由（MF-M-001/002，替代 MigrationRouter）。

按 FusionConfig.stage 路由：
- FUSION_FULL → 融合检索/统一画像
- FUSION_OFF → 原分类学路径（委托注入的 fallback 回调）
对外签名与 MigrationRouter 兼容（search / get_person_profile /
build_profile_injection_text）。
"""

from typing import Any, Awaitable, Callable, Optional

from .fusion_config import FusionConfig
from .spread_anchor_retriever import SpreadAnchorRetriever
from .unified_profile_service import UnifiedProfileService


class FusionRouter:
    """融合路由（替代 MigrationRouter 的 LEGACY_ONLY/DUAL_*/NEW_INDEPENDENT 切换）。"""

    def __init__(
        self,
        config: FusionConfig,
        retriever: SpreadAnchorRetriever,
        profile_service: UnifiedProfileService,
        legacy_search: Optional[Callable[..., Awaitable[Any]]] = None,
        legacy_get_person_profile: Optional[Callable[..., Awaitable[Any]]] = None,
        legacy_build_profile_injection_text: Optional[Callable[..., Awaitable[str]]] = None,
    ) -> None:
        """初始化。

        Args:
            config: 融合配置（stage 决定路由）
            retriever: 融合检索器
            profile_service: 统一画像服务
            legacy_*: 原路径回调（FUSION_OFF 时委托）
        """
        self._config = config
        self._retriever = retriever
        self._profile_service = profile_service
        self._legacy_search = legacy_search
        self._legacy_get_person_profile = legacy_get_person_profile
        self._legacy_build_profile_injection_text = legacy_build_profile_injection_text

    async def search(self, query: str, *, agent_id: str = "", **kwargs: Any) -> Any:
        """融合检索（FUSION_FULL 走扩散-锚定，否则原路径）。"""
        if self._config.is_full():
            result = self._retriever.retrieve(
                query,
                agent_id=agent_id,
                limit=max(1, int(kwargs.get("limit", 5) or 5)),
                max_depth=self._config.spread_depth,
            )
            return result
        if self._legacy_search is None:
            raise RuntimeError("FusionRouter: FUSION_OFF 需要 legacy_search 回调")
        return await self._legacy_search(query=query, agent_id=agent_id, **kwargs)

    async def get_person_profile(
        self,
        person_id: str,
        *,
        agent_id: str = "",
        limit: int = 4,
    ) -> dict[str, Any]:
        """统一画像（FUSION_FULL 走三元组，否则原路径）。"""
        if self._config.is_full():
            profile = await self._profile_service.get_person_profile(
                person_id, limit=max(1, int(limit or 4)),
            )
            return {
                "person_id": person_id,
                "evidence": [
                    {
                        "type": e.type,
                        "content": e.content,
                        "confidence": e.confidence,
                        "source_id": e.source_id,
                    }
                    for e in profile.evidence
                ],
                "associations": [
                    {
                        "concept_id": a.concept_id,
                        "weight": a.weight,
                        "valence": a.valence,
                        "perspective": a.perspective,
                    }
                    for a in profile.associations
                ],
                "valence": profile.valence,
            }
        if self._legacy_get_person_profile is None:
            raise RuntimeError("FusionRouter: FUSION_OFF 需要 legacy_get_person_profile 回调")
        return await self._legacy_get_person_profile(
            person_id=person_id, agent_id=agent_id, limit=limit,
        )

    async def build_profile_injection_text(
        self,
        raw_text: str,
        *,
        agent_id: str = "",
    ) -> str:
        """画像注入文本构建（融合路径：统一画像序列化）。"""
        if self._config.is_full():
            profile = await self._profile_service.get_person_profile(
                raw_text, limit=4,
            )
            lines = [f"- {e.content}" for e in profile.evidence]
            lines += [
                f"- 联想: {a.concept_id} (weight={a.weight:.2f})"
                for a in profile.associations
            ]
            return "\n".join(lines).strip()
        if self._legacy_build_profile_injection_text is None:
            raise RuntimeError("FusionRouter: FUSION_OFF 需要 legacy_build_profile_injection_text 回调")
        return await self._legacy_build_profile_injection_text(raw_text, agent_id=agent_id)
