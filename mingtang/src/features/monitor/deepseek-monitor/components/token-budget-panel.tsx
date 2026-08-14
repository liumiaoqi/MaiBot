/**
 * Token 预算分配面板（R4 债清理 P1——从 deepseek-monitor/index.tsx 机械拆分）
 *
 * 职责：上下文窗口 + segment 堆叠条/图例/详细列表（SEGMENT_LABELS/SEGMENT_COLORS 归属本面板）。
 */
import { useQuery } from '@tanstack/react-query'

import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { getAgentBudget } from '@/lib/deepseek-api'
import { formatTokens } from './overview-cards'

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

export function TokenBudgetPanel({ agentId }: { agentId: string }) {
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
