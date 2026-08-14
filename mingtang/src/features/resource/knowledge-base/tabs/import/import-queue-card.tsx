/**
 * import-queue-card —— Card3「导入队列」：运行中 / 排队中 / 最近完成 三组任务 + 自动轮询开关。
 * 三组 JSX 重复（按钮卡片 + ScrollArea + 空态）收敛为本地 TaskGroup + TaskItem 小组件。
 */
import type { ReactNode } from 'react'

import { RefreshCw } from 'lucide-react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import type { MemoryImportTaskPayload } from '@/lib/memory-api'

import {
  formatImportTime,
  formatProgressPercent,
  getImportStatusLabel,
  getImportStatusVariant,
  getImportStepLabel,
  normalizeProgress,
} from '../../utils'
import type { UseImportQueueResult } from '../../hooks/useImportQueue'

interface TaskItemProps {
  task: MemoryImportTaskPayload
  isSelected: boolean
  onSelect: () => void
  /** 底部摘要行（running/recent 显示进度，queued 显示创建时间） */
  footer: ReactNode
  /** 是否显示进度条（queued 没有） */
  showProgress?: boolean
}

function ImportTaskItem({ task, isSelected, onSelect, footer, showProgress = false }: TaskItemProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'w-full rounded-xl border p-4 text-left transition-all',
        isSelected
          ? 'border-primary/70 bg-primary/5 shadow-sm'
          : 'bg-background/80 hover:border-muted-foreground/40 hover:bg-muted/20',
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <div className="break-all font-mono text-[11px] leading-relaxed text-muted-foreground">
            {task.task_id}
          </div>
          <div className="text-sm font-medium">{String(task.task_kind ?? task.mode ?? '-')}</div>
        </div>
        <Badge variant={getImportStatusVariant(String(task.status ?? ''))}>
          {getImportStatusLabel(String(task.status ?? ''))}
        </Badge>
      </div>
      <div className="mt-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">{footer}</div>
      {showProgress ? <Progress value={normalizeProgress(task.progress)} className="mt-2 h-1.5" /> : null}
    </button>
  )
}

interface TaskGroupProps {
  title: string
  count: number
  badgeVariant?: 'outline' | 'secondary'
  heightClass: string
  tasks: MemoryImportTaskPayload[]
  selectedTaskId: string
  onSelectTask: (taskId: string) => void
  renderFooter: (task: MemoryImportTaskPayload) => ReactNode
  showProgress?: boolean
  emptyText: string
}

function TaskGroup({
  title,
  count,
  badgeVariant = 'outline',
  heightClass,
  tasks,
  selectedTaskId,
  onSelectTask,
  renderFooter,
  showProgress = false,
  emptyText,
}: TaskGroupProps) {
  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium">{title}</div>
        <Badge variant={badgeVariant}>{count}</Badge>
      </div>
      {tasks.length > 0 ? (
        <ScrollArea className={`${heightClass} rounded-xl border bg-muted/10`}>
          <div className="space-y-2.5 p-2.5">
            {tasks.map((task) => (
              <ImportTaskItem
                key={task.task_id}
                task={task}
                isSelected={task.task_id === selectedTaskId}
                onSelect={() => void onSelectTask(task.task_id)}
                footer={renderFooter(task)}
                showProgress={showProgress}
              />
            ))}
          </div>
        </ScrollArea>
      ) : (
        <div className="rounded-xl border bg-muted/20 p-4 text-sm text-muted-foreground">{emptyText}</div>
      )}
    </div>
  )
}

export function ImportQueueCard({ queue }: { queue: UseImportQueueResult }) {
  const {
    refreshImportQueue,
    runningImportTasks,
    queuedImportTasks,
    recentImportTasks,
    selectedImportTaskId,
    selectImportTask,
    importAutoPolling,
    setImportAutoPolling,
    importPollInterval,
    importErrorText,
  } = queue
  return (
    <Card className="rounded-2xl border-border/70 bg-card/90 shadow-sm">
      <CardHeader className="space-y-4 pb-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>导入队列</CardTitle>
          <Button variant="outline" size="sm" onClick={() => void refreshImportQueue()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            刷新
          </Button>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardDescription className="text-sm">
            查看任务是否正在运行、排队等待或已经结束。点击任务卡片可查看详情。
          </CardDescription>
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            <Badge variant="outline" className="bg-background/70">运行中 {runningImportTasks.length}</Badge>
            <Badge variant="outline" className="bg-background/70">排队中 {queuedImportTasks.length}</Badge>
            <Badge variant="outline" className="bg-background/70">最近完成 {recentImportTasks.length}</Badge>
          </div>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <Checkbox
              checked={importAutoPolling}
              onCheckedChange={(value) => setImportAutoPolling(Boolean(value))}
            />
            自动轮询 {importPollInterval}ms
          </label>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {importErrorText ? (
          <Alert variant="destructive">
            <AlertDescription>{importErrorText}</AlertDescription>
          </Alert>
        ) : null}

        <TaskGroup
          title="运行中"
          count={runningImportTasks.length}
          heightClass="h-[208px]"
          tasks={runningImportTasks}
          selectedTaskId={selectedImportTaskId}
          onSelectTask={selectImportTask}
          renderFooter={(task) => (
            <>
              <span>{getImportStepLabel(String(task.current_step ?? 'running'))}</span>
              <span>{formatProgressPercent(task.progress)}</span>
            </>
          )}
          showProgress
          emptyText="当前没有运行中任务"
        />

        <TaskGroup
          title="排队中"
          count={queuedImportTasks.length}
          heightClass="h-[188px]"
          tasks={queuedImportTasks}
          selectedTaskId={selectedImportTaskId}
          onSelectTask={selectImportTask}
          renderFooter={(task) => (
            <>
              <span>创建时间</span>
              <span>{formatImportTime(task.created_at)}</span>
            </>
          )}
          emptyText="当前没有排队任务"
        />

        <TaskGroup
          title="最近完成"
          count={recentImportTasks.length}
          badgeVariant="secondary"
          heightClass="h-[260px]"
          tasks={recentImportTasks}
          selectedTaskId={selectedImportTaskId}
          onSelectTask={selectImportTask}
          renderFooter={(task) => (
            <>
              <span>完成进度</span>
              <span>{formatProgressPercent(task.progress)}</span>
            </>
          )}
          showProgress
          emptyText="暂时没有历史任务"
        />
      </CardContent>
    </Card>
  )
}
