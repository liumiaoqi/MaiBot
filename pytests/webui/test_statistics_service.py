from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from src.services import statistics_service
from src.webui.schemas.statistics import DashboardData, StatisticsSummary, TimeSeriesData


class _Result:
    def __init__(self, *, first_value: Any = None, all_values: list[Any] | None = None) -> None:
        self._first_value = first_value
        self._all_values = all_values or []

    def first(self) -> Any:
        return self._first_value

    def all(self) -> list[Any]:
        return self._all_values


class _Session:
    def __init__(self, results: list[_Result]) -> None:
        self._results = results

    def exec(self, statement: Any) -> _Result:
        del statement
        return self._results.pop(0)


class _MemoryStore:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    def __getitem__(self, item: str) -> Any:
        return self.store.get(item)

    def __setitem__(self, key: str, value: Any) -> None:
        self.store[key] = value


def _patch_session_results(monkeypatch: pytest.MonkeyPatch, results: list[_Result]) -> list[bool]:
    auto_commit_calls: list[bool] = []

    @contextmanager
    def _fake_get_db_session(auto_commit: bool = True) -> Iterator[_Session]:
        auto_commit_calls.append(auto_commit)
        yield _Session([results.pop(0)])

    monkeypatch.setattr(statistics_service, "get_db_session", _fake_get_db_session)
    return auto_commit_calls


def _patch_session_result_group(monkeypatch: pytest.MonkeyPatch, results: list[_Result]) -> list[bool]:
    auto_commit_calls: list[bool] = []

    @contextmanager
    def _fake_get_db_session(auto_commit: bool = True) -> Iterator[_Session]:
        auto_commit_calls.append(auto_commit)
        yield _Session(results)

    monkeypatch.setattr(statistics_service, "get_db_session", _fake_get_db_session)
    return auto_commit_calls


def _build_dashboard_data(total_requests: int = 1) -> DashboardData:
    return DashboardData(
        summary=StatisticsSummary(total_requests=total_requests),
        model_stats=[],
        hourly_data=[],
        daily_data=[],
        recent_activity=[],
    )


def _build_dashboard_data_with_time_series() -> DashboardData:
    return DashboardData(
        summary=StatisticsSummary(total_requests=1),
        model_stats=[],
        hourly_data=[
            TimeSeriesData(timestamp="2026-05-06T10:00:00", requests=0, cost=0.0, tokens=0),
            TimeSeriesData(timestamp="2026-05-06T11:00:00", requests=2, cost=0.5, tokens=50),
            TimeSeriesData(timestamp="2026-05-06T12:00:00", requests=0, cost=0.0, tokens=0),
        ],
        daily_data=[
            TimeSeriesData(timestamp="2026-05-05T00:00:00", requests=0, cost=0.0, tokens=0),
            TimeSeriesData(timestamp="2026-05-06T00:00:00", requests=3, cost=0.7, tokens=70),
        ],
        recent_activity=[],
    )


def test_shared_fetch_queries_disable_auto_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 5, 6, 12, 0, 0)
    online_record = SimpleNamespace(start_timestamp=now - timedelta(minutes=5), end_timestamp=now)
    usage_record = SimpleNamespace(
        timestamp=now,
        request_type="chat.reply",
        model_api_provider_name="provider",
        model_assign_name="chat-main",
        model_name="gpt-a",
        prompt_tokens=10,
        completion_tokens=5,
        cost=0.01,
        time_cost=1.2,
    )
    message_record = SimpleNamespace(timestamp=now, message_id="msg-1")
    tool_record = SimpleNamespace(timestamp=now, tool_name="reply")
    auto_commit_calls = _patch_session_results(
        monkeypatch,
        [
            _Result(all_values=[online_record]),
            _Result(all_values=[usage_record]),
            _Result(all_values=[message_record]),
            _Result(all_values=[tool_record]),
        ],
    )

    online_ranges = statistics_service.fetch_online_time_since(now - timedelta(hours=1))
    usage_records = statistics_service.fetch_model_usage_since(now - timedelta(hours=1))
    messages = statistics_service.fetch_messages_since(now - timedelta(hours=1))
    tool_records = statistics_service.fetch_tool_records_since(now - timedelta(hours=1))

    assert online_ranges == [(online_record.start_timestamp, online_record.end_timestamp)]
    assert usage_records == [
        {
            "timestamp": now,
            "request_type": "chat.reply",
            "model_api_provider_name": "provider",
            "model_assign_name": "chat-main",
            "model_name": "gpt-a",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "cost": 0.01,
            "time_cost": 1.2,
        }
    ]
    assert messages == [message_record]
    assert tool_records == [tool_record]
    assert auto_commit_calls == [False, False, False, False]


