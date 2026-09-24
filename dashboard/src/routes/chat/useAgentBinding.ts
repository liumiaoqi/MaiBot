import { useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { bindSessionAgent, getAgentList, type AgentConfigInfo } from '@/lib/agent-api'
import { useToast } from '@/hooks/use-toast'
import { useTranslation } from 'react-i18next'

export interface AgentBindingInfo {
  agent_id: string
  display_name: string
  color: string
}

export function useAgentBinding(sessionId: string | undefined) {
  const { t } = useTranslation()
  const [currentAgentId, setCurrentAgentId] = useState<string>('silver_wolf')
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const { data: agents = [] } = useQuery({
    queryKey: ['agent', 'list'],
    queryFn: getAgentList,
  })

  const agentMap = new Map<string, AgentConfigInfo>(agents.map((a) => [a.agent_id, a]))
  const currentConfig = agentMap.get(currentAgentId)
  const currentAgent: AgentBindingInfo = {
    agent_id: currentAgentId,
    display_name: currentConfig?.display_name || t('agent.binding.defaultName'),
    color: currentConfig?.color || '#9b59b6',
  }

  const initFromSessionInfo = useCallback((agentId: string | undefined) => {
    setCurrentAgentId(agentId || 'silver_wolf')
  }, [])

  const switchAgent = useCallback(
    async (agentId: string) => {
      if (!sessionId) return
      try {
        await bindSessionAgent(sessionId, agentId)
        setCurrentAgentId(agentId)
        queryClient.invalidateQueries({ queryKey: ['chat-streams'] })
      } catch (e: any) {
        toast({
          title: t('agent.binding.switchFailed'),
          description: e?.message || String(e),
          variant: 'destructive',
        })
      }
    },
    [sessionId, queryClient, toast],
  )

  return { currentAgent, currentAgentId, initFromSessionInfo, switchAgent }
}