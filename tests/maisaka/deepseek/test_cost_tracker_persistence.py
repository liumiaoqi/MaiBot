"""CostTracker SQLite 持久化测试。

验证 record() 写库 + 重启后（新实例）从库加载，get_agent_cost() 返回重启前记录。
"""


import tempfile
from pathlib import Path

import pytest

from src.maisaka.deepseek.cost_tracker import CostTracker


@pytest.fixture
def temp_db_path():
    """提供临时 SQLite 路径，测试后清理。"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    try:
        if path.exists():
            path.unlink()
    except PermissionError:
        pass


class TestCostTrackerPersistence:
    """持久化验证。"""

    def test_record_survives_restart(self, temp_db_path):
        """record() 写入后重启 CostTracker 实例，get_agent_cost() 返回重启前记录。"""
        tracker1 = CostTracker(db_path=temp_db_path)
        tracker1.record(
            agent_id="agent_aria",
            task_type="replyer",
            model_tier="pro",
            input_tokens=100,
            output_tokens=200,
            cache_hit_tokens=50,
            cost=0.05,
        )

        tracker2 = CostTracker(db_path=temp_db_path)
        result = tracker2.get_agent_cost("agent_aria", period_days=30)

        assert result["total_cost"] == pytest.approx(0.05)
        assert result["total_input_tokens"] == 100
        assert result["total_output_tokens"] == 200
        assert result["total_cache_hit_tokens"] == 50

    def test_multiple_records_survive_restart(self, temp_db_path):
        """多条记录重启后全部存活。"""
        tracker1 = CostTracker(db_path=temp_db_path)
        for i in range(5):
            tracker1.record(
                agent_id="agent_test",
                task_type="replyer",
                model_tier="pro",
                input_tokens=10 * i,
                output_tokens=20 * i,
                cost=0.01 * i,
            )

        tracker2 = CostTracker(db_path=temp_db_path)
        result = tracker2.get_agent_cost("agent_test", period_days=30)

        assert result["total_input_tokens"] == sum(10 * i for i in range(5))
        assert result["total_output_tokens"] == sum(20 * i for i in range(5))
        assert result["total_cost"] == pytest.approx(sum(0.01 * i for i in range(5)))

    def test_monthly_report_after_restart(self, temp_db_path):
        """月度报告重启后数据完整。"""
        tracker1 = CostTracker(db_path=temp_db_path)
        tracker1.record(
            agent_id="agent_a", task_type="replyer", model_tier="pro",
            input_tokens=100, output_tokens=50, cost=0.03,
        )
        tracker1.record(
            agent_id="agent_b", task_type="planner", model_tier="think",
            input_tokens=200, output_tokens=100, cost=0.08,
        )

        tracker2 = CostTracker(db_path=temp_db_path)
        report = tracker2.get_monthly_report()

        assert "agent_a" in report["by_agent"]
        assert "agent_b" in report["by_agent"]
        assert report["by_agent"]["agent_a"]["cost"] == pytest.approx(0.03)
        assert report["by_agent"]["agent_b"]["cost"] == pytest.approx(0.08)