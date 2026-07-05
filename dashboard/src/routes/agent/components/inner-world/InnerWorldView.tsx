
import { Heart, Link2, Leaf, Clock, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'

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

interface InnerWorldViewProps {
  agentId: string
  onBack: () => void
}

export function InnerWorldView({ agentId, onBack }: InnerWorldViewProps) {
  const { t } = useTranslation()
  const { emotions, relationships, sessionCounts, latestSubAgentRecords, agents } = useBatchAgentData()
  const innerData = useInnerWorldData(agentId)

  const agent = innerData.agent
  const agentConfig = agents.find((a) => a.agent_id === agentId)

  const vitalSigns = agentConfig
    ? deriveVitalSignsData(
        agentConfig,
        emotions[agentId] ?? null,
        relationships[agentId] ?? null,
        sessionCounts[agentId] ?? 0,
        latestSubAgentRecords[agentId] ?? null,
      )
    : null

  if (innerData.isLoading || !agent) {
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
          <Tabs defaultValue="emotion">
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
                onUnbind={() => {}}
                onBindClick={() => {}}
                isUnbinding={false}
              />
            </TabsContent>
          </Tabs>

          <div className="mt-4 space-y-2 border-t pt-4">
            <LifeDefensePanel rules={agent.anti_mechanization_rules} />
            <CollapsedParameters
              talkValueModifier={agent.talk_value_modifier}
              idleBackoffModifier={agent.idle_backoff_modifier}
              relationshipGrowthRate={agent.relationship_growth_rate}
              emotionDecayRate={agent.emotion_decay_rate}
            />
          </div>
        </div>
      </ScrollArea>
    </div>
  )
}