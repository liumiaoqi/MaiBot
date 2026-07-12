import { useState } from 'react'
import { Activity, Heart, Link2, Leaf, Clock, Users, MessageCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useToast } from '@/hooks/use-toast'

import { bindSessionAgent, unbindSessionAgent } from '@/lib/agent-api'
import { useInnerWorldData } from '../../hooks/useInnerWorldData'
import { deriveVitalSignsData } from '../../utils/vital-signs'
import { useBatchAgentData } from '../../hooks/useBatchAgentData'
import { IdentityHeader } from './IdentityHeader'
import { EmotionLandscape } from './EmotionLandscape'
import { RelationshipNetwork } from './RelationshipNetwork'
import { MemoryGarden } from './MemoryGarden'
import { LifeTimeline } from './LifeTimeline'
import { ActiveSessions } from './ActiveSessions'
import { LifeDefensePanel } from './LifeDefensePanel'
import { CollapsedParameters } from './CollapsedParameters'
import { UnbindConfirmDialog } from './UnbindConfirmDialog'
import { BindSessionDialog } from './BindSessionDialog'
import { MonologuePanel } from './MonologuePanel'
import { AutonomyLogPanel } from '../AutonomyLogPanel'
import { StateAwarenessPanel } from '../StateAwarenessPanel'
import { MigrationPanel } from './MigrationPanel'

interface InnerWorldViewProps {
  agentId: string
  onBack: () => void
}

