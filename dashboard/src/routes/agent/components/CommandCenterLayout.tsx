import { useMemo, useState } from 'react'

import { AnimatePresence, motion } from 'motion/react'
import { RefreshCw, Search, Zap } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'

import { useAgentNavigation } from '../hooks/useAgentNavigation'
import { useBatchAgentData } from '../hooks/useBatchAgentData'
import { useViewSwitch } from '../hooks/useViewSwitch'
import { deriveVitalSignsData } from '../utils/vital-signs'
import { deriveConstellationData } from '../utils/constellation'
import { VitalSignsCard } from './VitalSignsCard'
import { ViewSwitcher } from './ViewSwitcher'
import { InnerWorldView } from './inner-world/InnerWorldView'
import { AgentConstellation } from './constellation/AgentConstellation'
import { GlobalSituationView } from './global-situation/GlobalSituationView'
import { InteractionStream } from './InteractionStream'
import { InteractionConfigPanel } from './InteractionConfigPanel'
import { ManualTriggerDialog } from './ManualTriggerDialog'

export function CommandCenterLayout() {
  const { t } = useTranslation()
  const { agents, emotions, relationships, sessionCounts, latestSubAgentRecords, isLoading, refetch } = useBatchAgentData()

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
        )
      )
      .filter((vs) => {
        if (!searchQuery) return true
        const q = searchQuery.toLowerCase()
        return vs.agentId.toLowerCase().includes(q) || vs.displayName.toLowerCase().includes(q)
      })
  }, [agents, emotions, relationships, sessionCounts, latestSubAgentRecords, searchQuery])

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

      <AnimatePresence>
        {isInnerWorldOpen && selectedAgentId && (
          <motion.div
            key="inner-world-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50 flex items-center justify-center"
            style={{ backgroundColor: 'hsl(var(--card))' }}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="w-full h-full max-w-full md:max-w-5xl max-h-[85vh] rounded-lg border shadow-lg overflow-hidden"
              style={{ backgroundColor: 'hsl(var(--card))' }}
            >
              <InnerWorldView agentId={selectedAgentId} onBack={exitInnerWorld} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
