import { useTranslation } from 'react-i18next'

import type { VitalSignsData } from '../../utils/vital-signs'
import type { BatchRelationshipItem } from '@/lib/agent-api'

interface GroupStatsBarProps {
  vitalSignsList: VitalSignsData[]
  relationships: Record<string, BatchRelationshipItem[]>
}

export function GroupStatsBar({ vitalSignsList, relationships }: GroupStatsBarProps) {
  const { t } = useTranslation()

  const totalAgents = vitalSignsList.length
  const activeAgents = vitalSignsList.filter((v) => v.activityRhythm.status === 'active').length
  const totalRelationships = Object.values(relationships).reduce((sum, rels) => sum + rels.length, 0)
  const avgScore = Object.values(relationships).flat().length > 0
    ? Math.round(Object.values(relationships).flat().reduce((sum, r) => sum + r.score, 0) / Object.values(relationships).flat().length)
    : 0

  return (
    <div className="flex items-center gap-4 text-sm text-muted-foreground">
      <span>{t('agent.globalSituation.stats.totalAgents', { count: totalAgents })}</span>
      <span>·</span>
      <span>{t('agent.globalSituation.stats.activeAgents', { count: activeAgents })}</span>
      <span>·</span>
      <span>{t('agent.globalSituation.stats.totalRelationships', { count: totalRelationships })}</span>
      <span>·</span>
      <span>{t('agent.globalSituation.stats.avgScore', { score: avgScore })}</span>
    </div>
  )
}
