import { useQuery } from '@tanstack/react-query'
import { Activity, RefreshCw } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

import { useToast } from '@/hooks/use-toast'

import {
  getAgentList,
  getSubAgentRecords,
  getSubAgentStats,

} from '@/lib/agent-api'

import { cn } from '@/lib/utils'

const STATUS_CONFIG: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  pending: { label: '等待中', variant: 'outline' },
  running: { label: '运行中', variant: 'default' },
  completed: { label: '已完成', variant: 'secondary' },
  failed: { label: '失败', variant: 'destructive' },
  cancelled: { label: '已取消', variant: 'outline' },
}

const TYPE_LABELS: Record<string, string> = {
  dream: 'Dream 巩固',
  compaction: 'Compaction 压缩',
  'checkpoint-writer': 'Checkpoint 快照',
}

function formatDateTime(isoStr: string | null): string {
  if (!isoStr) return '-'
  try {
    const d = new Date(isoStr)
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return isoStr
  }
}

function formatDuration(start: string | null, end: string | null): string {
  if (!start || !end) return '-'
  try {
    const ms = new Date(end).getTime() - new Date(start).getTime()
    if (ms < 1000) return `${ms}ms`
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
    return `${(ms / 60000).toFixed(1)}m`
  } catch {
    return '-'
  }
}

function formatTokens(n: number): string {
  if (n === 0) return '0'
  if (n < 1000) return `${n}`
  if (n < 1000000) return `${(n / 1000).toFixed(1)}K`
  return `${(n / 1000000).toFixed(1)}M`
}

