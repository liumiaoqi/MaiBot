/**
 * 仪表盘首页（R4-4b 搬移）
 *
 * 组合 8 hooks + 4 内置卡片 + HomeCardManager + 插件卡片。
 * 从 dashboard/src/routes/index.tsx 抽出，消费已搬移的 home 域 hooks/cards/manager。
 */
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { AgentStatusCard } from './cards/agent-status-card'
import { ChatStreamCard } from './cards/chat-stream-card'
import { LLMOverviewCard } from './cards/llm-overview-card'
import { SystemStatusCard } from './cards/system-status-card'
import { HomeCardManager, type HomeCardDefinition } from './home-card-manager'
import { useBotStatus } from './hooks/use-bot-status'
import { useDashboardData } from './hooks/use-dashboard-data'
import { useMaibotVersion } from './hooks/use-maibot-version'
import { usePluginHomeCards } from './hooks/use-plugin-home-cards'
import { APP_VERSION } from '@/lib/version'

function formatNumber(num: number): { display: string; exact: string; needsExact: boolean } {
  if (num >= 10000) {
    return { display: `${(num / 1000).toFixed(0)}k`, exact: String(num), needsExact: true }
  }
  return { display: String(num), exact: String(num), needsExact: false }
}

function formatCurrency(num: number): { display: string; exact: string; needsExact: boolean } {
  if (num >= 100) {
    return { display: `¥${num.toFixed(0)}`, exact: num.toFixed(2), needsExact: true }
  }
  return { display: `¥${num.toFixed(2)}`, exact: num.toFixed(2), needsExact: false }
}

function formatTime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  return `${Math.floor(seconds / 3600)}h${Math.floor((seconds % 3600) / 60)}m`
}

export function HomePage() {
  const { t } = useTranslation()
  const { dashboardData } = useDashboardData()
  const { botStatus, isBotStatusLoading } = useBotStatus()
  const { pluginHomeCards } = usePluginHomeCards()
  const { maibotStableRelease } = useMaibotVersion()
  void maibotStableRelease

  const builtinCards = useMemo<HomeCardDefinition[]>(() => {
    const cards: HomeCardDefinition[] = []

    if (dashboardData?.summary) {
      cards.push({
        id: 'llm-overview',
        title: t('home.llmOverview.title'),
        source: 'builtin',
        width: 'medium',
        render: () => <LLMOverviewCard summary={dashboardData.summary} formatNumber={formatNumber} formatCurrency={formatCurrency} />,
      })
    }

    cards.push({
      id: 'system-status',
      title: t('home.systemStatus.title'),
      source: 'builtin',
      width: 'medium',
      render: () => <SystemStatusCard botStatus={botStatus} isBotStatusLoading={isBotStatusLoading} webuiVersion={APP_VERSION} formatTime={formatTime} />,
    })

    if (dashboardData?.agent_stats) {
      cards.push({
        id: 'agent-status',
        title: t('home.agentStatus.title'),
        source: 'builtin',
        width: 'medium',
        render: () => <AgentStatusCard agentStats={dashboardData.agent_stats} />,
      })
    }

    if (dashboardData) {
      cards.push({
        id: 'chat-stream',
        title: t('home.chatStream.title'),
        source: 'builtin',
        width: 'medium',
        render: () => <ChatStreamCard agentStats={dashboardData.agent_stats} recentActivity={dashboardData.recent_activity} />,
      })
    }

    return cards
  }, [dashboardData, botStatus, isBotStatusLoading, t])

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <HomeCardManager cards={builtinCards} pluginCards={pluginHomeCards} />
    </div>
  )
}