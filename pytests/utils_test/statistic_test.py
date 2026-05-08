"""统计模块数据库会话行为测试。"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from types import ModuleType
from typing import Any, Callable, Iterator

import sys

import pytest

from src.chat.utils import statistic


class _DummyResult:
    """模拟 SQLModel 查询结果对象。"""

    def all(self) -> list[Any]:
        """返回空结果集。

        Returns:
            list[Any]: 空列表。
        """
        return []


class _DummySession:
    """模拟数据库 Session。"""

    def exec(self, statement: Any) -> _DummyResult:
        """执行查询语句并返回空结果。

        Args:
            statement: 待执行的查询语句。

        Returns:
            _DummyResult: 空结果对象。
        """
        del statement
        return _DummyResult()


def _build_fake_get_db_session(calls: list[bool]) -> Callable[[bool], Iterator[_DummySession]]:
    """构造一个记录 auto_commit 参数的假会话工厂。

    Args:
        calls: 用于记录每次调用 auto_commit 参数的列表。

    Returns:
        Callable[[bool], Iterator[_DummySession]]: 可替换 `get_db_session` 的上下文管理器工厂。
    """

    @contextmanager
    def _fake_get_db_session(auto_commit: bool = True) -> Iterator[_DummySession]:
        """记录会话参数并返回假 Session。

        Args:
            auto_commit: 是否启用自动提交。

        Yields:
            Iterator[_DummySession]: 假 Session 对象。
        """
        calls.append(auto_commit)
        yield _DummySession()

    return _fake_get_db_session


def _build_statistic_task() -> statistic.StatisticOutputTask:
    """构造一个最小可用的统计任务实例。

    Returns:
        statistic.StatisticOutputTask: 跳过 `__init__` 的测试实例。
    """
    task = statistic.StatisticOutputTask.__new__(statistic.StatisticOutputTask)
    task.name_mapping = {}
    return task


def _is_bot_self(platform: str, user_id: str) -> bool:
    """返回固定的非机器人身份判断结果。

    Args:
        platform: 平台名称。
        user_id: 用户 ID。

    Returns:
        bool: 始终返回 ``False``。
    """
    del platform
    del user_id
    return False


def test_statistic_read_queries_disable_auto_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """统计模块的纯读查询应关闭自动提交，避免 Session 退出后对象被 expire。"""
    calls: list[bool] = []
    now = datetime.now()
    task = _build_statistic_task()

    monkeypatch.setattr(statistic, "get_db_session", _build_fake_get_db_session(calls))

    utils_module = ModuleType("src.chat.utils.utils")
    utils_module.is_bot_self = _is_bot_self
    monkeypatch.setitem(sys.modules, "src.chat.utils.utils", utils_module)
    monkeypatch.setattr(statistic, "fetch_online_time_since", lambda query_start_time: [])
    monkeypatch.setattr(statistic, "fetch_model_usage_since", lambda query_start_time: [])
    monkeypatch.setattr(statistic, "fetch_messages_since", lambda query_start_time: [])
    monkeypatch.setattr(statistic, "fetch_tool_records_since", lambda query_start_time: [])

    task._collect_message_count_for_period([("last_hour", now - timedelta(hours=1))])
    task._collect_interval_data(now, hours=1, interval_minutes=60)
    task._collect_metrics_interval_data(now, hours=1, interval_hours=1)

    assert calls == []
