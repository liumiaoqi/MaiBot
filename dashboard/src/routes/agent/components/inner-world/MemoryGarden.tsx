import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import type { SubAgentRecord } from '@/lib/agent-api'
import { DeepMonitorLink } from './DeepMonitorLink'

interface MemoryGardenProps {
  agentId: string
  memoryFocusAreas: string[]
  subAgentRecords: SubAgentRecord[]
}

export function MemoryGarden({ agentId, memoryFocusAreas, subAgentRecords }: MemoryGardenProps) {
  const { t } = useTranslation()

  const recentRecords = subAgentRecords
    .filter((r) => r.status === 'completed')
    .slice(0, 5)

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">{t('agent.memoryGarden.focusAreas')}</CardTitle>
        </CardHeader>
        <CardContent>
          {memoryFocusAreas.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {memoryFocusAreas.map((area) => (
                <Badge key={area} variant="secondary">
                  🌱 {area}
                </Badge>
              ))}
            </div>
          ) : (
            <span className="text-sm text-muted-foreground">{t('agent.memoryGarden.noFocusAreas')}</span>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">{t('agent.memoryGarden.innerActivity')}</CardTitle>
        </CardHeader>
        <CardContent>
          {recentRecords.length > 0 ? (
            <div className="space-y-2">
              {recentRecords.map((record) => (
                <div key={record.id} className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span>
                    {record.subagent_type === 'Dream'
                      ? '💭'
                      : record.subagent_type === 'Compaction'
                        ? '🔄'
                        : '📌'}
                  </span>
                  <span>{record.result_summary || t('agent.memoryGarden.dreamComplete')}</span>
                  {record.completed_at && (
                    <span className="text-xs ml-auto">
                      {new Date(record.completed_at).toLocaleTimeString()}
                    </span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <span className="text-sm text-muted-foreground">{t('agent.memoryGarden.unavailable')}</span>
          )}
        </CardContent>
      </Card>

      <DeepMonitorLink agentId={agentId} target="subagent" />
    </div>
  )
}