export function InnerWorldView({ agentId, onBack }: InnerWorldViewProps) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const { emotions, relationships, sessionCounts, latestSubAgentRecords, agents } = useBatchAgentData()
  const innerData = useInnerWorldData(agentId)

  const [unbindConfirmOpen, setUnbindConfirmOpen] = useState(false)
  const [pendingUnbindSessionId, setPendingUnbindSessionId] = useState<string | null>(null)
  const [bindDialogOpen, setBindDialogOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<string>('emotion')

  const agent = innerData.agent
  const agentConfig = agents.find((a) => a.agent_id === agentId)

  const boundSessionIds = innerData.sessions.map((s) => s.session_id)

  const unbindMutation = useMutation({
    mutationFn: (sessionId: string) => unbindSessionAgent(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents', 'sessions', agentId] })
      queryClient.invalidateQueries({ queryKey: ['agents', 'batch-sessions'] })
      setUnbindConfirmOpen(false)
      setPendingUnbindSessionId(null)
    },
    onError: () => {
      toast({ title: t('agent.activeSessions.unbindFailed'), variant: 'destructive' })
    },
  })

  const bindMutation = useMutation({
    mutationFn: (sessionId: string) => bindSessionAgent(sessionId, agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents', 'sessions', agentId] })
      queryClient.invalidateQueries({ queryKey: ['agents', 'batch-sessions'] })
    },
    onError: () => {
      toast({ title: t('agent.activeSessions.bindFailed'), variant: 'destructive' })
    },
  })

  const isBinding = unbindMutation.isPending || bindMutation.isPending

  const vitalSigns = agentConfig
    ? deriveVitalSignsData(
        agentConfig,
        emotions[agentId] ?? null,
        relationships[agentId] ?? null,
        sessionCounts[agentId] ?? 0,
        latestSubAgentRecords[agentId] ?? null,
      )
    : null

  if (innerData.isCoreLoading || !agent) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        {t('agent.innerWorld.loading')}
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {vitalSigns && (
        <IdentityHeader
          vitalSigns={vitalSigns}
          personality={agent.personality}
          onBack={onBack}
        />
      )}

      <ScrollArea className="flex-1">
        <div className="p-4">
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="mb-4">
              <TabsTrigger value="emotion">
                <Heart className="h-3.5 w-3.5 mr-1" />
                {t('agent.innerWorld.subView.emotion')}
              </TabsTrigger>
              <TabsTrigger value="relationship">
                <Users className="h-3.5 w-3.5 mr-1" />
                {t('agent.innerWorld.subView.relationship')}
              </TabsTrigger>
              <TabsTrigger value="memory">
                <Leaf className="h-3.5 w-3.5 mr-1" />
                {t('agent.innerWorld.subView.memory')}
              </TabsTrigger>
              <TabsTrigger value="timeline">
                <Clock className="h-3.5 w-3.5 mr-1" />
                {t('agent.innerWorld.subView.timeline')}
              </TabsTrigger>
              <TabsTrigger value="sessions">
                <Link2 className="h-3.5 w-3.5 mr-1" />
                {t('agent.innerWorld.subView.sessions')}
              </TabsTrigger>
              <TabsTrigger value="monologue">
                <MessageCircle className="h-3.5 w-3.5 mr-1" />
                {t('agent.monologue.panel.title')}
              </TabsTrigger>
              <TabsTrigger value="autonomy">
                <Activity className="h-3.5 w-3.5 mr-1" />
                {t('agent.innerWorld.subView.autonomy')}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="emotion">
              <EmotionLandscape
                agentId={agentId}
                emotion={innerData.emotion}
                agent={agent}
                behaviorRules={innerData.emotionBehaviorRules}
              />
            </TabsContent>

            <TabsContent value="relationship">
              <RelationshipNetwork
                agentId={agentId}
                relationships={innerData.relationships}
                internalRelationships={agent.internal_relationships}
                agents={agents}
              />
            </TabsContent>

            <TabsContent value="memory">
              <MemoryGarden
                agentId={agentId}
                memoryFocusAreas={agent.memory_focus_areas}
                subAgentRecords={innerData.subAgentRecords}
              />
            </TabsContent>

            <TabsContent value="timeline">
              <LifeTimeline
                emotion={innerData.emotion}
                relationships={innerData.relationships}
                subAgentRecords={innerData.subAgentRecords}
              />
            </TabsContent>

            <TabsContent value="sessions">
              <ActiveSessions
                sessions={innerData.sessions}
                onUnbind={(sessionId) => {
                  setPendingUnbindSessionId(sessionId)
                  setUnbindConfirmOpen(true)
                }}
                onUnbindSpecific={(sessionId, _targetAgentId) => {
                  unbindMutation.mutate(sessionId)
                }}
                onBindClick={() => setBindDialogOpen(true)}
                isUnbinding={isBinding}
              />
            </TabsContent>

            <TabsContent value="monologue">
              <MonologuePanel agentId={agentId} />
            </TabsContent>

            <TabsContent value="autonomy">
              <div className="space-y-4">
                <AutonomyLogPanel agentId={agentId} />
                <StateAwarenessPanel
                  sessionId={innerData.sessions.length > 0 ? innerData.sessions[0].session_id : null}
                />
                <MigrationPanel />
              </div>
            </TabsContent>
          </Tabs>

          <div className="mt-4 space-y-2 border-t pt-4">
            <LifeDefensePanel rules={agent.anti_mechanization_rules} />
            <CollapsedParameters
              talkValueModifier={agent.talk_value_modifier}

              relationshipGrowthRate={agent.relationship_growth_rate}
              emotionDecayRate={agent.emotion_decay_rate}
            />
          </div>
        </div>
      </ScrollArea>

      <UnbindConfirmDialog
        open={unbindConfirmOpen}
        onOpenChange={setUnbindConfirmOpen}
        onConfirm={() => {
          if (pendingUnbindSessionId) {
            unbindMutation.mutate(pendingUnbindSessionId)
          }
        }}
        sessionName={
          innerData.sessions.find((s) => s.session_id === pendingUnbindSessionId)?.display_name ?? ''
        }
      />

      <BindSessionDialog
        open={bindDialogOpen}
        onOpenChange={setBindDialogOpen}
        onSelect={(sessionId) => bindMutation.mutate(sessionId)}
        agentId={agentId}
        boundSessionIds={boundSessionIds}
      />
    </div>
  )
}