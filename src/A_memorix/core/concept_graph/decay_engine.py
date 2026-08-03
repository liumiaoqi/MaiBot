"""FusedDecayEngine — 统一衰减引擎（MF-P1-003 相关，P2 全量接入）。

一次调用同时处理关系边权重衰减和 Trace 粒度衰减，保证衰减一致性——
替代"分别调用 GraphStore.reinforce_relations 与 GranularDecayEngine"的独立衰减路径。
"""

from typing import TYPE_CHECKING

from .models import DecayResult

if TYPE_CHECKING:
    from .concept_graph import ConceptGraph


class FusedDecayEngine:
    """统一衰减引擎。"""

    def __init__(self, concept_graph: "ConceptGraph") -> None:
        self._concept_graph = concept_graph

    def decay(
        self,
        *,
        relation_factor: float,
        trace_factor: float,
    ) -> DecayResult:
        """同步衰减事实投影与联想投影。

        Args:
            relation_factor: 关系边权重乘数 (0, 1]
            trace_factor: Trace 边 decay_factor 乘数 (0, 1]

        Returns:
            DecayResult（各层受影响行数）
        """
        return self._concept_graph.decay_all(
            relation_factor=relation_factor,
            trace_factor=trace_factor,
        )