def test_get_earliest_statistics_time_uses_min_valid_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    fallback_time = datetime(2026, 5, 6, 12, 0, 0)
    earliest_time = datetime(2026, 5, 1, 8, 30, 0)
    auto_commit_calls = _patch_session_result_group(
        monkeypatch,
        [
            _Result(first_value=datetime(2026, 5, 3, 9, 0, 0)),
            _Result(first_value=earliest_time),
            _Result(first_value=None),
            _Result(first_value=datetime(2026, 5, 2, 9, 0, 0)),
        ],
    )

    result = statistics_service.get_earliest_statistics_time(fallback_time)

    assert result == earliest_time
    assert auto_commit_calls == [False]


def test_get_earliest_statistics_time_falls_back_when_query_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    fallback_time = datetime(2026, 5, 6, 12, 0, 0)

    @contextmanager
    def _fake_get_db_session(auto_commit: bool = True) -> Iterator[_Session]:
        del auto_commit
        raise RuntimeError("database unavailable")
        yield _Session([])

    monkeypatch.setattr(statistics_service, "get_db_session", _fake_get_db_session)

    assert statistics_service.get_earliest_statistics_time(fallback_time) == fallback_time


def test_dashboard_statistics_cache_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    memory_store = _MemoryStore()
    now = datetime.now()
    dashboard_data = _build_dashboard_data(total_requests=7)
    monkeypatch.setattr(statistics_service, "local_storage", memory_store)

    statistics_service.store_dashboard_statistics_cache({24: dashboard_data}, generated_at=now)
    cached_data = statistics_service.get_cached_dashboard_statistics(24)

    assert cached_data is not None
    assert cached_data.summary.total_requests == 7


def test_dashboard_statistics_cache_stores_sparse_time_series(monkeypatch: pytest.MonkeyPatch) -> None:
    memory_store = _MemoryStore()
    generated_at = datetime(2026, 5, 6, 12, 0, 0)
    dashboard_data = _build_dashboard_data_with_time_series()
    monkeypatch.setattr(statistics_service, "local_storage", memory_store)

    statistics_service.store_dashboard_statistics_cache({2: dashboard_data}, generated_at=generated_at)

    raw_cache = memory_store[statistics_service.DASHBOARD_STATISTICS_CACHE_KEY]
    raw_entry = raw_cache["entries"]["2"]
    assert raw_entry["sparse"] is True
    assert raw_entry["hourly_data"] == [
        {"timestamp": "2026-05-06T11:00:00", "requests": 2, "cost": 0.5, "tokens": 50}
    ]
    assert raw_entry["daily_data"] == [
        {"timestamp": "2026-05-06T00:00:00", "requests": 3, "cost": 0.7, "tokens": 70}
    ]

    cached_data = statistics_service.get_cached_dashboard_statistics(2, max_age_seconds=10**9)
    assert cached_data is not None
    assert [item.timestamp for item in cached_data.hourly_data] == [
        "2026-05-06T10:00:00",
        "2026-05-06T11:00:00",
        "2026-05-06T12:00:00",
    ]
    assert cached_data.hourly_data[0].requests == 0
    assert cached_data.hourly_data[1].requests == 2
    assert cached_data.hourly_data[2].requests == 0


