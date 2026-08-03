"""MF-P0-003 验收：记忆检索限流配置可读且默认值合理。

对应 tasks.md 3.1/3.2：heuristic_memory_recall_min_interval_seconds 默认 60；
heuristic_memory_recall_rate_limit_rpm 默认 10 且范围为 1-60。
"""

import pytest

from src.core.types import AMemorixIntegrationSnapshot


def test_min_interval_default_is_60() -> None:
    """限流间隔默认 60s（允许 memory_driven 周期内多次检索）。"""
    snapshot = AMemorixIntegrationSnapshot()
    assert snapshot.heuristic_memory_recall_min_interval_seconds == 60


def test_rate_limit_rpm_default_is_10() -> None:
    """rpm 默认 10（每分钟最大检索次数）。"""
    snapshot = AMemorixIntegrationSnapshot()
    assert snapshot.heuristic_memory_recall_rate_limit_rpm == 10


def test_rate_limit_rpm_in_valid_range() -> None:
    """rpm 在 [1, 60] 范围（过小无意义，过大失去限流意义）。"""
    for rpm in (1, 10, 60):
        snapshot = AMemorixIntegrationSnapshot(heuristic_memory_recall_rate_limit_rpm=rpm)
        assert snapshot.heuristic_memory_recall_rate_limit_rpm == rpm


def test_rate_limit_rpm_overflow_rejected() -> None:
    """rpm 超出 60 被 pydantic 拒绝（official_configs 的 Field 校验生效）。"""
    from src.config.official_configs import AMemorixIntegrationConfig

    with pytest.raises(ValueError):
        AMemorixIntegrationConfig(heuristic_memory_recall_rate_limit_rpm=61)


def test_config_manager_reads_rate_limit() -> None:
    """official_configs 读取配置含 rpm 字段（默认值正确）。"""
    from src.config.official_configs import AMemorixIntegrationConfig

    ami = AMemorixIntegrationConfig()
    assert ami.heuristic_memory_recall_rate_limit_rpm == 10
    assert ami.heuristic_memory_recall_min_interval_seconds == 60
