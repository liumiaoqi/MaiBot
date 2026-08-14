/**
 * 批处理任务面板（R4 债清理 P1——从 deepseek-monitor/index.tsx 机械拆分）
 *
 * 职责：待处理/降级计数 + API 可用徽标 + 最近任务列表（TASK_TYPE_LABELS/STATUS_LABELS 归属本面板）。
 */
import { useQuery } from '@tanstack/react-query'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { getBatchOverview } from '@/lib/deepseek-api'
import { formatTimestamp } from './overview-cards'

const TASK_TYPE_LABELS: Record<string, string> = {
  dream_consolidation: 'Dream巩固',
  compaction_summary: 'Compaction压缩',
  profile_update: '画像更新',
  emotion_analysis: '情绪分析',
}

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  pending: { label: '待处理', color: 'bg-yellow-500' },
  submitted: { label: '已提交', color: 'bg-blue-500' },
  processing: { label: '处理中', color: 'bg-indigo-500' },
  completed: { label: '已完成', color: 'bg-green-500' },
  failed: { label: '失败', color: 'bg-red-500' },
  degraded: { label: '已降级', color: 'bg-orange-500' },
}

export function BatchPanel() {
  const { data: batch, isLoading } = useQuery({
    queryKey: ['deepseek', 'batch'],
    queryFn: getBatchOverview,
  })

  if (isLoading) {
    return <Skeleton className="h-64 w-full" />
  }

  if (!batch) {
    return <div className="text-muted-foreground text-sm">暂无批处理数据</div>
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-4 text-center">
            <div className="text-2xl font-bold">{batch.pending_count}</div>
            <div className="text-xs text-muted-foreground">待处理</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 text-center">
            <div className="text-2xl font-bold">{batch.degraded_count}</div>
            <div className="text-xs text-muted-foreground">降级为实时</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 text-center">
            <Badge variant={batch.api_available ? 'default' : 'destructive'}>
              {batch.api_available ? 'API可用' : 'API不可用'}
            </Badge>
          </CardContent>
        </Card>
      </div>

      {batch.recent_tasks.length > 0 ? (
        <ScrollArea className="h-64">
          <div className="space-y-2">
            {batch.recent_tasks.map((task, i) => {
              const statusInfo = STATUS_LABELS[task.status] || {
                label: task.status,
                color: 'bg-gray-500',
              }
              return (
                <div
                  key={`${task.task_id}-${i}`}
                  className="flex items-center justify-between rounded-md border p-2 text-xs"
                >
                  <div className="flex items-center gap-2">
                    <div className={`h-2 w-2 rounded-full ${statusInfo.color}`} />
                    <span className="font-medium">
                      {TASK_TYPE_LABELS[task.task_type] || task.task_type}
                    </span>
                    <span className="text-muted-foreground">{task.agent_id}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {task.degraded_to_realtime && (
                      <Badge variant="outline" className="text-[10px]">
                        已降级
                      </Badge>
                    )}
                    <span className="text-muted-foreground">
                      {formatTimestamp(task.created_at)}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </ScrollArea>
      ) : (
        <p className="text-center text-xs text-muted-foreground">暂无批处理任务记录</p>
      )}
    </div>
  )
}
