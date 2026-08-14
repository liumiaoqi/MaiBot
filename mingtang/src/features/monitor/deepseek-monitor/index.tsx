/**
 * DeepSeek 优化面板（T1-2-3 搬移——cockpit 只读模式）
 *
 * 定位：Token 预算分配 · 前缀缓存 · 批处理调度 · 成本追踪（REST only——零写操作）
 * 数据流：6 端点 useQuery 只读（overview / budget / cache / batch / cost / monthly-report）
 * 只读约束：零写操作（spec.md §4.3 #2）
 * i18n：页面标题 + Tab 标签走 monitor.deepseek.*（design.md §2.5），面板内文案保留源文件中文（行为等价）
 * 面板拆分（R4 债清理 P1）：components/overview-cards · token-budget-panel · cache-stats-panel
 * · batch-panel · cost-panel——本文件仅保留页面编排。
 */
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { PageShell } from '@/components/biz/page-shell'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { getAgentList, type AgentConfigInfo } from '@/lib/agent-api'
import { getDeepSeekOverview } from '@/lib/deepseek-api'

import { BatchPanel } from './components/batch-panel'
import { CacheStatsPanel } from './components/cache-stats-panel'
import { CostPanel } from './components/cost-panel'
import { OverviewCards } from './components/overview-cards'
import { TokenBudgetPanel } from './components/token-budget-panel'

export function DeepSeekMonitorPage() {
  const { t } = useTranslation()
  const [selectedAgent, setSelectedAgent] = useState<string>('')

  const { data: agents } = useQuery({
    queryKey: ['agent', 'list'],
    queryFn: getAgentList,
  })

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['deepseek', 'overview'],
    queryFn: getDeepSeekOverview,
  })

  const agentList: AgentConfigInfo[] = agents ?? []
  const currentAgent = selectedAgent || (agentList.length > 0 ? agentList[0].agent_id : '')

  return (
    <PageShell
      title={t('monitor.deepseek.title')}
      actions={
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
      }
    >
      <div className="space-y-6">
        <p className="text-sm text-muted-foreground">
          Token 预算分配 · 前缀缓存 · 批处理调度 · 成本追踪
        </p>

        {overviewLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : overview ? (
          <OverviewCards overview={overview} />
        ) : null}

        <Tabs defaultValue="budget" className="space-y-4">
          <TabsList>
            <TabsTrigger value="budget">{t('monitor.deepseek.budget')}</TabsTrigger>
            <TabsTrigger value="cache">{t('monitor.deepseek.cache')}</TabsTrigger>
            <TabsTrigger value="batch">批处理</TabsTrigger>
            <TabsTrigger value="cost">{t('monitor.deepseek.cost')}</TabsTrigger>
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
    </PageShell>
  )
}
