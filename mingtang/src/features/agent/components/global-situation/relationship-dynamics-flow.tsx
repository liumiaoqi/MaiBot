import { useTranslation } from 'react-i18next'

import type { BatchRelationshipItem } from '@/lib/agent-api'

interface RelationshipDynamicsFlowProps {
  relationships: Record<string, BatchRelationshipItem[]>
}

export function RelationshipDynamicsFlow({ relationships }: RelationshipDynamicsFlowProps) {
  const { t } = useTranslation()

  const nearBreakthrough: { agentId: string; userId: string; score: number; level: number }[] = []
  for (const [agentId, rels] of Object.entries(relationships)) {
    for (const rel of rels) {
      if (rel.level === 0 && rel.score >= 300) nearBreakthrough.push({ agentId, userId: rel.user_id, score: rel.score, level: rel.level })
      else if (rel.level === 1 && rel.score >= 600) nearBreakthrough.push({ agentId, userId: rel.user_id, score: rel.score, level: rel.level })
      else if (rel.level === 2 && rel.score >= 850) nearBreakthrough.push({ agentId, userId: rel.user_id, score: rel.score, level: rel.level })
    }
  }

  if (nearBreakthrough.length === 0) {
    return (
      <div>
        <h3 className="text-sm font-medium mb-2">{t('agent.globalSituation.relationshipDynamics')}</h3>
        <p className="text-sm text-muted-foreground">{t('agent.globalSituation.noChanges')}</p>
      </div>
    )
  }

  return (
    <div>
      <h3 className="text-sm font-medium mb-2">{t('agent.globalSituation.relationshipDynamics')}</h3>
      <div className="space-y-1.5">
        {nearBreakthrough.slice(0, 10).map((item, i) => (
          <div key={i} className="text-sm text-muted-foreground">
            🔥 {item.agentId} ↔ {item.userId} — {t('agent.globalSituation.nearBreakthrough')} ({Math.round(item.score)})
          </div>
        ))}
      </div>
    </div>
  )
}