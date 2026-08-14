/**
 * 成本追踪面板（R4 债清理 P1——从 deepseek-monitor/index.tsx 机械拆分）
 *
 * 职责：30 日总成本/输入输出 Token/缓存命中 Token + 月度成本排行。
 */
import { useQuery } from '@tanstack/react-query'

import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { getAgentCost, getMonthlyCostReport } from '@/lib/deepseek-api'
import { formatCost, formatTokens } from './overview-cards'

export function CostPanel({ agentId }: { agentId: string }) {
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
