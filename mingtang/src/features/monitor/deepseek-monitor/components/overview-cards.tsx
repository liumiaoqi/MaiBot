/**
 * DeepSeek 概览卡片 + 格式化工具（R4 债清理 P1——从 deepseek-monitor/index.tsx 机械拆分）
 *
 * 职责：4 项概览指标（智能体数/缓存命中率/30日成本/批处理API）+ 全页面共享的
 * token/成本/时间戳格式化工具（formatTokens/formatCost/formatTimestamp）。
 */
import { Cpu, DollarSign, Layers, Zap } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { DeepSeekOverviewInfo } from '@/lib/deepseek-api'

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

export function formatCost(n: number): string {
  if (n >= 1) return `¥${n.toFixed(2)}`
  if (n >= 0.01) return `¥${n.toFixed(4)}`
  if (n > 0) return `¥${n.toFixed(6)}`
  return '¥0'
}

export function formatTimestamp(ts: number): string {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString('zh-CN')
}

export function OverviewCards({ overview }: { overview: DeepSeekOverviewInfo }) {
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
