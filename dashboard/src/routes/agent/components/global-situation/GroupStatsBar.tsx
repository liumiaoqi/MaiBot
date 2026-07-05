import type { VitalSignsData } from '../../utils/vital-signs'
import type { BatchRelationshipItem } from '@/lib/agent-api'

interface GroupStatsBarProps {
  vitalSignsList: VitalSignsData[]
  relationships: Record<string, BatchRelationshipItem[]>
}

export function GroupStatsBar({ vitalSignsList, relationships }: GroupStatsBarProps) {

  const totalAgents = vitalSignsList.length
  const activeAgents = vitalSignsList.filter((v) => v.activityRhythm.status === 'active').length
  const totalRelationships = Object.values(relationships).reduce((sum, rels) => sum + rels.length, 0)
  const avgScore = Object.values(relationships).flat().length > 0
    ? Math.round(Object.values(relationships).flat().reduce((sum, r) => sum + r.score, 0) / Object.values(relationships).flat().length)
    : 0

  return (
    <div className="flex items-center gap-4 text-sm text-muted-foreground">
      <span>{totalAgents} 个生命体</span>
      <span>·</span>
      <span>{activeAgents} 个活跃</span>
      <span>·</span>
      <span>{totalRelationships} 条纽带</span>
      <span>·</span>
      <span>均温 {avgScore}</span>
    </div>
  )
}