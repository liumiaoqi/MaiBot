"""M3: 漂移循环核心——选择 + 经典梯度 + 进化笼子。与 VitalityManager 平级。

漂移算子 = 选择 + 经典梯度（exp53b 实证 +85.3%）。
回归力 3-4%（exp60 实测 6% 略强，调 3%）。
V2 增强：自我认知协方差（exp60c +54.7% > 全局共享 +52.6%），V1 用独立高斯。
"""

import random
from typing import TYPE_CHECKING

from src.common.logger import get_logger
from src.maisaka.agent.config import PersonalityLayer
from src.maisaka.agent_autonomy.personality_drift.drift_params import DriftParams

if TYPE_CHECKING:
    from src.maisaka.agent.config import LayeredPersonality
    from src.maisaka.agent_autonomy.personality_algo.plasticity import PlasticityCalculator
    from src.maisaka.agent_autonomy.personality_drift.drift_fitness_collector import (
        DriftFitnessCollector,
    )
    from src.maisaka.agent_autonomy.personality_persistence import PersonalityPersistence

logger = get_logger("maisaka.personality_drift.manager")


class PersonalityDriftManager:
    """漂移循环核心。与 VitalityManager 平级，共享 VitalityTickScheduler 调度。"""

    def __init__(
        self,
        config: dict,
        persistence: "PersonalityPersistence",
        plasticity: "PlasticityCalculator",
        fitness_collector: "DriftFitnessCollector",
    ) -> None:
        self._enabled = config.get("enabled", False)
        self._drift_period = config.get("drift_period", 500)
        self._regression_rate = config.get("regression_rate", 0.03)
        self._sigma_max = config.get("sigma_max", 0.3)
        self._selection_ratio = config.get("selection_ratio", 2 / 12)
        self._persistence = persistence
        self._plasticity = plasticity
        self._fitness = fitness_collector

    def on_tick(
        self,
        agent_id: str,
        interaction_count: int,
        layered_personality: "LayeredPersonality",
        user_id: str,
    ) -> None:
        """每 drift_period 次互动触发漂移。共享 VitalityTickScheduler 调度。"""
        if not self._enabled:
            return
        if interaction_count <= 0 or interaction_count % self._drift_period != 0:
            return
        try:
            fitness = self._fitness.collect(agent_id, user_id)
            layer_text = layered_personality.get_layer_text(PersonalityLayer.EXPRESSION)
            params = DriftParams.from_layer_text(layer_text)
            self._drift_step(params, fitness, interaction_count)
            self._regression(params)
            params.clamp_all()
            layered_personality.set_layer_text(
                PersonalityLayer.EXPRESSION, params.to_layer_text()
            )
            logger.info(
                "drift tick: agent=%s fitness=%.3f params=%s",
                agent_id, fitness, {p.name: round(p.value, 3) for p in params.all_params()},
            )
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "drift tick 异常", exception=exc)
            logger.warning("drift tick 异常: agent=%s error=%s", agent_id, exc)

    def _drift_step(
        self, params: DriftParams, fitness: float, interaction_count: int
    ) -> None:
        """漂移算子 = 选择 + 经典梯度。

        V1: 独立高斯 random.gauss(0, sigma*scale)。
        V2: 自我认知协方差（exp60c 验证更优），V1 跑稳后切换。
        """
        plasticity = self._plasticity.compute(interaction_count)
        sigma = self._sigma_max * plasticity
        if fitness < 0.2:
            scale = 1.6
        else:
            scale = 0.6
        for p in params.all_params():
            drift = random.gauss(0, sigma * scale)
            p.value += drift
            p.history.append(p.value)

    def _regression(self, params: DriftParams) -> None:
        """回归力——参数向初始值微弱拉回，防止漂移过远。"""
        for p in params.all_params():
            p.value = (
                p.value * (1 - self._regression_rate)
                + p.initial_value * self._regression_rate
            )

    async def save_drift_record(
        self,
        agent_id: str,
        params: DriftParams,
    ) -> None:
        """漂移存档（可回滚）。"""
        await self._persistence.save_modification(
            agent_id=agent_id,
            layer=PersonalityLayer.EXPRESSION,
            field="drift_params",
            modification_text=params.to_layer_text(),
            trigger="zh1_drift",
        )