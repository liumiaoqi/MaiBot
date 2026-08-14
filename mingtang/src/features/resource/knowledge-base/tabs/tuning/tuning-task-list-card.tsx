/**
 * 调优任务列表卡片（P2-B 从 TuningTab.tsx 拆出）——任务清单 + 推荐/应用最佳。
 */
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import type { UseMemoryTuningResult } from '../../hooks/useMemoryTuning'
import { formatImportTime, getImportStatusVariant } from '../../utils'
import { isTuningTaskRecommended } from './tuning-snapshot'

export function TuningTaskListCard({
  tasks,
  applyBestTask,
  t,
}: {
  tasks: UseMemoryTuningResult['tuningTasks']
  applyBestTask: UseMemoryTuningResult['applyBestTask']
  t: (key: string, options?: Record<string, unknown>) => string
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle>{t('memory.tuning.tasks.title')}</CardTitle>
        <CardDescription>{t('memory.tuning.tasks.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {tasks.length > 0 ? (
          <div className="space-y-2" role="list">
            {tasks.map((task, index) => {
              const taskId = String(task.task_id ?? '')
              const status = String(task.status ?? '-')
              const recommended = isTuningTaskRecommended(task)
              const canApply = Boolean(task.task_id) && status === 'completed' && recommended
              const statusLabel = t(`memory.tuning.status.${status}`, { defaultValue: status })
              return (
                <div
                  key={taskId || `tuning-task-${index}`}
                  className="space-y-3 rounded-md border bg-muted/20 p-3 transition-colors hover:bg-muted/30"
                  role="listitem"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 space-y-1">
                      <div className="break-all font-mono text-xs leading-5">{taskId || '-'}</div>
                      <div className="text-xs text-muted-foreground">
                        {formatImportTime(Number(task.updated_at ?? task.created_at ?? 0))}
                      </div>
                    </div>
                    <Badge variant={getImportStatusVariant(status)}>{statusLabel}</Badge>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <Badge variant={recommended ? 'secondary' : 'outline'}>
                      {recommended ? t('memory.tuning.tasks.recommended') : t('memory.tuning.tasks.notRecommended')}
                    </Badge>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void applyBestTask(taskId)}
                      disabled={!canApply}
                    >
                      {t('memory.tuning.actions.applyBest')}
                    </Button>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="rounded-md border border-dashed p-4 text-center text-sm text-muted-foreground">
            {t('memory.tuning.tasks.empty')}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
