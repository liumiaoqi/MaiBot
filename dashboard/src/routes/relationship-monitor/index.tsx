import { useRouterState } from '@tanstack/react-router'
import { RefreshCw, Users } from 'lucide-react'
import { useMemo } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'

import { Skeleton } from '@/components/ui/skeleton'

import type { AgentConfigInfo, RelationshipInfo } from '@/lib/agent-api'

import { useRelationshipMonitor } from '@/hooks/useRelationshipMonitor'

import { cn } from '@/lib/utils'

const LEVEL_CONFIG: Record<number, { label: string; color: string; bgColor: string }> = {
  0: { label: '陌生人', color: 'text-slate-500', bgColor: 'bg-slate-100' },
  1: { label: '认识', color: 'text-blue-600', bgColor: 'bg-blue-100' },
  2: { label: '熟悉', color: 'text-emerald-600', bgColor: 'bg-emerald-100' },
  3: { label: '亲密', color: 'text-rose-600', bgColor: 'bg-rose-100' },
}

const LEVEL_THRESHOLDS = [
  { level: 3, min: 900, label: '亲密' },
  { level: 2, min: 650, label: '熟悉' },
  { level: 1, min: 350, label: '认识' },
  { level: 0, min: 0, label: '陌生人' },
]

function RelationshipLevelBadge({ level }: { level: number }) {
  const config = LEVEL_CONFIG[level] ?? LEVEL_CONFIG[0]
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
        config.bgColor,
        config.color
      )}
    >
      {config.label}
    </span>
  )
}

function RelationshipDistributionChart({ relationships }: { relationships: RelationshipInfo[] }) {
  const distribution = useMemo(() => {
    const counts: Record<number, number> = { 0: 0, 1: 0, 2: 0, 3: 0 }
    for (const rel of relationships) {
      counts[rel.level] = (counts[rel.level] || 0) + 1
    }
    return LEVEL_THRESHOLDS.map(({ level, label }) => ({
      level,
      label,
      count: counts[level] || 0,
      config: LEVEL_CONFIG[level],
    }))
  }, [relationships])

  const total = relationships.length || 1

  return (
    <div className="space-y-3">
      {distribution.map(({ level, label, count, config }) => (
        <div key={level} className="flex items-center gap-3">
          <span className={cn('w-12 text-xs font-medium', config.color)}>{label}</span>
          <div className="flex-1">
            <div className="h-3 bg-muted rounded-full overflow-hidden">
              <div
                className={cn('h-full rounded-full transition-all', config.bgColor)}
                style={{ width: `${(count / total) * 100}%`, minWidth: count > 0 ? '4px' : '0' }}
              />
            </div>
          </div>
          <span className="text-xs text-muted-foreground w-8 text-right">{count}</span>
        </div>
      ))}
    </div>
  )
}

function RelationshipScoreChart({ relationships }: { relationships: RelationshipInfo[] }) {
  const sorted = useMemo(
    () => [...relationships].sort((a, b) => b.score - a.score).slice(0, 20),
    [relationships]
  )

  if (sorted.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground text-sm">暂无关系数据</div>
    )
  }

  return (
    <div className="space-y-2">
      {sorted.map((rel) => (
        <div key={rel.user_id} className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground w-24 truncate" title={rel.user_id}>
            {rel.user_id}
          </span>
          <div className="flex-1">
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div
                className={cn(
                  'h-full rounded-full transition-all',
                  LEVEL_CONFIG[rel.level]?.bgColor ?? 'bg-slate-100'
                )}
                style={{ width: `${(rel.score / 1000) * 100}%` }}
              />
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs text-muted-foreground w-12 text-right">
              {Math.round(rel.score)}
            </span>
            <RelationshipLevelBadge level={rel.level} />
          </div>
        </div>
      ))}
    </div>
  )
}