@pytest.mark.asyncio
async def test_get_dashboard_statistics_prefers_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    memory_store = _MemoryStore()
    dashboard_data = _build_dashboard_data(total_requests=9)
    monkeypatch.setattr(statistics_service, "local_storage", memory_store)
    statistics_service.store_dashboard_statistics_cache({24: dashboard_data}, generated_at=datetime.now())

    async def _fail_compute_dashboard_statistics(hours: int = 24) -> DashboardData:
        del hours
        raise AssertionError("cache should be used")

    monkeypatch.setattr(statistics_service, "compute_dashboard_statistics", _fail_compute_dashboard_statistics)

    result = await statistics_service.get_dashboard_statistics(24)

    assert result.summary.total_requests == 9


@pytest.mark.asyncio
async def test_get_dashboard_statistics_returns_empty_when_cache_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    memory_store = _MemoryStore()
    monkeypatch.setattr(statistics_service, "local_storage", memory_store)

    async def _fail_compute_dashboard_statistics(hours: int = 24) -> DashboardData:
        del hours
        raise AssertionError("dashboard API should not compute fallback data")

    monkeypatch.setattr(statistics_service, "compute_dashboard_statistics", _fail_compute_dashboard_statistics)

    result = await statistics_service.get_dashboard_statistics(24)

    assert result.summary.total_requests == 0
    assert result.model_stats == []


@pytest.mark.asyncio
async def test_get_summary_statistics_aggregates_database_and_message_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    start_time = datetime(2026, 5, 6, 10, 0, 0)
    end_time = datetime(2026, 5, 6, 12, 0, 0)
    online_records = [
        SimpleNamespace(
            start_timestamp=start_time - timedelta(minutes=30),
            end_timestamp=start_time + timedelta(minutes=30),
        ),
        SimpleNamespace(
            start_timestamp=start_time + timedelta(hours=1),
            end_timestamp=end_time + timedelta(minutes=30),
        ),
    ]
    auto_commit_calls = _patch_session_results(
        monkeypatch,
        [
            _Result(first_value=(3, 1.5, 900, 2.5)),
            _Result(all_values=online_records),
        ],
    )

    def _fake_count_messages(**kwargs: Any) -> int:
        return 5 if kwargs.get("has_reply_to") is None else 2

    monkeypatch.setattr(statistics_service, "count_messages", _fake_count_messages)

    summary = await statistics_service.get_summary_statistics(start_time, end_time)

    assert summary.total_requests == 3
    assert summary.total_cost == 1.5
    assert summary.total_tokens == 900
    assert summary.avg_response_time == 2.5
    assert summary.online_time == 5400
    assert summary.total_messages == 5
    assert summary.total_replies == 2
    assert summary.cost_per_hour == pytest.approx(1.0)
    assert summary.tokens_per_hour == pytest.approx(600.0)
    assert auto_commit_calls == [False, False]


@pytest.mark.asyncio
async def test_get_model_statistics_groups_by_display_model_name(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 5, 6, 12, 0, 0)
    records = [
        SimpleNamespace(
            model_assign_name="chat-main",
            model_name="gpt-a",
            cost=0.4,
            total_tokens=100,
            time_cost=2.0,
        ),
        SimpleNamespace(
            model_assign_name="chat-main",
            model_name="gpt-a",
            cost=0.6,
            total_tokens=200,
            time_cost=4.0,
        ),
        SimpleNamespace(
            model_assign_name=None,
            model_name="gpt-b",
            cost=0.2,
            total_tokens=50,
            time_cost=0.0,
        ),
    ]
    _patch_session_results(monkeypatch, [_Result(all_values=records)])

    stats = await statistics_service.get_model_statistics(now - timedelta(hours=24))

    assert [item.model_name for item in stats] == ["chat-main", "gpt-b"]
    assert stats[0].request_count == 2
    assert stats[0].total_cost == pytest.approx(1.0)
    assert stats[0].total_tokens == 300
    assert stats[0].avg_response_time == pytest.approx(3.0)
    assert stats[1].avg_response_time == 0.0
