import { useBatchAgentData } from '../../hooks/useBatchAgentData'
import { deriveVitalSignsData } from '../../utils/vital-signs'
import { EmotionDonutChart } from './EmotionDonutChart'
import { ActivityHeatmap } from './ActivityHeatmap'
import { RelationshipDynamicsFlow } from './RelationshipDynamicsFlow'
import { GroupStatsBar } from './GroupStatsBar'

export function GlobalSituationView() {
  const { agents, emotions, relationships, internalRelationshipsSummary, sessionCounts, latestSubAgentRecords } = useBatchAgentData()

  const vitalSignsList = agents.map((agent) =>
    deriveVitalSignsData(
      agent,
      emotions[agent.agent_id] ?? null,
      relationships[agent.agent_id] ?? null,
      sessionCounts[agent.agent_id] ?? 0,
      latestSubAgentRecords[agent.agent_id] ?? null,
      internalRelationshipsSummary[agent.agent_id],
    )
  )

  return (
    <div className="flex flex-col h-full overflow-auto p-4 space-y-6">
      <GroupStatsBar vitalSignsList={vitalSignsList} relationships={relationships} registeredCount={agents.length} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <EmotionDonutChart emotions={emotions} />
        <ActivityHeatmap vitalSignsList={vitalSignsList} />
      </div>

      <RelationshipDynamicsFlow relationships={relationships} />
    </div>
  )
}