function AgentRelationshipCard({
  agent,
  relationships,
  onClick,
}: {
  agent: AgentConfigInfo
  relationships: RelationshipInfo[]
  onClick: () => void
}) {
  const levelCounts = useMemo(() => {
    const counts: Record<number, number> = { 0: 0, 1: 0, 2: 0, 3: 0 }
    for (const rel of relationships) {
      counts[rel.level] = (counts[rel.level] || 0) + 1
    }
    return counts
  }, [relationships])

  const avgScore = useMemo(() => {
    if (relationships.length === 0) return 0
    return relationships.reduce((sum, r) => sum + r.score, 0) / relationships.length
  }, [relationships])

  return (
    <Card className="cursor-pointer transition-all hover:shadow-md" onClick={onClick}>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm shrink-0"
            style={{ backgroundColor: agent.color }}
          >
            {agent.display_name.charAt(0)}
          </div>
          <div className="flex-1 min-w-0">
            <CardTitle className="text-sm truncate">{agent.display_name}</CardTitle>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-muted-foreground">
                {relationships.length} 条关系
              </span>
              {relationships.length > 0 && (
                <span className="text-xs text-muted-foreground">
                  均分 {Math.round(avgScore)}
                </span>
              )}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex items-center gap-2">
          {LEVEL_THRESHOLDS.map(({ level, label }) => {
            const count = levelCounts[level] || 0
            if (count === 0) return null
            return (
              <div key={level} className="flex items-center gap-1">
                <span
                  className={cn(
                    'w-2 h-2 rounded-full',
                    LEVEL_CONFIG[level]?.bgColor ?? 'bg-slate-100'
                  )}
                />
                <span className="text-xs text-muted-foreground">
                  {label} {count}
                </span>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

export function RelationshipMonitorPage() {

  const search = useRouterState().location.search as Record<string, unknown>
  const agentParam = typeof search.agent === 'string' ? search.agent : undefined

  const {
    agents,
    allRelationships,
    selectedAgentId,
    selectedAgent,
    selectedRelationships,
    totalRelationships,
    isInitialLoading,
    isRefreshing,
    setSelectedAgentId,
    refresh,
  } = useRelationshipMonitor(agentParam)


  return (
    <div className="h-full flex flex-col">
      {/* 头部 */}
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-2">
          <Users className="h-5 w-5 text-primary" />
          <h1 className="text-lg font-semibold">关系查看</h1>
          <Badge variant="outline">
            {agents.length} 智能体 · {totalRelationships} 条关系
          </Badge>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => {
            refresh()
          }}
        >
          <RefreshCw
            className={cn(
              'h-4 w-4',
              isRefreshing && 'animate-spin'
            )}
          />
        </Button>
      </div>

      <div className="flex-1 overflow-hidden flex">
        {/* 左侧：智能体选择 */}
        <div className="w-72 border-r shrink-0 flex flex-col">
          <div className="p-3 border-b">
            <p className="text-sm font-medium">选择智能体</p>
          </div>
          <ScrollArea className="flex-1">
            <div className="p-3 space-y-2">
              {isInitialLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-20 w-full rounded-lg" />
                ))
              ) : (
                agents.map((agent) => (
                  <AgentRelationshipCard
                    key={agent.agent_id}
                    agent={agent}
                    relationships={allRelationships[agent.agent_id] ?? []}
                    onClick={() => setSelectedAgentId(agent.agent_id)}
                  />
                ))
              )}
            </div>
          </ScrollArea>
        </div>

        {/* 右侧：关系详情 */}
        <div className="flex-1 overflow-hidden">
          {!selectedAgentId ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              <div className="text-center">
                <Users className="h-12 w-12 mx-auto mb-3 opacity-30" />
                <p>选择一个智能体查看关系详情</p>
              </div>
            </div>
          ) : isInitialLoading ? (
            <div className="p-6 space-y-4">
              <Skeleton className="h-8 w-48" />
              <div className="grid grid-cols-2 gap-4">
                <Skeleton className="h-48 rounded-lg" />
                <Skeleton className="h-48 rounded-lg" />
              </div>
            </div>
          ) : (
            <ScrollArea className="h-full">
              <div className="p-6 space-y-6 max-w-4xl">
                {/* 头部 */}
                <div className="flex items-center gap-4">
                  <div
                    className="w-14 h-14 rounded-full flex items-center justify-center text-white font-bold text-xl shrink-0"
                    style={{ backgroundColor: selectedAgent?.color }}
                  >
                    {selectedAgent?.display_name.charAt(0)}
                  </div>
                  <div>
                    <h2 className="text-xl font-bold">{selectedAgent?.display_name}</h2>
                    <p className="text-sm text-muted-foreground">
                      关系进展速率 ×{selectedAgent?.relationship_growth_rate.toFixed(1)} ·{' '}
                      {selectedRelationships.length} 条关系
                    </p>
                  </div>
                </div>

                {/* 统计卡片 */}
                <div className="grid grid-cols-4 gap-4">
                  {LEVEL_THRESHOLDS.map(({ level, label }) => {
                    const count = selectedRelationships.filter((r) => r.level === level).length
                    return (
                      <Card key={level}>
                        <CardContent className="pt-4 pb-3 text-center">
                          <p className="text-2xl font-bold">{count}</p>
                          <p className={cn('text-xs mt-1', LEVEL_CONFIG[level]?.color)}>
                            {label}
                          </p>
                        </CardContent>
                      </Card>
                    )
                  })}
                </div>

                {/* 关系分布 + 排行 */}
                <div className="grid grid-cols-2 gap-6">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">关系等级分布</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <RelationshipDistributionChart relationships={selectedRelationships} />
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">平均分数</CardTitle>
                    </CardHeader>
                    <CardContent>
                      {selectedRelationships.length > 0 ? (
                        <div className="text-center">
                          <p className="text-4xl font-bold">
                            {Math.round(
                              selectedRelationships.reduce((s, r) => s + r.score, 0) /
                                selectedRelationships.length
                            )}
                          </p>
                          <p className="text-sm text-muted-foreground mt-1">/ 1000</p>
                          <div className="mt-4">
                            <Progress
                              value={
                                (selectedRelationships.reduce((s, r) => s + r.score, 0) /
                                  selectedRelationships.length /
                                  1000) *
                                100
                              }
                            />
                          </div>
                        </div>
                      ) : (
                        <div className="text-center py-8 text-muted-foreground text-sm">
                          暂无数据
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>

                {/* 关系排行 */}
                <Card>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm">关系排行（前20）</CardTitle>
                      <span className="text-xs text-muted-foreground">
                        共 {selectedRelationships.length} 条
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <RelationshipScoreChart relationships={selectedRelationships} />
                  </CardContent>
                </Card>
              </div>
            </ScrollArea>
          )}
        </div>
      </div>
    </div>
  )
}