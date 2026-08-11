import { useMemo, useState } from 'react'

import { RefreshCw, Search, Zap } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'

import { useAgentNavigation } from '../hooks/use-agent-navigation'
import { useBatchAgentData } from '../hooks/use-batch-agent-data'
import { useViewSwitch } from '../hooks/use-view-switch'
import { deriveConstellationData } from '../utils/constellation'
import { deriveVitalSignsData } from '../utils/vital-signs'
import { AgentConstellation } from './constellation/agent-constellation'
import { GlobalSituationView } from './global-situation/global-situation-view'
import { InnerWorldView } from './inner-world/inner-world-view'
import { InteractionConfigPanel } from './interaction-config-panel'
import { InteractionStream } from './interaction-stream'
import { ManualTriggerDialog } from './manual-trigger-dialog'
import { ViewSwitcher } from './view-switcher'
import { VitalSignsCard } from './vital-signs-card'

// motion/react 缺失（mingtang 无此依赖）→ 覆盖层改为条件渲染（进入/退出动画省略，行为等价）
export function CommandCenterLayout() {
  const { t } = useTranslation()
  const { agents, emotions, relationships, internalRelationshipsSummary, sessionCounts, latestSubAgentRecords, isLoading, refetch } = useBatchAgentData()

  const agentIds = useMemo(() => agents.map((a) => a.agent_id), [agents])
  const { selectedAgentId, setSelectedAgentId, isInnerWorldOpen, exitInnerWorld } = useAgentNavigation(agentIds)
  const { currentView, switchView } = useViewSwitch()

  const [searchQuery, setSearchQuery] = useState('')
  const [triggerDialogOpen, setTriggerDialogOpen] = useState(false)
  const [showConfig, setShowConfig] = useState(false)

  const vitalSignsList = useMemo(() => {
    if (!agents.length) return []
    return agents
      .map((agent) =>
        deriveVitalSignsData(
          agent,
          emotions[agent.agent_id] ?? null,
          relationships[agent.agent_id] ?? null,
          sessionCounts[agent.agent_id] ?? 0,
          latestSubAgentRecords[agent.agent_id] ?? null,
          internalRelationshipsSummary[agent.agent_id],
        )
      )
      .filter((vs) => {
        if (!searchQuery) return true
        const q = searchQuery.toLowerCase()
        return vs.agentId.toLowerCase().includes(q) || vs.displayName.toLowerCase().includes(q)
      })
  }, [agents, emotions, relationships, sessionCounts, latestSubAgentRecords, internalRelationshipsSummary, searchQuery])

  const constellationData = useMemo(() =>
    deriveConstellationData(agents, emotions, sessionCounts),
    [agents, emotions, sessionCounts]
  )

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between p-4 border-b shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">{t('agent.commandCenter.title')}</h1>
          <span className="text-xs text-muted-foreground">{t('agent.commandCenter.subtitle')}</span>
        </div>
        <div className="flex items-center gap-2">
          <ViewSwitcher currentView={currentView} onSwitch={switchView} />
          <Button variant="ghost" size="icon" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {currentView === 'dashboard' && (
        <>
          <div className="px-4 py-2 border-b shrink-0">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder={t('agent.commandCenter.searchPlaceholder')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>
          </div>
          <ScrollArea className="flex-1">
            <div className="p-4">
              {isLoading ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} className="h-40 w-full rounded-lg" />
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {vitalSignsList.map((vs) => (
                    <VitalSignsCard
                      key={vs.agentId}
                      data={vs}
                      isSelected={selectedAgentId === vs.agentId}
                      onClick={() => setSelectedAgentId(vs.agentId)}
                    />
                  ))}
                </div>
              )}
            </div>
          </ScrollArea>
        </>
      )}

      {currentView === 'constellation' && (
        <AgentConstellation
          data={constellationData}
          selectedAgentId={selectedAgentId}
          onNodeClick={(id) => setSelectedAgentId(id)}
          onNodeDoubleClick={(id) => setSelectedAgentId(id)}
          emotions={emotions}
          sessionCounts={sessionCounts}
          agents={agents}
        />
      )}

      {currentView === 'global' && (
        <div className="flex flex-1 overflow-hidden">
          <div className="flex-1 overflow-auto">
            <GlobalSituationView />
          </div>
          <div className="w-80 border-l shrink-0 overflow-auto p-3 space-y-4">
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs gap-1"
                onClick={() => setTriggerDialogOpen(true)}
              >
                <Zap className="h-3 w-3" />
                {t('agent.interaction.manualTrigger.title')}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={() => setShowConfig(!showConfig)}
              >
                ⚙
              </Button>
            </div>
            {showConfig && <InteractionConfigPanel />}
            <InteractionStream />
          </div>
        </div>
      )}

      <ManualTriggerDialog open={triggerDialogOpen} onOpenChange={setTriggerDialogOpen} />

      {isInnerWorldOpen && selectedAgentId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-card">
          <div className="w-full h-full max-w-full md:max-w-5xl max-h-[85vh] rounded-lg border shadow-lg overflow-hidden bg-card">
            <InnerWorldView agentId={selectedAgentId} onBack={exitInnerWorld} />
          </div>
        </div>
      )}
    </div>
  )
}