import { useQuery } from '@tanstack/react-query'
import { Cpu, DollarSign, Layers, Zap } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

import {
  getAgentBudget,
  getAgentCacheStats,
  getAgentCost,
  getBatchOverview,
  getDeepSeekOverview,
  getMonthlyCostReport,
  type DeepSeekOverviewInfo,
} from '@/lib/deepseek-api'
import { getAgentList, type AgentConfigInfo } from '@/lib/agent-api'

const SEGMENT_LABELS: Record<string, string> = {
  identity: '人设注入',
  anti_mechanization: '反机械化',
  internal_relationships: '内部关系网',
  emotion_state: '情绪状态',
  relationship: '关系状态',
  profile: '画像注入',
  mid_term: '中期记忆',
  heuristic: '启发式记忆',
  cross_chat: '跨聊上下文',
  history: '对话历史',
  reserved: '预留',
}

const SEGMENT_COLORS: Record<string, string> = {
  identity: '#8b5cf6',
  anti_mechanization: '#ec4899',
  internal_relationships: '#f97316',
  emotion_state: '#ef4444',
  relationship: '#f59e0b',
  profile: '#10b981',
  mid_term: '#06b6d4',
  heuristic: '#3b82f6',
  cross_chat: '#6366f1',
  history: '#22c55e',
  reserved: '#94a3b8',
}

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

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatCost(n: number): string {
  if (n >= 1) return `¥${n.toFixed(2)}`
  if (n >= 0.01) return `¥${n.toFixed(4)}`
  if (n > 0) return `¥${n.toFixed(6)}`
  return '¥0'
}

function formatTimestamp(ts: number): string {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString('zh-CN')
}

// ========== 概览卡片 ==========

function OverviewCards({ overview }: { overview: DeepSeekOverviewInfo }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">智能体数</CardTitle>
          <Cpu className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{overview.total_agents}</div>
          <p className="text-xs text-muted-foreground">
            {overview.agents_with_budget} 个已分配预算
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">缓存命中率</CardTitle>
          <Zap className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {(overview.avg_cache_hit_rate * 100).toFixed(1)}%
          </div>
          <p className="text-xs text-muted-foreground">
            {overview.agents_with_cache} 个智能体有缓存数据
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">30日成本</CardTitle>
          <DollarSign className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{formatCost(overview.total_cost_30d)}</div>
          <p className="text-xs text-muted-foreground">全部智能体合计</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">批处理API</CardTitle>
          <Layers className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            <Badge variant={overview.batch_api_available ? 'default' : 'destructive'}>
              {overview.batch_api_available ? '可用' : '不可用'}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">50% 成本折扣</p>
        </CardContent>
      </Card>
    </div>
  )
}

// ========== Token 预算分配 ==========