export function SubAgentMonitorPage() {

  const [filterType, setFilterType] = useState<string>('all')
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [filterAgent, setFilterAgent] = useState<string>('all')

  const agentsQuery = useQuery({
    queryKey: ['agents', 'list'],
    queryFn: getAgentList,
  })

  const statsQuery = useQuery({
    queryKey: ['subagent', 'stats'],
    queryFn: getSubAgentStats,
  })

  const recordsQuery = useQuery({
    queryKey: ['subagent', 'records', filterType, filterStatus, filterAgent],
    queryFn: () =>
      getSubAgentRecords({
        subagent_type: filterType !== 'all' ? filterType : undefined,
        status: filterStatus !== 'all' ? filterStatus : undefined,
        agent_id: filterAgent !== 'all' ? filterAgent : undefined,
        limit: 100,
      }),
  })

  const stats = statsQuery.data
  const records = recordsQuery.data ?? []
  const agents = agentsQuery.data ?? []

  const cacheHitRate = useMemo(() => {
    if (!stats || stats.total_input_tokens === 0) return 0
    return (stats.total_cache_hit_tokens / stats.total_input_tokens) * 100
  }, [stats])

  return (
    <div className="h-full flex flex-col">
      {/* 头部 */}
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-primary" />
          <h1 className="text-lg font-semibold">子智能体监控</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => {
              statsQuery.refetch()
              recordsQuery.refetch()
            }}
          >
            <RefreshCw
              className={cn(
                'h-4 w-4',
                (statsQuery.isFetching || recordsQuery.isFetching) && 'animate-spin'
              )}
            />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        <div className="p-4 space-y-4">
          {/* 统计卡片 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-xs text-muted-foreground">总执行次数</p>
                <p className="text-2xl font-bold">{stats?.total_executions ?? 0}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-xs text-muted-foreground">输入 Token</p>
                <p className="text-2xl font-bold">{formatTokens(stats?.total_input_tokens ?? 0)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-xs text-muted-foreground">输出 Token</p>
                <p className="text-2xl font-bold">{formatTokens(stats?.total_output_tokens ?? 0)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-xs text-muted-foreground">缓存命中率</p>
                <p className="text-2xl font-bold">{cacheHitRate.toFixed(1)}%</p>
              </CardContent>
            </Card>
          </div>

          {/* 类型分布 + 状态分布 */}
          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">按类型分布</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {Object.entries(stats?.by_type ?? {}).map(([type, count]) => (
                    <div key={type} className="flex items-center justify-between">
                      <span className="text-sm">{TYPE_LABELS[type] || type}</span>
                      <Badge variant="secondary">{count}</Badge>
                    </div>
                  ))}
                  {(!stats?.by_type || Object.keys(stats.by_type).length === 0) && (
                    <p className="text-sm text-muted-foreground text-center py-4">暂无数据</p>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">按状态分布</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {Object.entries(stats?.by_status ?? {}).map(([status, count]) => {
                    const config = STATUS_CONFIG[status]
                    return (
                      <div key={status} className="flex items-center justify-between">
                        <span className="text-sm">{config?.label || status}</span>
                        <Badge variant={config?.variant || 'outline'}>{count}</Badge>
                      </div>
                    )
                  })}
                  {(!stats?.by_status || Object.keys(stats.by_status).length === 0) && (
                    <p className="text-sm text-muted-foreground text-center py-4">暂无数据</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* 筛选器 */}
          <div className="flex items-center gap-3">
            <Select value={filterAgent} onValueChange={setFilterAgent}>
              <SelectTrigger className="w-40">
                <SelectValue placeholder="全部智能体" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部智能体</SelectItem>
                {agents.map((a) => (
                  <SelectItem key={a.agent_id} value={a.agent_id}>
                    {a.display_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={filterType} onValueChange={setFilterType}>
              <SelectTrigger className="w-40">
                <SelectValue placeholder="全部类型" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部类型</SelectItem>
                <SelectItem value="dream">Dream 巩固</SelectItem>
                <SelectItem value="compaction">Compaction 压缩</SelectItem>
                <SelectItem value="checkpoint-writer">Checkpoint 快照</SelectItem>
              </SelectContent>
            </Select>

            <Select value={filterStatus} onValueChange={setFilterStatus}>
              <SelectTrigger className="w-32">
                <SelectValue placeholder="全部状态" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部状态</SelectItem>
                <SelectItem value="pending">等待中</SelectItem>
                <SelectItem value="running">运行中</SelectItem>
                <SelectItem value="completed">已完成</SelectItem>
                <SelectItem value="failed">失败</SelectItem>
                <SelectItem value="cancelled">已取消</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* 执行记录表 */}
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">执行记录</CardTitle>
                <span className="text-xs text-muted-foreground">
                  共 {records.length} 条
                </span>
              </div>
            </CardHeader>
            <CardContent>
              {recordsQuery.isLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : records.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground text-sm">
                  暂无执行记录
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-24">类型</TableHead>
                        <TableHead className="w-24">智能体</TableHead>
                        <TableHead className="w-20">状态</TableHead>
                        <TableHead className="w-20">触发</TableHead>
                        <TableHead className="w-28">开始时间</TableHead>
                        <TableHead className="w-20">耗时</TableHead>
                        <TableHead className="w-20">输入</TableHead>
                        <TableHead className="w-20">输出</TableHead>
                        <TableHead className="w-20">缓存</TableHead>
                        <TableHead>摘要</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {records.map((rec) => {
                        const statusConfig = STATUS_CONFIG[rec.status]
                        return (
                          <TableRow key={rec.id}>
                            <TableCell>
                              <Badge variant="outline" className="text-xs">
                                {TYPE_LABELS[rec.subagent_type] || rec.subagent_type}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-xs">{rec.agent_id}</TableCell>
                            <TableCell>
                              <Badge variant={statusConfig?.variant || 'outline'} className="text-xs">
                                {statusConfig?.label || rec.status}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-xs">{rec.trigger_type}</TableCell>
                            <TableCell className="text-xs">
                              {formatDateTime(rec.started_at)}
                            </TableCell>
                            <TableCell className="text-xs">
                              {formatDuration(rec.started_at, rec.completed_at)}
                            </TableCell>
                            <TableCell className="text-xs">
                              {formatTokens(rec.input_tokens)}
                            </TableCell>
                            <TableCell className="text-xs">
                              {formatTokens(rec.output_tokens)}
                            </TableCell>
                            <TableCell className="text-xs">
                              {formatTokens(rec.cache_hit_tokens)}
                            </TableCell>
                            <TableCell className="text-xs max-w-48 truncate" title={rec.result_summary || rec.error_message}>
                              {rec.status === 'failed'
                                ? rec.error_message || '-'
                                : rec.result_summary || '-'}
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}