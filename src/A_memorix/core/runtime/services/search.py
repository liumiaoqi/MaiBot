from __future__ import annotations

from typing import Any, Callable, Coroutine, Dict, List, Optional, Sequence

from ...retrieval import RetrievalResult
from ...utils.aggregate_query_service import AggregateQueryService
from ...utils.episode_retrieval_service import EpisodeRetrievalService
from ...utils.search_execution_service import SearchExecutionRequest, SearchExecutionResult, SearchExecutionService
from ...utils.time_parser import format_timestamp, parse_query_datetime_to_timestamp
from .hit_filter import HitFilterService
from .types import KernelSearchRequest, NormalizedSearchTimeWindow

from src.common.logger import get_logger

logger = get_logger("A_Memorix.SearchService")


class SearchService:

    def __init__(
        self,
        *,
        hit_filter_service: HitFilterService,
        get_retriever: Callable[[], Any],
        get_episode_retriever: Callable[[], Optional[EpisodeRetrievalService]],
        get_aggregate_query_service: Callable[[], Optional[AggregateQueryService]],
        get_threshold_filter: Callable[[], Any],
        build_runtime_config: Callable[[], Dict[str, Any]],
        is_chat_filtered: Callable[..., bool],
        get_config_value: Callable[[str, Any], Any],
    ) -> None:
        self._hit_filter_service = hit_filter_service
        self._get_retriever = get_retriever
        self._get_episode_retriever = get_episode_retriever
        self._get_aggregate_query_service = get_aggregate_query_service
        self._get_threshold_filter = get_threshold_filter
        self._build_runtime_config = build_runtime_config
        self._is_chat_filtered = is_chat_filtered
        self._get_config_value = get_config_value

    async def search_memory(self, request: KernelSearchRequest) -> Dict[str, Any]:
        if self._is_chat_filtered(
            respect_filter=request.respect_filter,
            stream_id=request.chat_id,
            group_id=request.group_id,
            user_id=request.user_id,
        ):
            return {"summary": "", "hits": [], "filtered": True}

        retriever = self._get_retriever()
        episode_retriever = self._get_episode_retriever()
        aggregate_query_service = self._get_aggregate_query_service()
        assert retriever is not None
        assert episode_retriever is not None
        assert aggregate_query_service is not None

        mode = str(request.mode or "search").strip().lower() or "search"
        query = str(request.query or "").strip()
        limit = max(1, int(request.limit or 5))
        shared_chat_ids = tuple(str(item or "").strip() for item in request.shared_chat_ids if str(item or "").strip())
        scoped_limit = self._scoped_search_limit(limit, chat_id=request.chat_id, shared_chat_ids=shared_chat_ids)
        supported_modes = {"search", "time", "hybrid", "episode", "aggregate"}
        if mode not in supported_modes:
            return {
                "summary": "",
                "hits": [],
                "error": (
                    f"不支持的检索模式: {mode}（仅支持 search/time/hybrid/episode/aggregate，"
                    "semantic 已移除）"
                ),
            }
        try:
            time_window = self._normalize_search_time_window(request.time_start, request.time_end)
        except ValueError as exc:
            return {"summary": "", "hits": [], "error": str(exc)}

        if mode == "episode":
            rows = await self._episode_query_for_chat_scope(
                query=query,
                top_k=scoped_limit,
                time_from=time_window.numeric_start,
                time_to=time_window.numeric_end,
                person=request.person_id or None,
                chat_id=request.chat_id,
                shared_chat_ids=shared_chat_ids,
            )
            hits = self._hit_filter_service.filter_episode_hits([self._episode_hit(row) for row in rows])
            hits = self._hit_filter_service.filter_hits_by_chat_scope(hits, request.chat_id, shared_chat_ids)
            if request.respect_filter:
                hits = self._hit_filter_service.filter_hits_by_retrieval_type_scope(
                    hits,
                    current_stream_id=request.chat_id,
                    current_group_id=request.group_id,
                    current_user_id=request.user_id,
                )
            hits = hits[:limit]
            return {"summary": self._summary(hits), "hits": hits}

        if mode == "aggregate":
            payload = await aggregate_query_service.execute(
                query=query,
                top_k=scoped_limit,
                mix=True,
                mix_top_k=scoped_limit,
                time_from=time_window.query_start,
                time_to=time_window.query_end,
                search_runner=lambda: self._aggregate_search(query, scoped_limit, request),
                time_runner=lambda: self._aggregate_time(query, scoped_limit, request, time_window),
                episode_runner=lambda: self._aggregate_episode(query, scoped_limit, request, time_window),
            )
            hits = [dict(item) for item in payload.get("mixed_results", []) if isinstance(item, dict)]
            for item in hits:
                item.setdefault("metadata", {})
            filtered = self._filter_hits(hits, request.person_id)
            filtered = self._hit_filter_service.filter_user_visible_hits(filtered)
            filtered = self._hit_filter_service.filter_hits_by_chat_scope(filtered, request.chat_id, shared_chat_ids)
            if request.respect_filter:
                filtered = self._hit_filter_service.filter_hits_by_retrieval_type_scope(
                    filtered,
                    current_stream_id=request.chat_id,
                    current_group_id=request.group_id,
                    current_user_id=request.user_id,
                )
            filtered = filtered[:limit]
            return {"summary": self._summary(filtered), "hits": filtered}

        query_type = mode
        runtime_config = self._build_runtime_config()
        result = await self._search_execution_for_chat_scope(
            caller="sdk_memory_kernel",
            query_type=query_type,
            query=query,
            top_k=scoped_limit,
            request=request,
            time_from=time_window.query_start,
            time_to=time_window.query_end,
            plugin_config=runtime_config,
            enforce_chat_filter=bool(request.respect_filter),
        )
        if not result.success:
            return {"summary": "", "hits": [], "error": result.error}
        if result.chat_filtered:
            return {"summary": "", "hits": [], "filtered": True}

        hits = [self._retrieval_result_hit(item) for item in result.results]
        filtered = self._filter_hits(hits, request.person_id)
        filtered = self._hit_filter_service.filter_user_visible_hits(filtered)
        filtered = self._hit_filter_service.filter_hits_by_chat_scope(filtered, request.chat_id, shared_chat_ids)
        if request.respect_filter:
            filtered = self._hit_filter_service.filter_hits_by_retrieval_type_scope(
                filtered,
                current_stream_id=request.chat_id,
                current_group_id=request.group_id,
                current_user_id=request.user_id,
            )
        filtered = filtered[:limit]
        return {"summary": self._summary(filtered), "hits": filtered}

    async def _aggregate_search(self, query: str, limit: int, request: KernelSearchRequest) -> Dict[str, Any]:
        shared_chat_ids = tuple(str(item or "").strip() for item in request.shared_chat_ids if str(item or "").strip())
        result = await self._search_execution_for_chat_scope(
            caller="sdk_memory_kernel.aggregate",
            query_type="search",
            query=query,
            top_k=limit,
            request=request,
            plugin_config=self._build_runtime_config(),
            enforce_chat_filter=False,
        )
        hits = [self._retrieval_result_hit(item) for item in result.results] if result.success else []
        hits = self._hit_filter_service.filter_hits_by_chat_scope(hits, request.chat_id, shared_chat_ids)
        return {"success": result.success, "results": hits, "count": len(hits), "query_type": "search", "error": result.error}

    async def _aggregate_time(
        self,
        query: str,
        limit: int,
        request: KernelSearchRequest,
        time_window: NormalizedSearchTimeWindow,
    ) -> Dict[str, Any]:
        shared_chat_ids = tuple(str(item or "").strip() for item in request.shared_chat_ids if str(item or "").strip())
        result = await self._search_execution_for_chat_scope(
            caller="sdk_memory_kernel.aggregate",
            query_type="time",
            query=query,
            top_k=limit,
            request=request,
            time_from=time_window.query_start,
            time_to=time_window.query_end,
            plugin_config=self._build_runtime_config(),
            enforce_chat_filter=False,
        )
        hits = [self._retrieval_result_hit(item) for item in result.results] if result.success else []
        hits = self._hit_filter_service.filter_hits_by_chat_scope(hits, request.chat_id, shared_chat_ids)
        return {"success": result.success, "results": hits, "count": len(hits), "query_type": "time", "error": result.error}

    async def _aggregate_episode(
        self,
        query: str,
        limit: int,
        request: KernelSearchRequest,
        time_window: NormalizedSearchTimeWindow,
    ) -> Dict[str, Any]:
        episode_retriever = self._get_episode_retriever()
        assert episode_retriever
        shared_chat_ids = tuple(str(item or "").strip() for item in request.shared_chat_ids if str(item or "").strip())
        rows = await self._episode_query_for_chat_scope(
            query=query,
            top_k=limit,
            time_from=time_window.numeric_start,
            time_to=time_window.numeric_end,
            person=request.person_id or None,
            chat_id=request.chat_id,
            shared_chat_ids=shared_chat_ids,
        )
        hits = self._hit_filter_service.filter_episode_hits([self._episode_hit(row) for row in rows])
        hits = self._hit_filter_service.filter_hits_by_chat_scope(hits, request.chat_id, shared_chat_ids)
        return {"success": True, "results": hits, "count": len(hits), "query_type": "episode"}

    async def _search_execution_for_chat_scope(
        self,
        *,
        caller: str,
        query_type: str,
        query: str,
        top_k: int,
        request: KernelSearchRequest,
        plugin_config: dict,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
        enforce_chat_filter: bool,
    ) -> SearchExecutionResult:
        allowed_chat_ids = self._resolve_allowed_chat_ids(request.chat_id, request.shared_chat_ids)
        if len(allowed_chat_ids) <= 1:
            search_source = self._chat_source_for_search_scope(request.chat_id, request.shared_chat_ids)
            return await self._search_execution_once(
                caller=caller,
                query_type=query_type,
                query=query,
                top_k=top_k,
                request=request,
                plugin_config=plugin_config,
                source=search_source,
                time_from=time_from,
                time_to=time_to,
                enforce_chat_filter=enforce_chat_filter,
            )

        scoped_results: List[RetrievalResult] = []
        errors: List[str] = []
        chat_filtered = False
        for chat_id in sorted(allowed_chat_ids):
            result = await self._search_execution_once(
                caller=caller,
                query_type=query_type,
                query=query,
                top_k=top_k,
                request=request,
                plugin_config=plugin_config,
                source=self._chat_source(chat_id),
                time_from=time_from,
                time_to=time_to,
                enforce_chat_filter=False,
            )
            if result.chat_filtered:
                chat_filtered = True
            if not result.success:
                if result.error:
                    errors.append(result.error)
                continue
            scoped_results.extend(result.results)

        merged_results = self._dedupe_ranked_items(scoped_results, limit=top_k)
        return SearchExecutionResult(
            success=bool(merged_results) or not errors,
            error="; ".join(dict.fromkeys(errors)),
            query_type=query_type,
            query=query,
            top_k=top_k,
            time_from=time_from,
            time_to=time_to,
            person=str(request.person_id or "") or None,
            source=None,
            results=merged_results,
            chat_filtered=chat_filtered and not merged_results,
        )

    async def _search_execution_once(
        self,
        *,
        caller: str,
        query_type: str,
        query: str,
        top_k: int,
        request: KernelSearchRequest,
        plugin_config: dict,
        source: Optional[str],
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
        enforce_chat_filter: bool,
    ) -> SearchExecutionResult:
        return await SearchExecutionService.execute(
            retriever=self._get_retriever(),
            threshold_filter=self._get_threshold_filter(),
            plugin_config=plugin_config,
            request=SearchExecutionRequest(
                caller=caller,
                stream_id=str(request.chat_id or "") or None,
                group_id=str(request.group_id or "") or None,
                user_id=str(request.user_id or "") or None,
                query_type=query_type,
                query=query,
                top_k=top_k,
                time_from=time_from,
                time_to=time_to,
                person=str(request.person_id or "") or None,
                source=source,
                use_threshold=True,
                enable_ppr=bool(self._get_config_value("retrieval.enable_ppr", True)),
            ),
            enforce_chat_filter=enforce_chat_filter,
            reinforce_access=True,
        )

    async def _episode_query_for_chat_scope(
        self,
        *,
        query: str,
        top_k: int,
        time_from: Optional[float],
        time_to: Optional[float],
        person: Optional[str],
        chat_id: str,
        shared_chat_ids: Sequence[str] = (),
    ) -> List[Any]:
        episode_retriever = self._get_episode_retriever()
        assert episode_retriever is not None
        allowed_chat_ids = self._resolve_allowed_chat_ids(chat_id, shared_chat_ids)
        if len(allowed_chat_ids) <= 1:
            return await episode_retriever.query(
                query=query,
                top_k=top_k,
                time_from=time_from,
                time_to=time_to,
                person=person,
                source=self._chat_source_for_search_scope(chat_id, shared_chat_ids),
            )

        rows: List[Any] = []
        for allowed_chat_id in sorted(allowed_chat_ids):
            rows.extend(
                await episode_retriever.query(
                    query=query,
                    top_k=top_k,
                    time_from=time_from,
                    time_to=time_to,
                    person=person,
                    source=self._chat_source(allowed_chat_id),
                )
            )
        return self._dedupe_ranked_items(rows, limit=top_k)

    @staticmethod
    def _chat_source(chat_id: str) -> Optional[str]:
        clean = str(chat_id or "").strip()
        return f"chat_summary:{clean}" if clean else None

    @classmethod
    def _chat_source_for_search_scope(cls, chat_id: str, shared_chat_ids: Sequence[str] = ()) -> Optional[str]:
        allowed_chat_ids = cls._resolve_allowed_chat_ids(chat_id, shared_chat_ids)
        if len(allowed_chat_ids) > 1:
            return None
        return cls._chat_source(chat_id)

    @staticmethod
    def _scoped_search_limit(limit: int, *, chat_id: str, shared_chat_ids: Sequence[str] = ()) -> int:
        safe_limit = max(1, int(limit or 5))
        allowed_chat_ids = SearchService._resolve_allowed_chat_ids(chat_id, shared_chat_ids)
        if not allowed_chat_ids:
            return safe_limit
        multiplier = max(5, len(allowed_chat_ids) * 5)
        return min(50, max(safe_limit, safe_limit * multiplier))

    @classmethod
    def _resolve_allowed_chat_ids(cls, chat_id: str, shared_chat_ids: Sequence[str] = ()) -> set[str]:
        allowed_chat_ids = {str(item or "").strip() for item in shared_chat_ids if str(item or "").strip()}
        clean_chat_id = str(chat_id or "").strip()
        if clean_chat_id:
            allowed_chat_ids.add(clean_chat_id)
        return allowed_chat_ids

    @staticmethod
    def _rank_score_from_item(item: Any) -> float:
        if isinstance(item, dict):
            raw_score = item.get("score", item.get("final_score", item.get("relevance", 0.0)))
        else:
            raw_score = getattr(item, "score", 0.0)
        try:
            return float(raw_score or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _dedupe_ranked_items(cls, items: Sequence[Any], *, limit: int) -> List[Any]:
        ranked: Dict[str, Any] = {}
        for index, item in enumerate(items):
            if isinstance(item, dict):
                item_hash = str(item.get("hash", "") or "").strip()
                item_type = str(item.get("type", "") or "").strip()
                content = str(item.get("content", "") or "").strip()
            else:
                item_hash = str(getattr(item, "hash_value", "") or "").strip()
                item_type = str(getattr(item, "result_type", "") or "").strip()
                content = str(getattr(item, "content", "") or "").strip()
            key = item_hash or f"{item_type}:{content}"
            if not key:
                key = f"item:{index}"
            current = ranked.get(key)
            if current is None or cls._rank_score_from_item(item) > cls._rank_score_from_item(current):
                ranked[key] = item
        return sorted(ranked.values(), key=cls._rank_score_from_item, reverse=True)[: max(1, int(limit or 5))]

    @staticmethod
    def _time_meta(timestamp: Optional[float], time_start: Optional[float], time_end: Optional[float]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if timestamp is not None:
            payload["event_time"] = float(timestamp)
        if time_start is not None:
            payload["event_time_start"] = float(time_start)
        if time_end is not None:
            payload["event_time_end"] = float(time_end)
        if payload:
            payload["time_granularity"] = "minute"
            payload["time_confidence"] = 0.95
        return payload

    @classmethod
    def _normalize_search_time_bound(cls, value: Any, *, is_end: bool) -> tuple[Optional[float], Optional[str]]:
        if value in {None, ""}:
            return None, None
        if isinstance(value, (int, float)):
            ts = float(value)
            return ts, format_timestamp(ts)

        text = str(value or "").strip()
        if not text:
            return None, None

        numeric = cls._optional_float(text)
        if numeric is not None:
            return numeric, format_timestamp(numeric)

        try:
            ts = parse_query_datetime_to_timestamp(text, is_end=is_end)
        except ValueError as exc:
            raise ValueError(f"时间参数错误: {exc}") from exc
        return ts, text

    @classmethod
    def _normalize_search_time_window(cls, time_start: Any, time_end: Any) -> NormalizedSearchTimeWindow:
        numeric_start, query_start = cls._normalize_search_time_bound(time_start, is_end=False)
        numeric_end, query_end = cls._normalize_search_time_bound(time_end, is_end=True)
        if numeric_start is not None and numeric_end is not None and numeric_start > numeric_end:
            raise ValueError("时间参数错误: time_start 不能晚于 time_end")
        return NormalizedSearchTimeWindow(
            numeric_start=numeric_start,
            numeric_end=numeric_end,
            query_start=query_start,
            query_end=query_end,
        )

    @staticmethod
    def _retrieval_result_hit(item: RetrievalResult) -> Dict[str, Any]:
        payload = item.to_dict()
        return {
            "hash": payload.get("hash", ""),
            "content": payload.get("content", ""),
            "score": payload.get("score", 0.0),
            "type": payload.get("type", ""),
            "source": payload.get("source", ""),
            "metadata": payload.get("metadata", {}) or {},
        }

    @staticmethod
    def _episode_hit(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "episode",
            "episode_id": str(row.get("episode_id", "") or ""),
            "title": str(row.get("title", "") or ""),
            "content": str(row.get("summary", "") or ""),
            "score": float(row.get("lexical_score", 0.0) or 0.0),
            "source": "episode",
            "metadata": {
                "participants": row.get("participants", []) or [],
                "keywords": row.get("keywords", []) or [],
                "source": row.get("source"),
                "event_time_start": row.get("event_time_start"),
                "event_time_end": row.get("event_time_end"),
            },
        }

    @staticmethod
    def _summary(hits: Sequence[Dict[str, Any]]) -> str:
        if not hits:
            return ""
        lines = []
        for index, item in enumerate(hits[:5], start=1):
            content = str(item.get("content", "") or "").strip().replace("\n", " ")
            lines.append(f"{index}. {(content[:120] + '...') if len(content) > 120 else content}")
        return "\n".join(lines)

    @staticmethod
    def _filter_hits(hits: List[Dict[str, Any]], person_id: str) -> List[Dict[str, Any]]:
        if not person_id:
            return hits
        filtered = []
        for item in hits:
            metadata = item.get("metadata", {}) or {}
            if person_id in (metadata.get("person_ids", []) or []):
                filtered.append(item)
                continue
            if person_id and person_id in str(item.get("content", "") or ""):
                filtered.append(item)
        return filtered or hits

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value in {None, ""}:
            return None
        try:
            return float(value)
        except Exception:
            return None