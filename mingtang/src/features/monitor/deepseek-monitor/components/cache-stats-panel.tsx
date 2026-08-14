/**
 * 前缀缓存统计面板（R4 债清理 P1——从 deepseek-monitor/index.tsx 机械拆分）
 *
 * 职责：缓存启用徽标 + 命中/未命中 Token + 命中率环形图。
 */
import { useQuery } from '@tanstack/react-query'

import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { getAgentCacheStats } from '@/lib/deepseek-api'
import { formatTokens } from './overview-cards'

export function CacheStatsPanel({ agentId }: { agentId: string }) {
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