function TokenBudgetPanel({ agentId }: { agentId: string }) {
  const { data: budget, isLoading } = useQuery({
    queryKey: ['deepseek', 'budget', agentId],
    queryFn: () => getAgentBudget(agentId),
  })

  if (isLoading) {
    return <Skeleton className="h-64 w-full" />
  }

  if (!budget) {
    return <div className="text-muted-foreground text-sm">暂无预算数据</div>
  }

  const totalTokens = budget.model_context_window

  return (
    <div className="space-y-4">
      <div className="text-sm text-muted-foreground">
        上下文窗口: {formatTokens(totalTokens)} tokens
      </div>

      {/* 堆叠条 */}
      <div className="flex h-8 overflow-hidden rounded-md">
        {budget.segments.map((seg) => (
          <div
            key={seg.segment}
            style={{
              width: `${seg.ratio * 100}%`,
              backgroundColor: SEGMENT_COLORS[seg.segment] || '#6b7280',
            }}
            className="flex items-center justify-center text-[10px] font-medium text-white transition-all hover:opacity-80"
            title={`${SEGMENT_LABELS[seg.segment] || seg.segment}: ${(seg.ratio * 100).toFixed(1)}% (${formatTokens(seg.token_limit)})`}
          >
            {seg.ratio >= 0.08 ? SEGMENT_LABELS[seg.segment]?.slice(0, 2) : ''}
          </div>
        ))}
      </div>

      {/* 图例 */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {budget.segments.map((seg) => (
          <div key={seg.segment} className="flex items-center gap-2 text-xs">
            <div
              className="h-3 w-3 shrink-0 rounded-sm"
              style={{ backgroundColor: SEGMENT_COLORS[seg.segment] || '#6b7280' }}
            />
            <span className="truncate">{SEGMENT_LABELS[seg.segment] || seg.segment}</span>
            <span className="ml-auto text-muted-foreground">
              {(seg.ratio * 100).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>

      {/* 详细列表 */}
      <ScrollArea className="h-48">
        <div className="space-y-2">
          {budget.segments
            .sort((a, b) => b.ratio - a.ratio)
            .map((seg) => (
              <div key={seg.segment} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span>{SEGMENT_LABELS[seg.segment] || seg.segment}</span>
                  <span className="text-muted-foreground">
                    {formatTokens(seg.token_limit)} tokens
                  </span>
                </div>
                <Progress value={seg.ratio * 100} className="h-1.5" />
              </div>
            ))}
        </div>
      </ScrollArea>
    </div>
  )
}

// ========== 前缀缓存统计 ==========

function CacheStatsPanel({ agentId }: { agentId: string }) {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['deepseek', 'cache', agentId],
    queryFn: () => getAgentCacheStats(agentId),
  })

  if (isLoading) {
    return <Skeleton className="h-48 w-full" />
  }

  if (!stats) {
    return <div className="text-muted-foreground text-sm">暂无缓存数据</div>
  }

  const hitRate = (stats.hit_rate * 100).toFixed(1)
  const totalTokens = stats.hit_tokens + stats.miss_tokens

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">前缀缓存</span>
        <Badge variant={stats.prefix_cache_enabled ? 'default' : 'secondary'}>
          {stats.prefix_cache_enabled ? '已启用' : '已禁用'}
        </Badge>
      </div>

      <div className="grid grid-cols-3 gap-4 text-center">
        <div>
          <div className="text-2xl font-bold text-green-500">{hitRate}%</div>
          <div className="text-xs text-muted-foreground">命中率</div>
        </div>
        <div>
          <div className="text-lg font-semibold">{formatTokens(stats.hit_tokens)}</div>
          <div className="text-xs text-muted-foreground">命中Token</div>
        </div>
        <div>
          <div className="text-lg font-semibold">{formatTokens(stats.miss_tokens)}</div>
          <div className="text-xs text-muted-foreground">未命中Token</div>
        </div>
      </div>

      {/* 命中率环形图 */}
      <div className="flex justify-center">
        <svg width={120} height={120} viewBox="0 0 120 120">
          <circle
            cx={60}
            cy={60}
            r={50}
            fill="none"
            stroke="currentColor"
            strokeWidth={8}
            className="text-muted/20"
          />
          <circle
            cx={60}
            cy={60}
            r={50}
            fill="none"
            stroke="#22c55e"
            strokeWidth={8}
            strokeDasharray={`${stats.hit_rate * 314.16} 314.16`}
            strokeLinecap="round"
            transform="rotate(-90 60 60)"
          />
          <text
            x={60}
            y={60}
            textAnchor="middle"
            dominantBaseline="central"
            className="fill-foreground text-xl font-bold"
          >
            {hitRate}%
          </text>
        </svg>
      </div>

      {totalTokens === 0 && (
        <p className="text-center text-xs text-muted-foreground">
          尚无缓存交互记录，数据将在对话后产生
        </p>
      )}
    </div>
  )
}

// ========== 批处理任务 ==========

function BatchPanel() {
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

// ========== 成本追踪 ==========

function CostPanel({ agentId }: { agentId: string }) {
  const { data: cost, isLoading: costLoading } = useQuery({
    queryKey: ['deepseek', 'cost', agentId],
    queryFn: () => getAgentCost(agentId),
  })

  const { data: report, isLoading: reportLoading } = useQuery({
    queryKey: ['deepseek', 'cost-report'],
    queryFn: getMonthlyCostReport,
  })

  if (costLoading) {
    return <Skeleton className="h-64 w-full" />
  }

  return (
    <div className="space-y-4">
      {cost && (
        <>
          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardContent className="pt-4 text-center">
                <div className="text-2xl font-bold">{formatCost(cost.total_cost)}</div>
                <div className="text-xs text-muted-foreground">30日总成本</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 text-center">
                <div className="text-lg font-semibold">
                  {formatTokens(cost.total_input_tokens)} / {formatTokens(cost.total_output_tokens)}
                </div>
                <div className="text-xs text-muted-foreground">输入 / 输出 Token</div>
              </CardContent>
            </Card>
          </div>

          {cost.total_cache_hit_tokens > 0 && (
            <div className="rounded-md border p-3 text-xs">
              <span className="text-muted-foreground">缓存命中Token: </span>
              <span className="font-medium">{formatTokens(cost.total_cache_hit_tokens)}</span>
            </div>
          )}
        </>
      )}

      {report && !reportLoading && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium">月度成本排行</h4>
          <ScrollArea className="h-48">
            <div className="space-y-1">
              {Object.entries(report.by_agent ?? {})
                .sort(([, a], [, b]) => b.cost - a.cost)
                .slice(0, 13)
                .map(([aid, data]) => (
                  <div
                    key={aid}
                    className="flex items-center justify-between rounded-md px-2 py-1 text-xs hover:bg-muted/50"
                  >
                    <span className="font-medium">{aid}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-muted-foreground">
                        {formatTokens(data.input_tokens + data.output_tokens)} tokens
                      </span>
                      <span className="font-medium">{formatCost(data.cost)}</span>
                    </div>
                  </div>
                ))}
            </div>
          </ScrollArea>
        </div>
      )}
    </div>
  )
}

// ========== 主页面 ==========

export function DeepSeekMonitorPage() {
  const [selectedAgent, setSelectedAgent] = useState<string>('')

  const { data: agents } = useQuery({
    queryKey: ['agent', 'list'],
    queryFn: getAgentList,
  })

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['deepseek', 'overview'],
    queryFn: getDeepSeekOverview,
  })

  const agentList: AgentConfigInfo[] = (agents as any) || []
  const currentAgent = selectedAgent || (agentList.length > 0 ? agentList[0].agent_id : '')

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">DeepSeek 优化面板</h1>
          <p className="text-sm text-muted-foreground">
            Token 预算分配 · 前缀缓存 · 批处理调度 · 成本追踪
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={currentAgent} onValueChange={setSelectedAgent}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="选择智能体" />
            </SelectTrigger>
            <SelectContent>
              {agentList.map((a) => (
                <SelectItem key={a.agent_id} value={a.agent_id}>
                  {a.display_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {overviewLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : overview ? (
        <OverviewCards overview={overview} />
      ) : null}

      <Tabs defaultValue="budget" className="space-y-4">
        <TabsList>
          <TabsTrigger value="budget">Token 预算</TabsTrigger>
          <TabsTrigger value="cache">前缀缓存</TabsTrigger>
          <TabsTrigger value="batch">批处理</TabsTrigger>
          <TabsTrigger value="cost">成本追踪</TabsTrigger>
        </TabsList>

        <TabsContent value="budget">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Token 预算分配</CardTitle>
            </CardHeader>
            <CardContent>
              {currentAgent ? (
                <TokenBudgetPanel agentId={currentAgent} />
              ) : (
                <p className="text-sm text-muted-foreground">请选择智能体</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="cache">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">前缀缓存统计</CardTitle>
            </CardHeader>
            <CardContent>
              {currentAgent ? (
                <CacheStatsPanel agentId={currentAgent} />
              ) : (
                <p className="text-sm text-muted-foreground">请选择智能体</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="batch">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">批处理任务</CardTitle>
            </CardHeader>
            <CardContent>
              <BatchPanel />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="cost">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">成本追踪</CardTitle>
            </CardHeader>
            <CardContent>
              {currentAgent ? (
                <CostPanel agentId={currentAgent} />
              ) : (
                <p className="text-sm text-muted-foreground">请选择智能体</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}