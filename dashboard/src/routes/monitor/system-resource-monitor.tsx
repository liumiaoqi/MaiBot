import { Activity, Database, HardDrive, MemoryStick, Wifi, WifiOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { useSystemResources } from '@/hooks/useSystemResources'

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** unitIndex
  return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`
}

function ResourceGauge({ label, percent, used, total, icon: Icon }: {
  label: string
  percent: number
  used?: number
  total?: number
  icon: React.ComponentType<{ className?: string }>
}) {
  const displayPercent = Math.min(100, Math.max(0, percent))
  const colorClass = displayPercent > 90 ? 'text-red-500' : displayPercent > 70 ? 'text-orange-500' : 'text-primary'

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Icon className="h-4 w-4" />
          {label}
        </span>
        <span className={`text-sm font-bold ${colorClass}`}>
          {displayPercent.toFixed(1)}%
        </span>
      </div>
      <Progress value={displayPercent} className="h-2" />
      {used !== undefined && total !== undefined && (
        <p className="text-xs text-muted-foreground">
          {formatBytes(used)} / {formatBytes(total)}
        </p>
      )}
    </div>
  )
}

export function SystemResourceMonitor() {
  const { t } = useTranslation()
  const { data, isConnected, error, refetch } = useSystemResources()

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="flex h-5 items-center gap-2 text-sm font-medium leading-5">
          <Activity className="h-4 w-4" />
          {t('monitor.systemResources.title')}
        </CardTitle>
        <div className="flex items-center gap-2">
          {isConnected ? (
            <span className="flex items-center gap-1 text-xs text-green-600">
              <Wifi className="h-3.5 w-3.5" />
              {t('monitor.systemResources.live')}
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <WifiOff className="h-3.5 w-3.5" />
              {t('monitor.systemResources.polling')}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {error && !data ? (
          <p className="text-sm text-destructive">{t('monitor.systemResources.error')}</p>
        ) : data ? (
          <>
            <ResourceGauge
              label={t('monitor.systemResources.cpu')}
              percent={data.cpu_percent}
              icon={Activity}
            />
            <ResourceGauge
              label={t('monitor.systemResources.memory')}
              percent={data.memory_percent}
              used={data.memory_used}
              total={data.memory_total}
              icon={MemoryStick}
            />
            <ResourceGauge
              label={t('monitor.systemResources.disk')}
              percent={data.disk_percent}
              used={data.disk_used}
              total={data.disk_total}
              icon={HardDrive}
            />
            <div className="flex items-center justify-between gap-2 text-sm">
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <Database className="h-4 w-4" />
                {t('monitor.systemResources.database')}
              </span>
              <span className="font-bold">{formatBytes(data.database_size)}</span>
            </div>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">{t('monitor.systemResources.loading')}</p>
        )}
      </CardContent>
    </Card>
  )
}