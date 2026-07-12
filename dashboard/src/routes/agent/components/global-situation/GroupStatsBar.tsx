import { useTranslation } from 'react-i18next'

import type { VitalSignsData } from '../../utils/vital-signs'
import type { BatchRelationshipItem } from '@/lib/agent-api'

interface GroupStatsBarProps {
  vitalSignsList: VitalSignsData[]
  relationships: Record<string, BatchRelationshipItem[]>
  registeredCount: number
}

export function GroupStatsBar({ vitalSignsList, relationships, registeredCount }: GroupStatsBarProps) {
  const { t } = useTranslation()

  const activeAgents = vitalSignsList.filter((v) => v.activityRhythm.status === 'active').length
  const totalRelationships = Object.values(relationships).reduce((sum, rels) => sum + rels.length, 0)
  const avgScore = Object.values(relationships).flat().length > 0
    ? Math.round(Object.values(relationships).flat().reduce((sum, r) => sum + r.score, 0) / Object.values(relationships).flat().length)
    : 0

  return (
    <div className="flex items-center gap-4 text-sm text-muted-foreground">
      <span>{t('agent.globalSituation.statsDetail.registeredAgents', { count: registeredCount })}</span>
      <span>·</span>
      <span>{t('agent.globalSituation.statsDetail.activeAgents', { count: activeAgents })}</span>
      <span>·</span>
      <span>{t('agent.globalSituation.statsDetail.totalRelationships', { count: totalRelationships })}</span>
      <span>·</span>
      <span>{t('agent.globalSituation.statsDetail.avgScore', { score: avgScore })}</span>
    </div>
  )
}
