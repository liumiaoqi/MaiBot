from datetime import datetime

from sqlalchemy import select

from src.common.database.database import get_db_session
from src.common.database.database_model import AgentInteractionRelationship as AIRTable
from src.common.logger import get_logger

from src.core.adapters.agent_config_port import get_agent_config_provider
from src.maisaka.agent_interaction.models import AgentInteractionRelationshipRead

logger = get_logger("agent_interaction.relationship_manager")

# Hebbian 共激活参数（CC 原型实验推荐值）
_COACTIVATION_DELTA_COPRESENCE = 0.08
_COACTIVATION_DELTA_MENTION = 0.12
_COACTIVATION_DECAY_RATE = 0.02  # 每小时衰减率，半衰期 ~34.7h
_COACTIVATION_MAX = 1.0


def _table_to_read(row: AIRTable) -> AgentInteractionRelationshipRead:
    return AgentInteractionRelationshipRead(
        id=row.id,
        agent_id=row.agent_id,
        target_agent_id=row.target_agent_id,
        score=row.score,
        relationship_type=row.relationship_type,
        attitude=row.attitude,
        interaction_count=row.interaction_count,
        last_interaction_at=row.last_interaction_at,
        coactivation_strength=row.coactivation_strength,
        last_coactivation_at=row.last_coactivation_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class AgentRelationshipManager:
    """智能体间交互关系管理"""

    def __init__(self) -> None:
        self._registry = get_agent_config_provider()
        self._interaction_counter = 0

    async def initialize_from_config(self) -> None:
        agents = self._registry.list_agents()
        with get_db_session() as session:
            for agent in agents:
                for rel in agent.internal_relationships:
                    exists = session.execute(
                        select(AIRTable).where(
                            AIRTable.agent_id == agent.agent_id,
                            AIRTable.target_agent_id == rel.target_agent_id,
                        )
                    )
                    if exists.scalar_one_or_none() is not None:
                        continue
                    row = AIRTable(
                        agent_id=agent.agent_id,
                        target_agent_id=rel.target_agent_id,
                        score=rel.mention_tendency * 300,
                        relationship_type=rel.relationship_type,
                        attitude=rel.attitude,
                    )
                    session.add(row)
            session.commit()

    async def get_relationship(
        self, agent_id: str, target_agent_id: str
    ) -> AgentInteractionRelationshipRead | None:
        with get_db_session() as session:
            result = session.execute(
                select(AIRTable).where(
                    AIRTable.agent_id == agent_id,
                    AIRTable.target_agent_id == target_agent_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _table_to_read(row)

    async def update_relationship(
        self, agent_id: str, target_agent_id: str, delta: float
    ) -> AgentInteractionRelationshipRead:
        with get_db_session() as session:
            result = session.execute(
                select(AIRTable).where(
                    AIRTable.agent_id == agent_id,
                    AIRTable.target_agent_id == target_agent_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = AIRTable(
                    agent_id=agent_id,
                    target_agent_id=target_agent_id,
                    score=max(0.0, min(1000.0, delta)),
                    interaction_count=1,
                    last_interaction_at=datetime.now(),
                )
                session.add(row)
            else:
                row.score = max(0.0, min(1000.0, row.score + delta))
                row.interaction_count += 1
                row.last_interaction_at = datetime.now()
                row.updated_at = datetime.now()
            session.commit()
            session.refresh(row)
            # LS-6: 交互计数触发涌现检测
            self._interaction_counter += 1
            if self._interaction_counter >= self._EMERGENCE_INTERACTION_INTERVAL:
                self._interaction_counter = 0
                try:
                    communities = await self.detect_emergent_communities()
                    if communities:
                        await self._apply_emergent_types(communities)
                except Exception as exc:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.WARNING, "涌现检测失败，跳过", exception=exc)
                    logger.debug(f"涌现检测跳过: error={exc}")
            return _table_to_read(row)

    async def _apply_emergent_types(self, communities: list[dict]) -> None:
        """LS-6: 将涌现类型写入关系记录的 relationship_type（双轨制，不覆盖配置类型）。"""
        with get_db_session() as session:
            for community in communities:
                agents = set(community["agents"])
                emerged_type = community["emerged_type"]
                for aid in agents:
                    for target_id in agents:
                        if aid == target_id:
                            continue
                        result = session.execute(
                            select(AIRTable).where(
                                AIRTable.agent_id == aid,
                                AIRTable.target_agent_id == target_id,
                            )
                        )
                        row = result.scalar_one_or_none()
                        if row is None:
                            continue
                        # 双轨制：只在无配置类型或配置类型为默认值时标注涌现类型
                        if not row.relationship_type or row.relationship_type in self._KNOWN_TYPES:
                            # 保留原配置类型，涌现类型存入 attitude 字段
                            if not row.attitude.startswith("[emerged:"):
                                row.attitude = f"[emerged:{emerged_type}] {row.attitude}"
            session.commit()

    async def update_coactivation(
        self, agent_id: str, target_agent_id: str, delta: float
    ) -> None:
        """更新 Hebbian 共激活强度。

        delta 由交互类型决定：共在场 +0.08，互相提及 +0.12。
        先应用时间衰减，再累加增量，上限 1.0。
        """
        import time as _time

        now = _time.time()
        with get_db_session() as session:
            result = session.execute(
                select(AIRTable).where(
                    AIRTable.agent_id == agent_id,
                    AIRTable.target_agent_id == target_agent_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return

            # 先衰减
            hours_elapsed = (now - row.last_coactivation_at) / 3600.0
            if hours_elapsed > 0 and row.coactivation_strength > 0:
                import math
                row.coactivation_strength *= math.exp(-_COACTIVATION_DECAY_RATE * hours_elapsed)

            # 累加增量
            row.coactivation_strength = min(_COACTIVATION_MAX, row.coactivation_strength + delta)
            row.last_coactivation_at = now
            row.updated_at = datetime.now()
            session.commit()

    async def decay_coactivations(self, agent_id: str) -> int:
        """批量衰减指定智能体所有关系的共激活强度。

        由心跳调度器定期调用。返回衰减的行数。
        """
        import math
        import time as _time

        now = _time.time()
        decayed = 0
        with get_db_session() as session:
            result = session.execute(
                select(AIRTable).where(AIRTable.agent_id == agent_id)
            )
            rows = result.scalars().all()
            for row in rows:
                if row.coactivation_strength <= 0:
                    continue
                hours_elapsed = (now - row.last_coactivation_at) / 3600.0
                if hours_elapsed <= 0:
                    continue
                new_strength = row.coactivation_strength * math.exp(-_COACTIVATION_DECAY_RATE * hours_elapsed)
                # 低于 0.001 视为归零
                row.coactivation_strength = 0.0 if new_strength < 0.001 else new_strength
                row.last_coactivation_at = now
                row.updated_at = datetime.now()
                decayed += 1
            if decayed > 0:
                session.commit()
        return decayed

    async def get_coactivation(self, agent_id: str, target_agent_id: str) -> float:
        """获取共激活强度（先衰减再返回）。"""
        import math
        import time as _time

        now = _time.time()
        with get_db_session() as session:
            result = session.execute(
                select(AIRTable).where(
                    AIRTable.agent_id == agent_id,
                    AIRTable.target_agent_id == target_agent_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return 0.0
            hours_elapsed = (now - row.last_coactivation_at) / 3600.0
            if hours_elapsed > 0 and row.coactivation_strength > 0:
                return row.coactivation_strength * math.exp(-_COACTIVATION_DECAY_RATE * hours_elapsed)
            return row.coactivation_strength

    # ── LS-6: 分类涌现 ──────────────────────────────────

    _EMERGENCE_THRESHOLD = 0.5
    _EMERGENCE_INTERACTION_INTERVAL = 50
    _KNOWN_TYPES = {"family", "romantic", "friend", "mentor", "rival"}
    _EMERGED_PREFIX = "emerged_"

    async def detect_emergent_communities(self) -> list[dict]:
        """LS-6: 阈值切断 + 连通分量，从共激活图中涌现社区。

        返回 [{"agents": [...], "dominant_type": "friend", "emerged_type": "emerged_friend"}, ...]
        """
        graph = await self._build_coactivation_graph()
        if not graph:
            return []

        # 阈值切断：只保留 coactivation >= threshold 的边
        threshold = self._EMERGENCE_THRESHOLD
        filtered = {aid: {} for aid in graph}
        for aid, neighbors in graph.items():
            for target, strength in neighbors.items():
                if strength >= threshold:
                    filtered[aid][target] = strength

        # 连通分量（BFS）
        visited: set[str] = set()
        communities: list[set[str]] = []
        for aid in filtered:
            if aid in visited:
                continue
            component: set[str] = set()
            queue = [aid]
            while queue:
                node = queue.pop(0)
                if node in component:
                    continue
                component.add(node)
                for neighbor in filtered.get(node, {}):
                    if neighbor not in component:
                        queue.append(neighbor)
            visited.update(component)
            if len(component) >= 2:
                communities.append(component)

        # 为每个社区确定涌现类型
        result = []
        for community in communities:
            agents = sorted(community)
            dominant_type = self._infer_community_type(community, graph)
            emerged_type = f"{self._EMERGED_PREFIX}{dominant_type}"
            result.append({
                "agents": agents,
                "dominant_type": dominant_type,
                "emerged_type": emerged_type,
                "size": len(agents),
            })

        if result:
            logger.info(
                f"涌现社区检测: communities={len(result)} "
                f"types={','.join(r['emerged_type'] for r in result)}"
            )
        return result

    async def _build_coactivation_graph(self) -> dict[str, dict[str, float]]:
        """构建共激活邻接表（全量）。"""
        import time as _time

        now = _time.time()
        graph: dict[str, dict[str, float]] = {}
        with get_db_session() as session:
            rows = session.execute(select(AIRTable)).scalars().all()
            for row in rows:
                strength = row.coactivation_strength
                if strength <= 0:
                    continue
                hours_elapsed = (now - row.last_coactivation_at) / 3600.0
                if hours_elapsed > 0:
                    import math
                    strength = strength * math.exp(-_COACTIVATION_DECAY_RATE * hours_elapsed)
                if strength < 0.001:
                    continue
                graph.setdefault(row.agent_id, {})[row.target_agent_id] = strength
        return graph

    def _infer_community_type(self, community: set[str], graph: dict[str, dict[str, float]]) -> str:
        """从社区内边的 relationship_type 众数推断类型。"""
        type_counts: dict[str, int] = {}
        with get_db_session() as session:
            rows = session.execute(select(AIRTable)).scalars().all()
            for row in rows:
                if row.agent_id in community and row.target_agent_id in community:
                    rtype = row.relationship_type
                    if rtype:
                        type_counts[rtype] = type_counts.get(rtype, 0) + 1
        if not type_counts:
            return "group"
        return max(type_counts, key=type_counts.get)

    @staticmethod
    def resolve_effect_type(relationship_type: str) -> str:
        """LS-6: 将涌现类型映射到 effect_calculator 可识别的类型。

        emerged_friend → friend, emerged_intimate → friend, 未知 → friend
        """
        if relationship_type.startswith("emerged_"):
            base = relationship_type[len("emerged_"):]
            if base in AgentRelationshipManager._KNOWN_TYPES:
                return base
            return "friend"
        return relationship_type