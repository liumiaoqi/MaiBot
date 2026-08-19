"""T2: M2 DriftFitnessCollector 测试。"""

from unittest.mock import MagicMock

import pytest

from src.maisaka.agent_autonomy.personality_drift.drift_fitness_collector import (
    DriftFitnessCollector,
)
from src.maisaka.relationship.level import RelationshipLevel, RelationshipSnapshot


def _mock_rm(score: float = 0.0, interaction_count: int = 0) -> MagicMock:
    rm = MagicMock()
    rm.get_relationship.return_value = RelationshipSnapshot(
        agent_id="agent1",
        user_id="user1",
        score=score,
        level=RelationshipLevel.from_score(score),
        interaction_count=interaction_count,
    )
    return rm


class TestFitnessWeighted:
    def test_weights_default(self):
        collector = DriftFitnessCollector(_mock_rm())
        w1, w2, w3, w4 = collector.weights
        assert w1 == pytest.approx(0.4)
        assert w2 == pytest.approx(0.2)
        assert w3 == pytest.approx(0.3)
        assert w4 == pytest.approx(0.0)

    def test_fitness_in_range(self):
        collector = DriftFitnessCollector(_mock_rm(score=500, interaction_count=100))
        fitness = collector.collect("agent1", "user1")
        assert 0.0 <= fitness <= 1.0

    def test_fitness_zero_interaction(self):
        collector = DriftFitnessCollector(_mock_rm(score=0, interaction_count=0))
        fitness = collector.collect("agent1", "user1")
        assert fitness >= 0.0

    def test_fitness_high_interaction(self):
        collector = DriftFitnessCollector(_mock_rm(score=1000, interaction_count=1000))
        fitness = collector.collect("agent1", "user1")
        assert fitness > 0.0


class TestQuietLiving:
    def test_low_interaction_high_uniqueness_positive_fitness(self):
        collector = DriftFitnessCollector(_mock_rm(score=0, interaction_count=0))
        fitness = collector.collect("agent1", "user1")
        assert fitness > 0.0


class TestEmotionReserved:
    def test_w4_default_zero(self):
        collector = DriftFitnessCollector(_mock_rm())
        assert collector.weights[3] == pytest.approx(0.0)

    def test_w4_configurable(self):
        collector = DriftFitnessCollector(_mock_rm(), {"w_emotion": 0.1})
        assert collector.weights[3] == pytest.approx(0.1)