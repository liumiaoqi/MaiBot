import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import type { RelationshipInfo, InternalRelationship, AgentConfigInfo } from '@/lib/agent-api'
import { DeepMonitorLink } from './DeepMonitorLink'
import { InternalRelationshipGraph } from './InternalRelationshipGraph'

interface RelationshipNetworkProps {
  agentId: string
  relationships: RelationshipInfo[]
  internalRelationships: InternalRelationship[]
  agents: AgentConfigInfo[]
}

export const REL_TYPE_COLORS: Record<string, string> = {
  romantic: '#ef4444',
  family: '#f97316',
  mentor: '#3b82f6',
  friend: '#22c55e',
  rival: '#94a3b8',
}

export function RelationshipNetwork({ agentId, relationships, internalRelationships, agents }: RelationshipNetworkProps) {
  const { t } = useTranslation()

  if (relationships.length === 0 && internalRelationships.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
        {t('agent.relationshipNetwork.unavailable')}
      </div>
    )
  }

  const levelDistribution = relationships.reduce<Record<string, number>>((acc, rel) => {
    acc[rel.level_name] = (acc[rel.level_name] || 0) + 1
    return acc
  }, {})

  return (
    <div className="space-y-4">
      {Object.keys(levelDistribution).length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t('agent.relationshipNetwork.distribution')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {Object.entries(levelDistribution).map(([level, count]) => (
                <Badge key={level} variant="secondary">
                  {level} ×{count}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {relationships.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t('agent.relationshipNetwork.ranking')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {relationships
                .sort((a, b) => b.score - a.score)
                .slice(0, 5)
                .map((rel) => (
                  <div key={rel.user_id} className="flex items-center justify-between text-sm">
                    <span className="truncate">{rel.user_id}</span>
                    <div className="flex items-center gap-2">
                      <Badge variant={rel.level >= 3 ? 'default' : 'outline'}>{rel.level_name}</Badge>
                      <span className="text-xs text-muted-foreground">{Math.round(rel.score)}</span>
                    </div>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      )}

      {internalRelationships.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t('agent.relationshipNetwork.internalGraph')}</CardTitle>
          </CardHeader>
          <CardContent>
            <InternalRelationshipGraph
              agentId={agentId}
              internalRelationships={internalRelationships}
              agents={agents}
            />
          </CardContent>
        </Card>
      )}

      <DeepMonitorLink agentId={agentId} target="relationship" />
    </div>
  )
}