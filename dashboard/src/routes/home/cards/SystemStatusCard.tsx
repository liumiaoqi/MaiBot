import { CheckCircle2, Clock, FileText } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import type { BotStatus } from '../types'

interface SystemStatusCardProps {
  botStatus: BotStatus | null
  isBotStatusLoading: boolean
  webuiVersion: string
  formatTime: (seconds: number) => string
}

export function SystemStatusCard({ botStatus, isBotStatusLoading, webuiVersion, formatTime }: SystemStatusCardProps) {
  const { t } = useTranslation()

  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <CardTitle className="flex h-5 items-center gap-2 text-sm font-medium leading-5">
          <FileText className="h-4 w-4" />
          {t('home.systemStatus.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm text-muted-foreground">{t('home.systemStatus.status')}</span>
            {isBotStatusLoading && !botStatus ? (
              <Badge variant="outline" className="text-muted-foreground">
                {t('home.botStatus.loading')}
              </Badge>
            ) : botStatus?.running ? (
              <Badge variant="outline" className="border-green-300 bg-green-50 text-green-600 whitespace-nowrap">
                <CheckCircle2 className="mr-1 h-3 w-3" />
                {t('home.botStatus.running')}
              </Badge>
            ) : botStatus ? (
              <Badge variant="outline" className="border-red-300 bg-red-50 text-red-600 whitespace-nowrap">
                {t('home.botStatus.stopped')}
              </Badge>
            ) : (
              <Badge variant="outline" className="text-muted-foreground">
                {t('home.botStatus.unknown')}
              </Badge>
            )}
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm text-muted-foreground">{t('home.systemStatus.uptime')}</span>
            <span className="flex items-center gap-1.5 text-sm font-medium">
              <Clock className="h-3.5 w-3.5 text-muted-foreground" />
              {botStatus ? formatTime(botStatus.uptime) : '--'}
            </span>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm text-muted-foreground">{t('home.systemStatus.version')}</span>
            <Badge variant="secondary" className="border border-primary/20 bg-primary/10 px-2 py-0.5 font-semibold text-primary">
              {botStatus?.version ? `v${botStatus.version}` : t('home.versionCard.unknown')}
            </Badge>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm text-muted-foreground">{t('home.systemStatus.webuiVersion')}</span>
            <Badge variant="secondary" className="border border-primary/20 bg-primary/10 px-2 py-0.5 font-semibold text-primary">
              v{webuiVersion}
            </Badge>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}