import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { backendApi } from '@/lib/http'
import { unifiedWsClient, type WsEventEnvelope } from '@/lib/unified-ws'

export interface AgentStatisticsItem {
  agent_id: string
  request_count: number
  total_input_tokens: number
  total_output_tokens: number
  total_cost: number
  avg_response_time: number
}

export interface ModelStatisticsItem {
  model_name: string
  request_count: number
  total_cost: number
  total_tokens: number
  avg_response_time: number
}

export interface TimeSeriesItem {
  timestamp: string
  requests: number
  cost: number
  tokens: number
}

interface DashboardSummary {
  total_requests: number
  total_cost: number
  total_tokens: number
  online_time: number
  total_messages: number
  total_replies: number
  avg_response_time: number
  cost_per_hour: number
  tokens_per_hour: number
}

interface DashboardData {
  summary: DashboardSummary
  model_stats: ModelStatisticsItem[]
  hourly_data: TimeSeriesItem[]
  daily_data: TimeSeriesItem[]
  recent_activity: Record<string, unknown>[]
}

const DEFAULT_HOURS = 24

export function useLLMStats(initialHours = DEFAULT_HOURS) {
  const [hours, setHours] = useState(initialHours)
  const [agentStats, setAgentStats] = useState<AgentStatisticsItem[]>([])
  const [modelStats, setModelStats] = useState<ModelStatisticsItem[]>([])
  const [timeSeriesData, setTimeSeriesData] = useState<TimeSeriesItem[]>([])
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isConnected, setIsConnected] = useState(false)
  const mountedRef = useRef(true)

  const fetchAllData = useCallback(async (h: number) => {
    setIsLoading(true)
    try {
      const [dashboardData, agentsData] = await Promise.allSettled([
        backendApi.get<DashboardData>('/api/webui/statistics/dashboard', { query: { hours: h } }),
        backendApi.get<{ hours: number; agents: AgentStatisticsItem[] }>('/api/webui/statistics/agents', { query: { hours: h } }),
      ])

      if (mountedRef.current) {
        if (dashboardData.status === 'fulfilled') {
          const d = dashboardData.value
          setModelStats(d.model_stats)
          setTimeSeriesData(d.hourly_data)
          setSummary(d.summary)
        }
        if (agentsData.status === 'fulfilled') {
          setAgentStats(agentsData.value.agents)
        }
      }
    } catch (err) {
      console.error('获取 LLM 统计数据失败:', err)
    } finally {
      if (mountedRef.current) {
        setIsLoading(false)
      }
    }
  }, [])

  const exportCSV = useCallback(async () => {
    try {
      const blob = await backendApi.get<Blob>(`/api/webui/statistics/export?hours=${hours}&format=csv`, {
        parse: 'blob',
        errorMessage: 'CSV 导出失败',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `llm_stats_${new Date().toISOString().slice(0, 19).replace(/[T:]/g, '_')}.csv`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('CSV 导出失败:', err)
    }
  }, [hours])

  useEffect(() => {
    mountedRef.current = true
    void fetchAllData(hours)

    const handleEvent = (message: WsEventEnvelope) => {
      if (message.domain === 'llm_stats') {
        if (message.event === 'call_completed') {
          // 增量更新：累加到当前统计
          const payload = message.data as {
            model_name?: string
            cost?: number
            prompt_tokens?: number
            completion_tokens?: number
            time_cost?: number
          }
          if (payload.model_name) {
            setModelStats((prev) => {
              const idx = prev.findIndex((m) => m.model_name === payload.model_name)
              if (idx >= 0) {
                const updated = [...prev]
                updated[idx] = {
                  ...updated[idx],
                  request_count: updated[idx].request_count + 1,
                  total_cost: updated[idx].total_cost + (payload.cost ?? 0),
                  total_tokens: updated[idx].total_tokens + (payload.prompt_tokens ?? 0) + (payload.completion_tokens ?? 0),
                }
                return updated
              }
              return prev
            })
          }
        }
      }
    }

    const handleConnectionChange = (connected: boolean) => {
      setIsConnected(connected)
      if (connected) {
        void unifiedWsClient.subscribe('llm_stats', 'main').catch(() => {})
      }
    }

    const removeEventListener = unifiedWsClient.addEventListener(handleEvent)
    const removeConnectionListener = unifiedWsClient.onConnectionChange(handleConnectionChange)

    if (unifiedWsClient.getStatus() === 'connected') {
      setIsConnected(true)
      void unifiedWsClient.subscribe('llm_stats', 'main').catch(() => {})
    }

    return () => {
      mountedRef.current = false
      removeEventListener()
      removeConnectionListener()
      void unifiedWsClient.unsubscribe('llm_stats', 'main').catch(() => {})
    }
  }, [hours, fetchAllData])

  const handleSetHours = useCallback((h: number) => {
    setHours(h)
  }, [])

  return {
    agentStats,
    modelStats,
    timeSeriesData,
    summary,
    isLoading,
    isConnected,
    hours,
    setHours: handleSetHours,
    exportCSV,
    refetch: () => void fetchAllData(hours),
  }
}