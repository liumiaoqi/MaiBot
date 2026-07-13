from __future__ import annotations


from ..enums import Valence
from ..models import Fragment, Trace


def build_fragments_from_traces(
    traces_by_obs: dict[str, list[Trace]],
    fragment_statuses: dict[str, str] | None = None,
) -> list[Fragment]:
    """从 TraceStore 查询结果构建 Fragment 列表。

    Fragment 是 Trace 的聚合视图，不持有独立存储。
    同一 observation_id 下的所有 Trace 构成一个 Fragment。

    Args:
        traces_by_obs: observation_id → Trace 列表的映射
        fragment_statuses: observation_id → status 的映射（可选，用于生命周期）
    """
    fragment_statuses = fragment_statuses or {}
    fragments = []
    for obs_id, traces in traces_by_obs.items():
        if not traces:
            continue
        concepts: set[str] = set()
        trace_keys: list[tuple[str, str, str, str]] = []
        valence_sum = 0
        max_weight = 0.0
        min_timestamp = float("inf")

        for t in traces:
            concepts.add(t.source)
            concepts.add(t.target)
            trace_keys.append(t.unique_key)
            valence_sum += t.valence.value_int
            max_weight = max(max_weight, t.weight)
            min_timestamp = min(min_timestamp, t.timestamp)

        if valence_sum > 0:
            agg_valence = Valence.POSITIVE
        elif valence_sum < 0:
            agg_valence = Valence.NEGATIVE
        else:
            agg_valence = Valence.NEUTRAL

        fragments.append(Fragment(
            observation_id=obs_id,
            agent_id=traces[0].agent_id,
            concepts=sorted(concepts),
            trace_keys=trace_keys,
            valence=agg_valence,
            max_weight=max_weight,
            timestamp=min_timestamp,
            status=fragment_statuses.get(obs_id, "active"),
        ))

    return fragments