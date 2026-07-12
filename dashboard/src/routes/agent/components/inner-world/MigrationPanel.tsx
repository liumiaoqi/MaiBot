import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowRight, Database } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useToast } from '@/hooks/use-toast'

import { advanceMigration, getMigrationStates } from '@/lib/migration-api'
import type { MigrationState } from '@/lib/migration-api'

const PHASE_LABELS: Record<string, { label: string; color: string }> = {
  LEGACY_ONLY: { label: '仅分类学', color: 'bg-slate-500' },
  DUAL_WRITE: { label: '双写', color: 'bg-amber-500' },
  DUAL_READ: { label: '双读', color: 'bg-blue-500' },
  DATA_MIGRATION: { label: '数据迁移', color: 'bg-purple-500' },
  NEW_INDEPENDENT: { label: '连接主义独立', color: 'bg-emerald-500' },
}

function PhaseBadge({ phase }: { phase: string }) {
  const info = PHASE_LABELS[phase] ?? { label: phase, color: 'bg-slate-400' }
  return (
    <Badge variant="secondary" className="text-[10px] gap-1">
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${info.color}`} />
      {info.label}
    </Badge>
  )
}

function formatTimestamp(ts: number): string {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString('zh-CN')
}

function MigrationStateRow({ state }: { state: MigrationState }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const advanceMut = useMutation({
    mutationFn: () => advanceMigration(state.plugin_id),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['migration', 'states'] })
      toast({ title: t('agent.migration.advanceSuccess', { name: state.plugin_name, phase: result.current_phase }) })
    },
    onError: () => {
      toast({ title: t('agent.migration.advanceFailed'), variant: 'destructive' })
    },
  })

  const isLast = state.current_phase === 'NEW_INDEPENDENT'

  return (
    <div className="flex items-center gap-3 rounded-md border px-3 py-2">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-sm">{state.plugin_name}</span>
          <PhaseBadge phase={state.current_phase} />
        </div>
        <div className="text-xs text-muted-foreground">
          {state.notes && <span className="mr-2">{state.notes}</span>}
          <span>{formatTimestamp(state.last_updated)}</span>
        </div>
      </div>
      {!isLast && (
        <Button
          size="sm"
          variant="outline"
          className="text-xs"
          onClick={() => advanceMut.mutate()}
          disabled={advanceMut.isPending}
        >
          <ArrowRight className="h-3 w-3 mr-1" />
          {t('agent.migration.advance')}
        </Button>
      )}
    </div>
  )
}

export function MigrationPanel() {
  const { t } = useTranslation()

  const { data: states, isLoading, error } = useQuery({
    queryKey: ['migration', 'states'],
    queryFn: getMigrationStates,
  })

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Database className="h-4 w-4" />
            {t('agent.migration.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">{t('agent.migration.loading')}</div>
        </CardContent>
      </Card>
    )
  }

  if (error || !states || states.length === 0) {
    return null
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Database className="h-4 w-4" />
          {t('agent.migration.title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {states.map((s) => (
          <MigrationStateRow key={s.plugin_id} state={s} />
        ))}
      </CardContent>
    </Card>
  )
}